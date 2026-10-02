"""Limpieza de audio para el procesamiento de las clases (sin DeepFilterNet)."""
import numpy as np
import pytest

from infraestructura.mejorador_audio import perfil_de_ruido

SR = 16000


def _audio(segmentos):
    """Une tramos (amplitud, segundos) de un tono: lo fuerte hace de voz, lo suave de ruido de fondo."""
    partes = []
    for amplitud, segundos in segmentos:
        t = np.arange(int(SR * segundos)) / SR
        partes.append(amplitud * np.sin(2 * np.pi * 220 * t))
    return np.concatenate(partes).astype(np.float32)


def test_el_perfil_de_ruido_no_es_el_inicio_cuando_el_profesor_ya_esta_hablando():
    """Lo que se corrigió: antes eran los primeros 0,5 s, que en una clase ya son la voz, y el filtro la borraba."""
    audio = _audio([(0.5, 10), (0.01, 3), (0.5, 10)])  # voz, un respiro con ruido de sala, voz
    perfil = perfil_de_ruido(audio, SR, 0.5)
    assert np.sqrt(np.mean(perfil ** 2)) < 0.02  # el respiro, no la voz
    assert np.sqrt(np.mean(audio[: SR // 2] ** 2)) > 0.2  # y el inicio sí era voz


def test_el_silencio_digital_exacto_no_sirve_de_perfil():
    audio = _audio([(0.5, 5), (0.0, 3), (0.01, 2), (0.5, 5)])  # un corte sin señal y, después, el ruido de la sala
    perfil = perfil_de_ruido(audio, SR, 0.5)
    assert 0.004 < np.sqrt(np.mean(perfil ** 2)) < 0.02


def test_si_todo_es_silencio_o_el_audio_es_corto_no_falla():
    assert len(perfil_de_ruido(np.zeros(SR * 5, dtype=np.float32), SR, 0.5)) == SR // 2
    corto = _audio([(0.3, 0.3)])
    assert perfil_de_ruido(corto, SR, 0.5) is corto  # más corto que la ventana: se usa tal cual


@pytest.mark.parametrize("segundos", [0.5, 1.0])
def test_la_ventana_tiene_el_largo_pedido(segundos):
    audio = _audio([(0.5, 8), (0.01, 4)])
    assert len(perfil_de_ruido(audio, SR, segundos)) == int(SR * segundos)


# --- Cómo se elige y se aplica la limpieza en el procesamiento de una clase ---------------------------

from servicios import servicio_grabacion as sg


def test_por_defecto_se_usa_light_dsp(monkeypatch):
    monkeypatch.delenv("LIMPIEZA_AUDIO", raising=False)
    assert sg.modo_de_limpieza() == "light_dsp"
    assert sg.config_de_limpieza() == {"enabled": True, "denoise_mode": "light_dsp", "normalize_input": True, "normalize_output": True, "highpass_hz": 80}


@pytest.mark.parametrize("modo", ["none", "light_dsp", "dsp", "heavy_dsp", "mmse"])
def test_se_puede_elegir_cualquiera_de_los_modos_sin_deepfilter(monkeypatch, modo):
    monkeypatch.setenv("LIMPIEZA_AUDIO", modo)
    assert sg.modo_de_limpieza() == modo
    assert sg.config_de_limpieza()["enabled"] is (modo != "none")
    assert sg.config_de_limpieza()["denoise_mode"] == modo


def test_se_acepta_mayusculas_y_espacios(monkeypatch):
    monkeypatch.setenv("LIMPIEZA_AUDIO", "  MMSE ")
    assert sg.modo_de_limpieza() == "mmse"


@pytest.mark.parametrize("pedido", ["deepfilter", "DeepFilter", "inventado", ""])
def test_deepfilter_y_los_modos_invalidos_caen_al_de_por_defecto(monkeypatch, capsys, pedido):
    """DeepFilterNet no se ofrece: pide compilar Rust y no corre en un equipo modesto. Un valor malo no tumba el procesamiento."""
    monkeypatch.setenv("LIMPIEZA_AUDIO", pedido)
    assert sg.modo_de_limpieza() == sg.LIMPIEZA_POR_DEFECTO
    assert "AVISO" in capsys.readouterr().out


def test_la_transcripcion_recibe_la_configuracion_de_limpieza(monkeypatch):
    import servicios.servicio_transcripcion as st

    recibida = []

    class MotorFalso:
        current_model = "cargado"

        def free_memory(self):
            pass

    class ServicioFalso:
        engine = MotorFalso()

        def set_enhancement_config(self, config):
            recibida.append(config)

        def load_model(self, modelo):
            pass

        def transcribe_file(self, ruta):
            yield {"status": "✅ Completado", "text": "hola", "srt": "s"}

    monkeypatch.setattr(st, "TranscriptionService", ServicioFalso)
    monkeypatch.setattr(sg, "_servicio", None)
    monkeypatch.setenv("LIMPIEZA_AUDIO", "dsp")
    assert sg.transcribir("x") == ("hola", "s")
    assert recibida == [{"enabled": True, "denoise_mode": "dsp", "normalize_input": True, "normalize_output": True, "highpass_hz": 80}]
    monkeypatch.setattr(sg, "_servicio", None)


# --- Por tramos: la memoria no puede crecer con el largo de la clase ----------------------------------

from infraestructura.mejorador_audio import por_tramos


def _ruido_y_voz(segundos, semilla=1):
    rng = np.random.default_rng(semilla)
    return (rng.standard_normal(int(SR * segundos)) * 0.1).astype(np.float32)


def test_un_audio_corto_se_procesa_de_una_vez():
    llamadas = []
    audio = _ruido_y_voz(20)
    por_tramos(lambda x: llamadas.append(len(x)) or x, audio, SR, tramo_s=30, traslape_s=2)
    assert llamadas == [len(audio)]


def test_sin_procesar_el_audio_vuelve_identico_aunque_se_parta_en_tramos():
    """Las dos rampas del empalme suman 1: partir en tramos no cambia nada por sí solo."""
    audio = _ruido_y_voz(95)
    salida = por_tramos(lambda x: x, audio, SR, tramo_s=20, traslape_s=2)
    assert len(salida) == len(audio)
    assert np.max(np.abs(salida - audio)) < 1e-5


def test_ningun_tramo_supera_el_tamano_maximo_y_se_cubre_todo_el_audio():
    """Lo que importa en un equipo modesto: el filtro nunca recibe más de tramo + traslape, dure lo que dure la clase."""
    tamanos = []
    for segundos in (45, 200, 600):
        tamanos.clear()
        audio = _ruido_y_voz(segundos)
        salida = por_tramos(lambda x: tamanos.append(len(x)) or x, audio, SR, tramo_s=30, traslape_s=2)
        assert max(tamanos) <= int(SR * 32) and len(salida) == len(audio)
    assert len(tamanos) > 15  # 600 s en tramos de 30 s


def test_el_filtro_se_aplica_a_todo_el_audio_tambien_en_los_empalmes():
    audio = _ruido_y_voz(70)
    salida = por_tramos(lambda x: x * 0.5, audio, SR, tramo_s=20, traslape_s=2)
    assert np.max(np.abs(salida - audio * 0.5)) < 1e-5  # sin saltos de volumen en los empalmes


def test_si_el_filtro_devuelve_unas_muestras_de_mas_o_de_menos_no_se_rompe():
    audio = _ruido_y_voz(70)
    sin_el_final = por_tramos(lambda x: x[:-3], audio, SR, tramo_s=20, traslape_s=2)
    con_de_mas = por_tramos(lambda x: np.concatenate([x, x[:5]]), audio, SR, tramo_s=20, traslape_s=2)
    assert len(sin_el_final) == len(audio) and len(con_de_mas) == len(audio)


def test_el_pico_de_memoria_no_depende_del_largo_del_audio():
    import tracemalloc

    def pico(segundos):
        audio = _ruido_y_voz(segundos)
        tracemalloc.start()
        por_tramos(lambda x: x * 0.5, audio, SR, tramo_s=10, traslape_s=1)
        _, maximo = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return maximo, audio.nbytes

    corto, bytes_corto = pico(60)
    largo, bytes_largo = pico(300)
    # El audio largo es 5 veces más grande, pero lo que se pide de más (salida + un tramo) crece con él una sola vez:
    # sin tramos, un filtro como el de la clase real pedía varias veces el tamaño del audio completo.
    assert largo < bytes_largo * 3
    assert largo / bytes_largo < (corto / bytes_corto) * 1.5


def test_enhance_usa_los_tramos_con_cada_modo_dsp(monkeypatch, tmp_path):
    """Que `enhance` limpie por tramos de verdad (no el archivo entero) con cada modo."""
    import soundfile as sf
    from infraestructura import mejorador_audio as ma

    ruta = tmp_path / "e.wav"
    sf.write(ruta, _ruido_y_voz(40), SR)
    for modo in ("light_dsp", "dsp", "heavy_dsp", "mmse"):
        tamanos = []
        original = ma.por_tramos

        def espia(funcion, audio, sr, _t=tamanos, _o=original):
            return _o(lambda x: _t.append(len(x)) or funcion(x), audio, sr, tramo_s=10, traslape_s=1)

        monkeypatch.setattr(ma, "por_tramos", espia)
        salida = ma.AudioEnhancer().enhance(
            str(ruta), str(tmp_path / f"s_{modo}.wav"), denoise_mode=modo, highpass_hz=0, lowpass_hz=0, normalize_input=False, normalize_output=False
        )  # sin otras etapas: solo cuenta la limpieza de ruido
        assert len(tamanos) >= 4 and max(tamanos) <= SR * 11, modo
        assert sf.info(salida).frames == SR * 40
        monkeypatch.setattr(ma, "por_tramos", original)


# --- Filtros y normalización: el mismo resultado de siempre, sin copias de más ------------------------

from scipy.signal import butter, sosfiltfilt

from infraestructura import mejorador_audio as ma


def _voz_y_graves(segundos):
    t = np.arange(int(SR * segundos)) / SR
    return (0.3 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 30 * t)).astype(np.float32)  # voz + zumbido grave


def test_rms_da_lo_mismo_que_la_formula_directa():
    audio = _ruido_y_voz(30)
    assert ma._rms(audio) == pytest.approx(float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))), rel=1e-9)
    assert ma._rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_la_normalizacion_da_lo_mismo_que_antes():
    audio = _ruido_y_voz(20)
    e = ma.AudioEnhancer()
    objetivo = 10 ** (-20 / 20.0)
    esperado = np.clip(audio * np.clip(objetivo / np.sqrt(np.mean(audio ** 2)), 0, 15), -1, 1)
    assert np.max(np.abs(e._normalize_rms(audio) - esperado)) < 1e-5
    assert np.max(np.abs(e._normalize_peak(audio) - audio / np.max(np.abs(audio)) * 0.95)) < 1e-6
    assert e._normalize_peak(audio).dtype == np.float32 and e._normalize_rms(audio).dtype == np.float32


def test_la_normalizacion_no_modifica_el_audio_de_entrada():
    audio = _ruido_y_voz(10)
    copia = audio.copy()
    ma.AudioEnhancer()._normalize_rms(audio)
    ma.AudioEnhancer()._normalize_peak(audio)
    assert np.array_equal(audio, copia)


@pytest.mark.parametrize("tipo,filtro", [("high", "_highpass_filter"), ("low", "_lowpass_filter")])
def test_los_filtros_de_frecuencia_por_tramos_dan_lo_mismo_que_sobre_el_audio_entero(monkeypatch, tipo, filtro):
    audio = _voz_y_graves(60)
    corte = 80 if tipo == "high" else 1000
    sos = butter(4, corte / (SR / 2), btype=tipo, output="sos")
    esperado = sosfiltfilt(sos, audio).astype(np.float32)
    original = ma.por_tramos
    monkeypatch.setattr(ma, "por_tramos", lambda f, a, sr: original(f, a, sr, tramo_s=10, traslape_s=2))  # forzar varios tramos
    obtenido = getattr(ma.AudioEnhancer(), filtro)(audio, SR, corte)
    assert np.max(np.abs(obtenido - esperado)) < 1e-3  # solo difiere en el borde de los tramos, y casi nada


def test_el_filtro_de_graves_realmente_quita_el_zumbido_grave():
    audio = _voz_y_graves(20)
    filtrado = ma.AudioEnhancer()._highpass_filter(audio, SR, 80)
    espectro = np.abs(np.fft.rfft(filtrado))
    f = np.fft.rfftfreq(len(filtrado), 1 / SR)
    assert espectro[np.argmin(np.abs(f - 440))] > 20 * espectro[np.argmin(np.abs(f - 30))]


def test_los_filtros_de_frecuencia_trabajan_por_tramos(monkeypatch):
    llamados = []
    original = ma.por_tramos
    monkeypatch.setattr(ma, "por_tramos", lambda f, a, sr: llamados.append(len(a)) or original(f, a, sr))
    audio = _ruido_y_voz(5)
    ma.AudioEnhancer()._highpass_filter(audio, SR, 80)
    ma.AudioEnhancer()._lowpass_filter(audio, SR, 4000)
    assert llamados == [len(audio), len(audio)]


def test_la_normalizacion_recorta_lo_que_pase_de_1():
    """Con poco volumen general y un pico, subir al nivel objetivo se pasaría de 1: se recorta, como antes."""
    audio = (np.random.default_rng(3).standard_normal(SR * 5) * 0.01).astype(np.float32)
    audio[1000] = 0.9
    salida = ma.AudioEnhancer()._normalize_rms(audio)
    assert float(np.max(np.abs(salida))) <= 1.0
    assert float(np.max(np.abs(salida))) == pytest.approx(1.0)  # el pico llegó al tope
