import gc

import torch

from nucleo import configuracion as app_config
from nucleo.recursos import hilos_de_procesamiento
from infraestructura import hardware

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    WhisperModel = None
    HAS_FASTER_WHISPER = False

# Solo aplica si hay GPU disponible; es un plus oportunista, no un requisito.
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False


# Catálogo CPU (o GPU NVIDIA con < 4GB VRAM): modelos livianos.
WHISPER_MODELS = [
    "Systran/faster-whisper-tiny ➔ [Más liviano y rápido • menor precisión — para pruebas rápidas en CPU]",
    "Systran/faster-whisper-base ➔ [Balance rapidez/precisión en CPU modesta]",
    "Systran/faster-whisper-small ➔ [Recomendado • mejor precisión en español, aún viable en CPU]",
]

# Catálogo GPU NVIDIA con >= 4GB VRAM: modelos más grandes y precisos.
GPU_WHISPER_MODELS = [
    "Systran/faster-whisper-medium ➔ [Buen punto medio • cómodo desde 4GB VRAM]",
    "deepdml/faster-whisper-large-v3-turbo-ct2 ➔ [Recomendado • rápido y preciso, ~6GB VRAM]",
    "Systran/faster-whisper-large-v3 ➔ [Máxima precisión • ideal con 8GB+ VRAM]",
]

# 3.5 en vez de 4.0: el driver/SO se queda con algo de VRAM (en una GPU de
# notebook "4GB" real medimos ~3.68GB usables vía CUDA), así que un umbral
# estricto de 4.0 excluiría justo a las tarjetas "clase 4GB" que se busca cubrir.
MIN_GPU_TIER_VRAM_GB = 3.5


def get_device():
    """Usa GPU NVIDIA (CUDA) si está disponible; si no, cae a CPU. CTranslate2
    (el motor de faster-whisper) no soporta AMD/ROCm, así que una GPU AMD
    también cae a CPU aquí — su fallback real vive en motor_transformers.py."""
    return "cuda" if hardware.detect_gpu_vendor() == "nvidia" else "cpu"


def get_vram_gb() -> float:
    """VRAM total de la GPU CUDA actual en GB, o 0 si no hay GPU."""
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.get_device_properties(0).total_memory / (1024**3)


class WhisperEngine:
    """Adaptador delgado sobre faster-whisper: carga de modelo, liberación
    de memoria e inferencia cruda (sin preprocesamiento de audio ni
    formateo de salida — eso es responsabilidad de la capa de servicios)."""

    def __init__(self):
        self.device = get_device()
        self.current_model = None
        self.current_backend = None
        self._last_load_args = None  # (model_id_or_path,)

    @property
    def available_models(self):
        """Catálogo GPU (modelos grandes) si hay NVIDIA con >= 4GB VRAM;
        catálogo liviano (CPU, o GPU con menos VRAM) en cualquier otro caso."""
        if self.device == "cuda" and get_vram_gb() >= MIN_GPU_TIER_VRAM_GB:
            return GPU_WHISPER_MODELS
        return WHISPER_MODELS

    def free_memory(self):
        """Libera la memoria del modelo actual antes de cargar otro."""
        if self.current_model is not None:
            del self.current_model
            self.current_model = None

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

    def load_model(self, model_id_or_path: str) -> str:
        """Carga un modelo faster-whisper (local o desde el Hub de HuggingFace)
        con la cuantización apropiada para el hardware disponible."""
        self.free_memory()
        self._last_load_args = (model_id_or_path,)

        if not HAS_FASTER_WHISPER:
            return "❌ La librería 'faster-whisper' no está instalada."

        print(f"[faster-whisper] Inicializando '{model_id_or_path}' en '{self.device}'...")

        try:
            fw_compute_type = app_config.get_param("compute_type")
            if fw_compute_type == "default":
                if self.device == "cuda":
                    fw_compute_type = "int8" if get_vram_gb() < 5.0 else "int8_float16"
                else:
                    fw_compute_type = "int8"

            try:
                # En CPU se deja un núcleo libre: el servidor sigue atendiendo a la gente mientras transcribe.
                self.current_model = WhisperModel(
                    model_id_or_path, device=self.device, compute_type=fw_compute_type, cpu_threads=hilos_de_procesamiento()
                )
            except Exception as e:
                if "out of memory" in str(e).lower() and self.device == "cuda":
                    print("⚠️ OOM Detectado en GPU. Reintentando con limpieza profunda y cuantización int8 extrema...")
                    self.free_memory()
                    try:
                        # Forzar int8 en GPU, nunca saltar a CPU automáticamente
                        self.current_model = WhisperModel(model_id_or_path, device="cuda", compute_type="int8")
                    except Exception as e2:
                        raise RuntimeError(f"GPU Insuficiente: Incluso con cuantización int8, el modelo no cabe en la VRAM. Error: {str(e2)}")
                else:
                    raise e

            self.current_backend = "faster-whisper"
            return f"✅ Modelo montado correctamente.\nMotor: FASTER-WHISPER\nDispositivo: {self.device.upper()}\nListo."

        except Exception as e:
            self.current_model = None
            self.current_backend = None
            return f"❌ Fallo al cargar el modelo:\n{str(e)}"

    def ensure_model_loaded(self) -> bool:
        """Asegura que el modelo actual esté cargado. Si fue descargado (offload), lo recarga."""
        if self.current_model is not None:
            return True
        if self._last_load_args:
            print("[whisper_engine] Restaurando modelo offloaded para continuar el lote...")
            self.load_model(*self._last_load_args)
            return self.current_model is not None
        return False

    def transcribe_raw(self, audio_path: str):
        """Generador que ejecuta la inferencia de faster-whisper y reporta
        progreso. Yields dicts con status/full_text/segments — sin SRT ni
        métricas de presentación, eso vive en el servicio que orquesta."""
        if not self.current_model:
            yield {"status": "❌ Sin modelo", "full_text": "No hay modelo inicializado.", "segments": []}
            return

        vad_filter = app_config.get_param("vad_filter")
        beam_size = app_config.get_param("beam_size")
        kwargs = {"audio": audio_path, "vad_filter": vad_filter, "beam_size": beam_size, "language": "es"}

        if self.device == "cpu":
            # Medido (4 hilos, int8, clase real): con beam 5 `small` va a 2,5-3,5x el tiempo real y con beam 1 a 6-7x,
            # y una clase de 90 minutos pasa de ~40 a ~15 minutos. En un servidor 24/7 sin GPU el tiempo manda.
            kwargs["beam_size"] = 1

        if self.device == "cuda":
            if get_vram_gb() < 5.0:
                # GPUs chicas: greedy search + VAD forzado + chunks más pequeños para evitar picos de VRAM.
                kwargs["condition_on_previous_text"] = False
                kwargs["beam_size"] = 1
                kwargs["vad_filter"] = True
                kwargs["vad_parameters"] = dict(min_silence_duration_ms=500)

        full_text = ""
        segments_data = []

        try:
            segments, info = self.current_model.transcribe(**kwargs)
            for seg in segments:
                full_text += seg.text + " "
                segments_data.append({'start': seg.start, 'end': seg.end, 'text': seg.text})
                yield {"status": "✍️ Transcribiendo", "full_text": full_text.strip(), "segments": segments_data}
        except Exception as e:
            if "out of memory" in str(e).lower() and self.device == "cuda":
                print("⚠️ OOM durante transcripción. Reintentando con configuración mínima (Beam 1)...")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                kwargs["beam_size"] = 1
                kwargs["condition_on_previous_text"] = False
                segments, info = self.current_model.transcribe(**kwargs)
                for seg in segments:
                    full_text += seg.text + " "
                    segments_data.append({'start': seg.start, 'end': seg.end, 'text': seg.text})
                    yield {"status": "✍️ Transcribiendo (Modo Seguro)", "full_text": full_text.strip(), "segments": segments_data}
            else:
                raise
