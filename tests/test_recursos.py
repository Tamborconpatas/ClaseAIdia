# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""El servidor del colegio es un equipo modesto 24/7: el procesamiento de una clase deja un núcleo libre y, sin GPU,
transcribe con la configuración que se midió como viable (beam 1)."""
import pytest

from infraestructura import cliente_ollama, motor_whisper
from nucleo import recursos


@pytest.mark.parametrize(
    "nucleos,esperado",
    [(1, 1), (2, 1), (4, 3), (8, 7), (12, 8), (64, 8), (None, 1)],  # None: os.cpu_count() no sabe
)
def test_siempre_se_deja_un_nucleo_libre_con_un_minimo_de_uno_y_un_tope(monkeypatch, nucleos, esperado):
    monkeypatch.setattr(recursos.os, "cpu_count", lambda: nucleos)
    assert recursos.hilos_de_procesamiento() == esperado


def test_ollama_recibe_los_hilos_que_se_le_permiten(monkeypatch):
    enviados = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(cliente_ollama.requests, "post", lambda url, json, timeout: enviados.append(json) or Respuesta())
    monkeypatch.setattr(cliente_ollama, "hilos_de_procesamiento", lambda: 3)
    cliente_ollama.generate("hola", model="m", max_tokens=10)
    assert enviados[0]["options"]["num_thread"] == 3


class _ModeloFalso:
    def __init__(self):
        self.pedidos = []

    def transcribe(self, **kwargs):
        self.pedidos.append(kwargs)
        return iter([]), None


def _motor(dispositivo):
    motor = motor_whisper.WhisperEngine.__new__(motor_whisper.WhisperEngine)
    motor.device, motor.current_model, motor.current_backend, motor._last_load_args = dispositivo, _ModeloFalso(), "faster-whisper", None
    return motor


def _parametros(monkeypatch, beam=5):
    valores = {"vad_filter": True, "beam_size": beam}
    monkeypatch.setattr(motor_whisper.app_config, "get_param", lambda k: valores[k])


def test_sin_gpu_se_transcribe_con_beam_1(monkeypatch):
    """Medido: con beam 5 una clase de 90 min tardaba ~40 min en 4 núcleos; con beam 1, ~15."""
    _parametros(monkeypatch, beam=5)
    motor = _motor("cpu")
    list(motor.transcribe_raw("audio.wav"))
    assert motor.current_model.pedidos[0]["beam_size"] == 1


def test_con_gpu_grande_se_respeta_el_beam_configurado(monkeypatch):
    _parametros(monkeypatch, beam=5)
    monkeypatch.setattr(motor_whisper, "get_vram_gb", lambda: 12.0)
    motor = _motor("cuda")
    list(motor.transcribe_raw("audio.wav"))
    assert motor.current_model.pedidos[0]["beam_size"] == 5


def test_el_modelo_se_carga_con_los_hilos_permitidos(monkeypatch):
    cargados = []
    monkeypatch.setattr(motor_whisper, "WhisperModel", lambda *a, **k: cargados.append(k) or object())
    monkeypatch.setattr(motor_whisper, "HAS_FASTER_WHISPER", True)
    monkeypatch.setattr(motor_whisper, "hilos_de_procesamiento", lambda: 3)
    valores = {"compute_type": "default"}
    monkeypatch.setattr(motor_whisper.app_config, "get_param", lambda k: valores[k])
    motor = _motor("cpu")
    motor.current_model = None
    motor.load_model("small")
    assert cargados[0]["cpu_threads"] == 3 and cargados[0]["compute_type"] == "int8"
