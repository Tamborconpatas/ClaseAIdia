"""Whisper transcribe la clase por tramos: la memoria no puede depender de cuánto dura (con 92 minutos de una vez el
proceso llegó a 6,1 GB, y en un equipo modesto con el resto del sistema eso agota la memoria)."""
import numpy as np
import pytest
import soundfile as sf

from infraestructura import motor_whisper as mw

SR = 16000


def _wav(ruta, segundos, silencios=()):
    """Un tono (la 'voz') con silencios en los tramos (inicio_s, fin_s) indicados."""
    t = np.arange(int(SR * segundos)) / SR
    audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for a, b in silencios:
        audio[int(a * SR):int(b * SR)] = 0.001 * np.random.default_rng(1).standard_normal(int(b * SR) - int(a * SR)).astype(np.float32)
    sf.write(ruta, audio, SR)
    return ruta


class _Segmento:
    def __init__(self, inicio, fin, texto):
        self.start, self.end, self.text = inicio, fin, texto


class _ModeloFalso:
    """Anota lo que recibe y devuelve un segmento de 1 s por tramo, con tiempos relativos al tramo."""

    def __init__(self):
        self.pedidos = []

    def transcribe(self, **kwargs):
        self.pedidos.append(kwargs)
        n = len(self.pedidos)
        return iter([_Segmento(0.0, 1.0, f"texto{n}")]), None


def _motor(modelo=None, dispositivo="cpu"):
    motor = mw.WhisperEngine.__new__(mw.WhisperEngine)
    motor.device, motor.current_model, motor.current_backend, motor._last_load_args = dispositivo, modelo or _ModeloFalso(), "faster-whisper", None
    return motor


@pytest.fixture(autouse=True)
def _configuracion(monkeypatch):
    valores = {"vad_filter": True, "beam_size": 5}
    monkeypatch.setattr(mw.app_config, "get_param", lambda k: valores[k])


def _transcribir(motor, ruta):
    ultimo = None
    for ultimo in motor.transcribe_raw(str(ruta)):
        pass
    return ultimo


def test_un_audio_corto_se_transcribe_entero_como_siempre(tmp_path):
    ruta = _wav(tmp_path / "corto.wav", 60)
    motor = _motor()
    resultado = _transcribir(motor, ruta)
    assert len(motor.current_model.pedidos) == 1
    assert motor.current_model.pedidos[0]["audio"] == str(ruta)  # la ruta, no un arreglo: el camino de antes
    assert resultado["segments"] == [{"start": 0.0, "end": 1.0, "text": "texto1"}]


def test_un_audio_largo_se_parte_en_tramos_que_cubren_todo(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    ruta = _wav(tmp_path / "largo.wav", 100)
    motor = _motor()
    _transcribir(motor, ruta)
    pedidos = motor.current_model.pedidos
    assert len(pedidos) >= 4
    assert sum(len(p["audio"]) for p in pedidos) == 100 * SR  # ninguna muestra se pierde ni se repite
    assert all(isinstance(p["audio"], np.ndarray) and p["audio"].dtype == np.float32 for p in pedidos)
    assert max(len(p["audio"]) for p in pedidos) <= 31 * SR  # el máximo: 1,5 tramos antes de partir


def test_los_tiempos_de_cada_tramo_se_corrigen_para_que_los_subtitulos_sigan_alineados(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    ruta = _wav(tmp_path / "largo.wav", 100)
    motor = _motor()
    resultado = _transcribir(motor, ruta)
    inicios = [s["start"] for s in resultado["segments"]]
    assert inicios == sorted(inicios) and inicios[0] == 0.0
    assert len(set(inicios)) == len(inicios)
    assert all(abs(inicios[i + 1] - inicios[i] - 20) < 16 for i in range(len(inicios) - 1))  # un tramo después, no todos en 0
    assert [s["text"] for s in resultado["segments"]] == [f"texto{i + 1}" for i in range(len(inicios))]
    assert resultado["full_text"].startswith("texto1 texto2")


def test_el_corte_cae_en_el_momento_mas_silencioso_cerca_del_limite(tmp_path, monkeypatch):
    """No se parte una palabra por la mitad: hay un silencio a 17-18 s y el límite es 20 s."""
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    ruta = _wav(tmp_path / "con_silencio.wav", 70, silencios=[(17.0, 18.0)])
    with sf.SoundFile(ruta) as archivo:
        cortes = mw.cortes_de_audio(archivo, 20)
    assert 17 * SR <= cortes[1] <= 18 * SR
    assert cortes[0] == 0 and cortes[-1] == 70 * SR
    assert cortes == sorted(cortes)


def test_el_final_no_queda_en_un_tramo_diminuto(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    ruta = _wav(tmp_path / "x.wav", 41)  # 41 s: dos tramos de ~20 y un resto de 1 s no deben salir
    with sf.SoundFile(ruta) as archivo:
        cortes = mw.cortes_de_audio(archivo, 20)
    largos = [b - a for a, b in zip(cortes, cortes[1:])]
    assert min(largos) >= 10 * SR


def test_cada_tramo_sigue_el_hilo_del_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    ruta = _wav(tmp_path / "largo.wav", 100)
    motor = _motor()
    _transcribir(motor, ruta)
    pedidos = motor.current_model.pedidos
    assert "initial_prompt" not in pedidos[0]
    assert pedidos[1]["initial_prompt"] == "texto1" and pedidos[2]["initial_prompt"].endswith("texto2")


def test_sin_contexto_entre_tramos_cuando_esta_desactivado(tmp_path, monkeypatch):
    """La GPU chica fuerza condition_on_previous_text=False: no se mete un prompt por la puerta de atrás."""
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    monkeypatch.setattr(mw, "get_vram_gb", lambda: 4.0)
    ruta = _wav(tmp_path / "largo.wav", 100)
    motor = _motor(dispositivo="cuda")
    _transcribir(motor, ruta)
    assert all("initial_prompt" not in p for p in motor.current_model.pedidos)


def test_un_archivo_que_no_es_wav_de_16khz_mono_se_transcribe_entero(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    estereo = tmp_path / "estereo.wav"
    sf.write(estereo, np.zeros((SR * 100, 2), dtype=np.float32), SR)
    otro = tmp_path / "44k.wav"
    sf.write(otro, np.zeros(44100 * 100, dtype=np.float32), 44100)
    for ruta in (estereo, otro, tmp_path / "no_existe.wav"):
        motor = _motor()
        _transcribir(motor, ruta)
        assert len(motor.current_model.pedidos) == 1 and motor.current_model.pedidos[0]["audio"] == str(ruta), ruta.name


def test_el_modo_seguro_por_falta_de_memoria_de_gpu_tambien_corrige_los_tiempos(tmp_path, monkeypatch):
    monkeypatch.setattr(mw, "TRAMO_TRANSCRIPCION_S", 20)
    monkeypatch.setattr(mw, "get_vram_gb", lambda: 12.0)

    class SinMemoriaLaPrimeraVez(_ModeloFalso):
        def transcribe(self, **kwargs):
            self.pedidos.append(kwargs)
            if len(self.pedidos) == 2:  # el segundo tramo (el primero tiene desplazamiento 0 y no probaría nada)
                raise RuntimeError("CUDA out of memory")
            return iter([_Segmento(0.0, 1.0, f"texto{len(self.pedidos)}")]), None

    ruta = _wav(tmp_path / "largo.wav", 100)
    motor = _motor(SinMemoriaLaPrimeraVez(), dispositivo="cuda")
    resultado = _transcribir(motor, ruta)
    assert motor.current_model.pedidos[2]["beam_size"] == 1  # reintento en modo seguro del segundo tramo
    inicios = [seg["start"] for seg in resultado["segments"]]
    assert inicios[0] == 0.0 and inicios[1] > 5 and inicios == sorted(inicios)  # el reintento también va desplazado


def _wav_con_ceros(ruta, segundos, silencios):
    t = np.arange(int(SR * segundos)) / SR
    audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    for a, b in silencios:
        audio[int(a * SR):int(b * SR)] = 0.0
    sf.write(ruta, audio, SR)
    return ruta


def test_entre_dos_silencios_igual_de_buenos_se_corta_en_el_mas_cercano_al_limite(tmp_path):
    """Si no, los tramos quedarían de largo impredecible (y a veces diminutos)."""
    ruta = _wav_con_ceros(tmp_path / "dos.wav", 70, silencios=[(15.5, 16.0), (19.8, 20.2)])  # límite en 20 s
    with sf.SoundFile(ruta) as archivo:
        cortes = mw.cortes_de_audio(archivo, 20)
    assert 19.8 * SR <= cortes[1] <= 20.2 * SR


def test_un_silencio_demasiado_lejos_del_limite_no_se_usa(tmp_path):
    """Con tramos de 20 s, la búsqueda llega a 5 s del límite: un silencio a 11 s de distancia haría un primer tramo de 8 s."""
    ruta = _wav_con_ceros(tmp_path / "lejos.wav", 70, silencios=[(8.0, 9.0)])
    with sf.SoundFile(ruta) as archivo:
        cortes = mw.cortes_de_audio(archivo, 20)
    assert 15 * SR <= cortes[1] <= 25 * SR
