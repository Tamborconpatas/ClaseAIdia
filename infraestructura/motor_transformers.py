import gc

import torch

try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
except ImportError:
    pipeline = None
    HAS_TRANSFORMERS = False

try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    sf = None
    HAS_SOUNDFILE = False


# Solo variantes livianas, mismo criterio que WHISPER_MODELS en motor_whisper.py.
TRANSFORMERS_WHISPER_MODELS = [
    "openai/whisper-tiny ➔ [Más liviano y rápido • menor precisión]",
    "openai/whisper-base ➔ [Balance rapidez/precisión]",
    "openai/whisper-small ➔ [Recomendado • mejor precisión en español]",
]


class TransformersEngine:
    """Motor Whisper vía `transformers` + PyTorch, para GPU AMD (ROCm) —
    PyTorch expone esa GPU bajo el mismo namespace `torch.cuda`, a
    diferencia de CTranslate2 (usado por WhisperEngine), que no la soporta.
    Misma interfaz que WhisperEngine para que TranscriptionService use
    ambos motores indistintamente."""

    def __init__(self):
        self.device = "cuda"
        self.current_model = None
        self.current_backend = None
        self._last_load_args = None  # (model_id_or_path,)

    @property
    def available_models(self):
        return TRANSFORMERS_WHISPER_MODELS

    def free_memory(self):
        if self.current_model is not None:
            del self.current_model
            self.current_model = None

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def load_model(self, model_id_or_path: str) -> str:
        """Carga un modelo Whisper vía transformers en la GPU AMD (ROCm)."""
        self.free_memory()
        self._last_load_args = (model_id_or_path,)

        if not HAS_TRANSFORMERS:
            return "❌ La librería 'transformers' no está instalada (requerida para GPU AMD/ROCm)."

        print(f"[transformers-rocm] Inicializando '{model_id_or_path}' en GPU AMD...")

        try:
            self.current_model = pipeline(
                task="automatic-speech-recognition",
                model=model_id_or_path,
                torch_dtype=torch.float16,
                chunk_length_s=30,
                return_timestamps=True,
                device=0,
            )
            self.current_backend = "transformers-rocm"
            return "✅ Modelo montado correctamente.\nMotor: TRANSFORMERS (ROCm)\nDispositivo: GPU AMD\nListo."

        except Exception as e:
            self.current_model = None
            self.current_backend = None
            return f"❌ Fallo al cargar el modelo:\n{str(e)}"

    def ensure_model_loaded(self) -> bool:
        if self.current_model is not None:
            return True
        if self._last_load_args:
            print("[transformers-rocm] Restaurando modelo offloaded para continuar el lote...")
            self.load_model(*self._last_load_args)
            return self.current_model is not None
        return False

    def transcribe_raw(self, audio_path: str):
        """Generador que ejecuta la inferencia vía transformers. A
        diferencia de faster-whisper, el pipeline no transcribe por
        segmentos incrementales, así que solo hay un yield intermedio de
        estado y uno final con el resultado completo."""
        if not self.current_model:
            yield {"status": "❌ Sin modelo", "full_text": "No hay modelo inicializado.", "segments": []}
            return

        if not HAS_SOUNDFILE:
            yield {"status": "❌ Falta 'soundfile'", "full_text": "No se pudo leer el audio.", "segments": []}
            return

        yield {"status": "🧠 Procesando con transformers/ROCm...", "full_text": "", "segments": []}

        audio_np, sample_rate = sf.read(audio_path, dtype="float32")

        result = self.current_model(
            {"sampling_rate": sample_rate, "raw": audio_np},
            generate_kwargs={"task": "transcribe", "language": "es"},
        )

        full_text = result.get('text', '').strip()
        segments_data = []
        for chunk in result.get('chunks', []):
            start = chunk['timestamp'][0]
            end = chunk['timestamp'][1] if chunk['timestamp'][1] is not None else start + 3.0
            segments_data.append({'start': start, 'end': end, 'text': chunk['text']})

        yield {"status": "✅ Completado", "full_text": full_text, "segments": segments_data}
