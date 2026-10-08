"""Si CUDA no se puede usar (falta libcublas, el driver no calza...), la clase se transcribe en la CPU en vez de perderse."""
import numpy as np
import pytest
import soundfile as sf

from infraestructura import motor_whisper as mw

SR = 16000
ERROR_CUBLAS = "Library libcublas.so.12 is not found or cannot be loaded"


class _Segmento:
    def __init__(self, inicio, fin, texto):
        self.start, self.end, self.text = inicio, fin, texto


class _Modelo:
    def __init__(self, falla=None):
        self.falla, self.pedidos = falla, []

    def transcribe(self, **kwargs):
        self.pedidos.append(kwargs)
        if self.falla:
            raise RuntimeError(self.falla)
        return iter([_Segmento(0.0, 1.0, "hola")]), None


@pytest.fixture(autouse=True)
def _configuracion(monkeypatch):
    valores = {"vad_filter": True, "beam_size": 5, "compute_type": "default"}
    monkeypatch.setattr(mw.app_config, "get_param", lambda k: valores[k])
    monkeypatch.setattr(mw, "get_vram_gb", lambda: 4.0)


def _wav(ruta):
    sf.write(ruta, (0.3 * np.sin(2 * np.pi * 220 * np.arange(SR * 2) / SR)).astype(np.float32), SR)
    return str(ruta)


def _motor(modelo, dispositivo="cuda"):
    motor = mw.WhisperEngine.__new__(mw.WhisperEngine)
    motor.device, motor.current_model, motor.current_backend, motor._last_load_args = dispositivo, modelo, "faster-whisper", ("small",)
    return motor


def _transcribir(motor, ruta):
    ultimo = None
    for ultimo in motor.transcribe_raw(ruta):
        pass
    return ultimo


@pytest.mark.parametrize("mensaje", [ERROR_CUBLAS, "Library libcudnn_ops.so.9 is not found", "CUDA driver version is insufficient for CUDA runtime version", "no CUDA-capable device is detected", "cublas failed"])
def test_si_falla_cuda_al_transcribir_se_sigue_en_la_cpu(monkeypatch, tmp_path, mensaje):
    cpu = _Modelo()
    motor = _motor(_Modelo(falla=mensaje))
    monkeypatch.setattr(motor, "load_model", lambda *a: setattr(motor, "current_model", cpu) or "ok")
    resultado = _transcribir(motor, _wav(tmp_path / "a.wav"))
    assert motor.device == "cpu" and resultado["full_text"] == "hola"
    assert cpu.pedidos[0]["beam_size"] == 1  # en CPU, el ajuste rápido de siempre


def test_despues_del_cambio_las_clases_siguientes_ya_van_directo_a_la_cpu(monkeypatch, tmp_path):
    cpu = _Modelo()
    motor = _motor(_Modelo(falla=ERROR_CUBLAS))
    monkeypatch.setattr(motor, "load_model", lambda *a: setattr(motor, "current_model", cpu) or "ok")
    _transcribir(motor, _wav(tmp_path / "a.wav"))
    _transcribir(motor, _wav(tmp_path / "b.wav"))
    assert len(cpu.pedidos) == 2 and motor.device == "cpu"


def test_si_tampoco_se_puede_cargar_en_la_cpu_el_error_es_claro(monkeypatch, tmp_path):
    motor = _motor(_Modelo(falla=ERROR_CUBLAS))
    monkeypatch.setattr(motor, "load_model", lambda *a: setattr(motor, "current_model", None) or "falló")
    with pytest.raises(RuntimeError, match="ni cargar el modelo en la CPU"):
        _transcribir(motor, _wav(tmp_path / "a.wav"))


def test_un_error_que_no_es_de_cuda_se_sigue_propagando(monkeypatch, tmp_path):
    motor = _motor(_Modelo(falla="archivo de audio corrupto"))
    with pytest.raises(RuntimeError, match="corrupto"):
        _transcribir(motor, _wav(tmp_path / "a.wav"))
    assert motor.device == "cuda"


def test_la_falta_de_memoria_sigue_con_su_propio_reintento_y_no_pasa_a_la_cpu(monkeypatch, tmp_path):
    class SinMemoria(_Modelo):
        def transcribe(self, **kwargs):
            self.pedidos.append(kwargs)
            if len(self.pedidos) == 1:
                raise RuntimeError("CUDA out of memory")
            return iter([_Segmento(0.0, 1.0, "hola")]), None

    motor = _motor(SinMemoria())
    assert _transcribir(motor, _wav(tmp_path / "a.wav"))["full_text"] == "hola"
    assert motor.device == "cuda"


def test_si_falla_cuda_al_cargar_el_modelo_se_carga_en_la_cpu(monkeypatch):
    llamadas = []

    def modelo(id_, device, compute_type, cpu_threads=None):
        llamadas.append((device, compute_type))
        if device == "cuda":
            raise RuntimeError(ERROR_CUBLAS)
        return _Modelo()

    monkeypatch.setattr(mw, "WhisperModel", modelo)
    monkeypatch.setattr(mw, "HAS_FASTER_WHISPER", True)
    motor = _motor(None)
    mensaje = motor.load_model("small")
    assert llamadas == [("cuda", "int8"), ("cpu", "int8")] and motor.device == "cpu" and motor.current_model is not None
    assert mensaje.startswith("✅")


@pytest.mark.parametrize("mensaje,esperado", [
    (ERROR_CUBLAS, True), ("CUDA driver version is insufficient", True), ("libcudnn missing", True), ("CUDA out of memory", False),
    ("Out of memory", False), ("archivo corrupto", False), ("", False),
])
def test_es_falla_de_cuda(mensaje, esperado):
    assert mw.es_falla_de_cuda(RuntimeError(mensaje)) is esperado
