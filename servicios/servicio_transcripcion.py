import os
import time

from nucleo import subtitulos as srt_format
from infraestructura import hardware
from infraestructura.herramientas_ffmpeg import optimize_audio_ffmpeg
from infraestructura.motor_whisper import WhisperEngine, WHISPER_MODELS

try:
    from infraestructura.mejorador_audio import AudioEnhancer
    HAS_ENHANCER = True
except ImportError:
    AudioEnhancer = None
    HAS_ENHANCER = False

try:
    from infraestructura.motor_transformers import TransformersEngine, TRANSFORMERS_WHISPER_MODELS, HAS_TRANSFORMERS
except ImportError:
    TransformersEngine = None
    TRANSFORMERS_WHISPER_MODELS = []
    HAS_TRANSFORMERS = False


def _select_engine():
    """CTranslate2 (faster-whisper) no soporta GPU AMD/ROCm, así que ahí se
    usa transformers + PyTorch; NVIDIA y CPU siguen con faster-whisper."""
    vendor = hardware.detect_gpu_vendor()
    if vendor == "amd" and HAS_TRANSFORMERS:
        return TransformersEngine()
    if vendor == "amd" and not HAS_TRANSFORMERS:
        print("⚠️ GPU AMD detectada pero 'transformers' no está instalado — usando faster-whisper en CPU.")
    return WhisperEngine()


class TranscriptionService:
    """Orquesta el caso de uso completo "transcribir un archivo de audio":
    optimización FFmpeg, limpieza de audio opcional, inferencia con el
    motor de transcripción activo (faster-whisper, o transformers en GPU
    AMD) y formateo del resultado (SRT + métricas)."""

    def __init__(self):
        self.engine = _select_engine()
        self.enhancer = AudioEnhancer() if HAS_ENHANCER else None
        self.enhancement_config = {
            'enabled': False,
            'mode': 'dsp',
            'strength': 1.5,
            'highpass_hz': 80,
            'normalize': True,
        }

    @property
    def device(self):
        return self.engine.device

    @property
    def current_backend(self):
        return self.engine.current_backend

    @property
    def engine_name(self):
        """A diferencia de `current_backend`, no depende de si ya se cargó un modelo."""
        if isinstance(self.engine, WhisperEngine):
            return "faster-whisper"
        return "transformers-rocm"

    @property
    def available_models(self):
        """Catálogo de modelos del motor activo."""
        if isinstance(self.engine, WhisperEngine):
            return WHISPER_MODELS
        return TRANSFORMERS_WHISPER_MODELS

    def load_model(self, model_id_or_path: str) -> str:
        return self.engine.load_model(model_id_or_path)

    def ensure_model_loaded(self) -> bool:
        return self.engine.ensure_model_loaded()

    def set_enhancement_config(self, config: dict):
        self.enhancement_config = config

    def _generate_metrics_html(self, wps, cps, duration, status=""):
        return f"""
        <div style='display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 15px; padding: 10px; background: transparent; border-radius: 8px; border: 1px solid rgba(148,163,184,0.14); font-family: system-ui, -apple-system, sans-serif;'>
            <div style='display: flex; align-items: center; gap: 6px;'>
                <span style='color: #8992a3; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;'>Estado:</span>
                <span style='color: #e5e7eb; font-size: 0.9em; font-weight: 500;'>{status}</span>
            </div>
            <div style='height: 15px; width: 1px; background: rgba(148,163,184,0.14);'></div>
            <div style='display: flex; gap: 8px;'>
                <div style='background: rgba(148,163,184,0.08); color: #e5e7eb; padding: 4px 12px; border-radius: 6px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(148,163,184,0.14);'>
                    {wps:.1f} pal/s
                </div>
                <div style='background: rgba(148,163,184,0.08); color: #e5e7eb; padding: 4px 12px; border-radius: 6px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(148,163,184,0.14);'>
                    {cps:.1f} car/s
                </div>
                <div style='background: rgba(148,163,184,0.08); color: #e5e7eb; padding: 4px 12px; border-radius: 6px; font-size: 0.85em; font-weight: 600; border: 1px solid rgba(148,163,184,0.14);'>
                    {duration:.1f}s
                </div>
            </div>
        </div>
        """

    def transcribe_file(self, audio_path: str, language=None):
        """Generador que transcribe un archivo de audio de principio a fin,
        reportando progreso. Yields dicts con status/text/srt/segments/metrics_html."""
        if not os.path.exists(audio_path):
            yield {"status": "❌ Error E/S", "text": f"Error: No se encuentra '{audio_path}'.", "srt": "", "metrics_html": ""}
            return

        yield {"status": f"💽 Convirtiendo y comprimiendo a 16kHz mono...", "text": "", "srt": "", "metrics_html": ""}
        optimized_path = optimize_audio_ffmpeg(audio_path)

        if not self.ensure_model_loaded():
            yield {"status": "❌ Sin modelo", "text": "El modelo de transcripción no está cargado y no se pudo restaurar.", "srt": "", "metrics_html": ""}
            return

        enhanced_path = optimized_path
        _enhanced_temp = None
        cfg = self.enhancement_config
        if cfg.get('enabled') and self.enhancer:
            try:
                mode = cfg.get('denoise_mode', 'dsp')
                yield {"status": f"✨ Limpiando audio ({mode})...", "text": "", "srt": "", "metrics_html": ""}
                print(f"[Transcriptor] Aplicando limpieza de audio (modo: {mode.upper()})...")
                enhanced_path = self.enhancer.enhance(
                    input_path=optimized_path,
                    output_path=None,
                    denoise_mode=mode,
                    denoise_strength=float(cfg.get('denoise_strength', 1.5)),
                    highpass_hz=int(cfg.get('highpass_hz', 80)),
                    lowpass_hz=int(cfg.get('lowpass_hz', 0)),
                    normalize_input=cfg.get('normalize_input', True),
                    normalize_output=cfg.get('normalize_output', True),
                    voice_boost_db=float(cfg.get('voice_boost_db', 0.0)),
                    voice_boost_low_hz=int(cfg.get('voice_boost_low_hz', 800)),
                    voice_boost_high_hz=int(cfg.get('voice_boost_high_hz', 4000)),
                    use_compressor=cfg.get('use_compressor', False),
                    compressor_threshold_db=float(cfg.get('compressor_threshold_db', -20.0)),
                    compressor_ratio=float(cfg.get('compressor_ratio', 3.0)),
                )
                _enhanced_temp = enhanced_path if enhanced_path != optimized_path else None
            except Exception as enh_err:
                print(f"[Transcriptor] ⚠️ Limpieza falló: {enh_err}")
                enhanced_path = optimized_path

        try:
            full_text = ""
            segments_data = []
            start_time = time.time()

            def calculate_metrics():
                elapsed = time.time() - start_time
                if elapsed <= 0:
                    return 0.0, 0.0, 0.0
                words = len(full_text.split())
                chars = len(full_text)
                return words / elapsed, chars / elapsed, elapsed

            yield {"status": "🎬 Iniciando IA...", "text": "", "srt": "", "metrics_html": self._generate_metrics_html(0, 0, 0, "Cargando audio...")}

            for update in self.engine.transcribe_raw(enhanced_path):
                full_text = update["full_text"]
                segments_data = update["segments"]
                wps, cps, dur = calculate_metrics()
                yield {
                    "status": update["status"],
                    "text": full_text,
                    "srt": "",
                    "segments": segments_data,
                    "metrics_html": self._generate_metrics_html(wps, cps, dur, "Whisper Activo")
                }

            final_srt = srt_format.format_srt(segments_data)
            wps, cps, dur = calculate_metrics()
            yield {
                "status": "✅ Completado",
                "text": full_text.strip(),
                "srt": final_srt,
                "segments": segments_data,
                "metrics_html": self._generate_metrics_html(wps, cps, dur, "Finalizado satisfactoriamente")
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"status": "❌ Error Fatal", "text": f"Error: {str(e)}", "srt": "", "metrics_html": ""}
        finally:
            if _enhanced_temp and os.path.exists(_enhanced_temp):
                try:
                    os.remove(_enhanced_temp)
                except Exception:
                    pass
            if optimized_path != audio_path and os.path.exists(optimized_path):
                try:
                    os.remove(optimized_path)
                except Exception:
                    pass
