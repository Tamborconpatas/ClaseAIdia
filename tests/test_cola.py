"""Cola de procesamiento: orden EDF (el plazo más próximo primero), prioridad manual, lugares libres y trabajos perdidos."""
import datetime
import os
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infraestructura.basedatos import Base
from infraestructura.modelos_orm import Bloque, Clase, Colegio, ContenidoClase, Curso, EstadoGrabacion as E, Grabacion, TipoBloque
from servicios import servicio_grabacion as sg

LUNES = datetime.date(2026, 9, 28)
T = datetime.time
AHORA = datetime.datetime(2026, 9, 28, 15, 0)
_arrancar_real = sg._arrancar  # capturado al importar: conftest lo reemplaza por uno que no hace nada en cada test


class Sala:
    """Una base en archivo (varios hilos) con una carpeta de audio temporal, y una forma corta de crear clases en cola."""

    def __init__(self, tmp_path):
        self.motor = create_engine(f"sqlite:///{tmp_path / 'cola.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.motor)
        self.fabrica = sessionmaker(bind=self.motor, autoflush=False)
        with self.fabrica() as db:
            curso = Curso(nombre="8A", colegio=Colegio(nombre="C"), codigo_invitacion="ABC123")
            db.add(curso)
            db.commit()
            self.curso_id = curso.id

    def clase(self, fecha=LUNES, hora=T(8), prioritaria=False, estado=E.PROCESANDO, audio=True, transcripcion=None, **campos) -> int:
        """Devuelve el id de la grabación."""
        with self.fabrica() as db:
            bloque = Bloque(curso_id=self.curso_id, tipo=TipoBloque.CLASE, asignatura="Mate", dia_semana=fecha.weekday(), hora_inicio=hora, hora_fin=T(hora.hour + 1))
            clase = Clase(bloque=bloque, fecha=fecha, prioritaria=prioritaria)
            if transcripcion:
                clase.contenido = ContenidoClase(transcripcion_texto=transcripcion, retirado=True)
            g = Grabacion(clase=clase, estado=estado, corte_en=AHORA, trozos=1, mime="audio/webm", **campos)
            db.add(g)
            db.commit()
            if audio:
                carpeta = sg._carpeta(g.id)
                carpeta.mkdir(parents=True)
                (carpeta / "000000.parte").write_bytes(b"audio")
            return g.id

    def ver(self, grabacion_id):
        with self.fabrica() as db:
            g = db.get(Grabacion, grabacion_id)
            return g.estado, g.iniciada_en, g.error, g.intentos

    def orden(self):
        with self.fabrica() as db:
            return [g.id for g in sg.cola(db)]

    def posicion(self, grabacion_id):
        with self.fabrica() as db:
            return sg.posicion_en_cola(db, db.get(Grabacion, grabacion_id))


@pytest.fixture()
def sala(tmp_path, monkeypatch):
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    monkeypatch.setattr(sg, "ahora_utc", lambda: AHORA)
    monkeypatch.setattr(sg, "PROCESAMIENTOS_SIMULTANEOS", 1)
    sg._hilos.clear()
    s = Sala(tmp_path)
    yield s
    s.motor.dispose()
    sg._hilos.clear()


@pytest.fixture()
def arranques(monkeypatch):
    """Anota qué clase se arranca (y cómo) sin arrancar nada: sigue «en marcha» hasta que alguien la termine."""
    anotados = []
    monkeypatch.setattr(sg, "_arrancar", lambda modo, i, fabrica: anotados.append((i, modo)))
    return anotados


def terminar(sala, grabacion_id, estado=E.TERMINADA):
    with sala.fabrica() as db:
        db.get(Grabacion, grabacion_id).estado = estado
        db.commit()


# --- El plazo y el orden --------------------------------------------------------------------------


def test_el_plazo_de_una_clase_es_la_proxima_vez_que_se_dicta_ese_bloque(sala):
    g = sala.clase(fecha=LUNES, hora=T(8, 30))
    with sala.fabrica() as db:
        assert sg.fecha_limite(db.get(Grabacion, g)) == datetime.datetime(2026, 10, 5, 8, 30)  # el lunes siguiente, a la misma hora


def test_la_cola_va_por_el_plazo_mas_proximo_y_no_por_orden_de_llegada(sala):
    tarde = sala.clase(fecha=LUNES + datetime.timedelta(days=4))  # viernes: su plazo es el viernes siguiente
    lunes_9 = sala.clase(fecha=LUNES, hora=T(9))
    lunes_8 = sala.clase(fecha=LUNES, hora=T(8))
    vieja = sala.clase(fecha=LUNES - datetime.timedelta(days=20))  # lleva días esperando: su plazo ya pasó
    assert sala.orden() == [vieja, lunes_8, lunes_9, tarde]


def test_con_el_mismo_plazo_se_procesa_primero_la_que_se_grabo_antes(sala):
    primera, segunda, tercera = (sala.clase(fecha=LUNES, hora=T(8)) for _ in range(3))
    assert sala.orden() == [primera, segunda, tercera]


def test_lo_prioritario_pasa_por_delante_de_todo_y_entre_prioritarias_manda_el_plazo(sala):
    normal_urgente = sala.clase(fecha=LUNES - datetime.timedelta(days=30))
    prio_tarde = sala.clase(fecha=LUNES + datetime.timedelta(days=4), prioritaria=True)
    prio_pronto = sala.clase(fecha=LUNES, prioritaria=True)
    normal = sala.clase(fecha=LUNES)
    assert sala.orden() == [prio_pronto, prio_tarde, normal_urgente, normal]


def test_marcar_prioritaria_mientras_espera_la_adelanta(sala):
    a, b, c = (sala.clase(fecha=LUNES + datetime.timedelta(days=n)) for n in range(3))
    assert sala.orden() == [a, b, c]
    with sala.fabrica() as db:
        g = db.get(Grabacion, c)
        sg.aplicar_comando(db, g, "marcar_prioritaria")  # el profesor la marca cuando ya terminó la clase
    assert sala.orden() == [c, a, b]
    with sala.fabrica() as db:
        sg.aplicar_comando(db, db.get(Grabacion, c), "quitar_prioritaria")
    assert sala.orden() == [a, b, c]


def test_solo_cuentan_las_que_esperan_turno(sala):
    espera = sala.clase()
    sala.clase(iniciada_en=AHORA)  # ya la tomó un trabajador
    sala.clase(estado=E.ERROR)
    sala.clase(estado=E.GRABANDO)
    sala.clase(estado=E.TERMINADA)
    assert sala.orden() == [espera]


def test_el_lugar_en_la_cola(sala):
    a, b, c = (sala.clase(fecha=LUNES + datetime.timedelta(days=n)) for n in range(3))
    en_marcha = sala.clase(iniciada_en=AHORA)
    con_error = sala.clase(estado=E.ERROR)
    assert [sala.posicion(x) for x in (a, b, c)] == [1, 2, 3]
    assert sala.posicion(en_marcha) is None and sala.posicion(con_error) is None


# --- Despachar: cuántas a la vez y en qué orden ----------------------------------------------------


def test_con_un_lugar_solo_arranca_la_primera_y_las_demas_esperan(sala, arranques):
    a, b = sala.clase(fecha=LUNES), sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    sg.despachar(sala.fabrica)
    assert arranques == [(a, "clase")]
    assert sala.ver(a)[1] == AHORA and sala.ver(b)[1] is None  # la primera quedó «tomada»; la segunda sigue esperando
    sg.despachar(sala.fabrica)  # otra vez, con la primera todavía en marcha: no arranca nada más
    assert arranques == [(a, "clase")]


def test_al_terminar_la_primera_arranca_la_que_sigue(sala, arranques):
    a, b = sala.clase(fecha=LUNES), sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    sg.despachar(sala.fabrica)
    terminar(sala, a)
    sg.despachar(sala.fabrica)
    assert arranques == [(a, "clase"), (b, "clase")]


def test_una_que_falla_y_queda_en_error_tambien_libera_el_lugar(sala, arranques):
    a, b = sala.clase(fecha=LUNES), sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    sg.despachar(sala.fabrica)
    terminar(sala, a, E.ERROR)
    sg.despachar(sala.fabrica)
    assert [i for i, _ in arranques] == [a, b]


def test_con_dos_lugares_arrancan_las_dos_primeras(sala, arranques, monkeypatch):
    monkeypatch.setattr(sg, "PROCESAMIENTOS_SIMULTANEOS", 2)
    a, b, c = (sala.clase(fecha=LUNES + datetime.timedelta(days=n)) for n in range(3))
    sg.despachar(sala.fabrica)
    assert [i for i, _ in arranques] == [a, b] and sala.ver(c)[1] is None


def test_si_la_prioritaria_llega_cuando_hay_un_lugar_libre_va_primero(sala, arranques):
    normal = sala.clase(fecha=LUNES - datetime.timedelta(days=9))
    prioritaria = sala.clase(fecha=LUNES + datetime.timedelta(days=4), prioritaria=True)
    sg.despachar(sala.fabrica)
    assert [i for i, _ in arranques] == [prioritaria]
    assert sala.ver(normal)[1] is None


def test_una_prioritaria_no_interrumpe_a_la_que_ya_esta_en_marcha(sala, arranques):
    en_marcha = sala.clase(fecha=LUNES)
    sg.despachar(sala.fabrica)
    prioritaria = sala.clase(fecha=LUNES, prioritaria=True)
    sg.despachar(sala.fabrica)
    assert [i for i, _ in arranques] == [en_marcha]  # espera su turno: no se corta lo que ya se está procesando
    assert sala.posicion(prioritaria) == 1


def test_se_procesa_en_el_orden_edf_de_punta_a_punta(sala, monkeypatch):
    """Cada trabajo termina y deja pasar al siguiente, como en el servidor: el orden en que arrancan es el esperado."""
    orden = []

    def arrancar(modo, i, fabrica):
        orden.append(i)
        terminar(sala, i)

    monkeypatch.setattr(sg, "_arrancar", arrancar)
    viernes = sala.clase(fecha=LUNES + datetime.timedelta(days=4))
    lunes_9 = sala.clase(fecha=LUNES, hora=T(9))
    lunes_8 = sala.clase(fecha=LUNES, hora=T(8))
    urgente = sala.clase(fecha=LUNES + datetime.timedelta(days=4), prioritaria=True)
    sg.despachar(sala.fabrica)
    assert orden == [urgente, lunes_8, lunes_9, viernes]
    assert sala.orden() == []


def test_el_modo_sale_de_lo_que_falta_hacer(sala, arranques):
    con_audio = sala.clase(fecha=LUNES)
    solo_material = sala.clase(fecha=LUNES + datetime.timedelta(days=1), audio=False, transcripcion="Hola a todos")
    sg.despachar(sala.fabrica)
    terminar(sala, con_audio)
    sg.despachar(sala.fabrica)
    assert arranques == [(con_audio, "clase"), (solo_material, "generacion")]


def test_que_falta_hacer_con_cada_clase(sala):
    solo_audio = sala.clase()
    solo_transcripcion = sala.clase(audio=False, transcripcion="Hola")
    ambas = sala.clase(transcripcion="Hola")  # la transcripción manda: lo que falta es el material
    nada = sala.clase(audio=False)
    ya_con_material = sala.clase(audio=False, transcripcion="Hola")
    with sala.fabrica() as db:
        db.get(Grabacion, ya_con_material).clase.contenido.resumen = "Resumen"
        db.commit()
        modos = [sg._modo_de(db.get(Grabacion, i)) for i in (solo_audio, solo_transcripcion, ambas, nada, ya_con_material)]
    assert modos == ["clase", "generacion", "generacion", None, None]


def test_una_clase_sin_audio_ni_transcripcion_queda_en_error_y_la_cola_sigue(sala, arranques):
    vacia = sala.clase(fecha=LUNES, audio=False)
    buena = sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    sg.despachar(sala.fabrica)
    estado, iniciada, error, _ = sala.ver(vacia)
    assert estado == E.ERROR and iniciada is None and "hay que grabarla de nuevo" in error
    assert arranques == [(buena, "clase")]  # no se queda trabada en la que no tiene nada


def test_con_la_cola_vacia_no_pasa_nada(sala, arranques):
    sg.despachar(sala.fabrica)
    assert arranques == []


def test_dos_despachos_a_la_vez_no_arrancan_la_misma_clase_dos_veces(sala, arranques, monkeypatch):
    sala.clase()
    sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    original = sg.cola

    def lenta(db):
        resultado = original(db)
        time.sleep(0.05)  # ensancha el hueco entre mirar la cola y tomar la clase
        return resultado

    monkeypatch.setattr(sg, "cola", lenta)
    hilos = [threading.Thread(target=sg.despachar, args=(sala.fabrica,)) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert len(arranques) == 1  # un solo lugar: una sola clase


# --- Con hilos de verdad ------------------------------------------------------------------------


def _esperar(condicion, segundos=15.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    return False


def test_con_hilos_de_verdad_las_clases_se_procesan_una_tras_otra_en_orden(sala, monkeypatch):
    registro = {}

    registrados = {}

    def trabajar(modo, i, fabrica):
        inicio = time.monotonic()
        registrados[i] = i in sg._hilos  # mientras trabaja está anotado: así la vigilancia sabe que no se perdió
        time.sleep(0.3)
        terminar(sala, i)
        registro[i] = (inicio, time.monotonic())

    monkeypatch.setattr(sg, "_trabajar_aparte", trabajar)
    monkeypatch.delenv("PROCESAMIENTO_EN_HILO", raising=False)
    monkeypatch.setattr(sg, "_arrancar", _arrancar_real)
    a = sala.clase(fecha=LUNES + datetime.timedelta(days=2))
    b = sala.clase(fecha=LUNES)
    c = sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    sg.despachar(sala.fabrica)
    assert _esperar(lambda: len(registro) == 3)
    en_orden = sorted(registro, key=lambda i: registro[i][0])
    assert en_orden == [b, c, a]
    assert registrados == {a: True, b: True, c: True}
    for antes, despues in zip(en_orden, en_orden[1:]):
        assert registro[despues][0] >= registro[antes][1] - 0.02  # uno a la vez: el siguiente empieza cuando el anterior terminó
    assert _esperar(lambda: not sg._hilos)


def test_con_dos_lugares_dos_clases_se_procesan_al_mismo_tiempo(sala, monkeypatch):
    registro = {}

    def trabajar(modo, i, fabrica):
        inicio = time.monotonic()
        time.sleep(0.5)
        terminar(sala, i)
        registro[i] = (inicio, time.monotonic())

    monkeypatch.setattr(sg, "_trabajar_aparte", trabajar)
    monkeypatch.delenv("PROCESAMIENTO_EN_HILO", raising=False)
    monkeypatch.setattr(sg, "_arrancar", _arrancar_real)
    monkeypatch.setattr(sg, "PROCESAMIENTOS_SIMULTANEOS", 2)
    a, b, c = (sala.clase(fecha=LUNES + datetime.timedelta(days=n)) for n in range(3))
    sg.despachar(sala.fabrica)
    assert _esperar(lambda: len(registro) == 3)
    assert registro[b][0] < registro[a][1]  # la segunda empezó con la primera todavía en marcha
    assert registro[c][0] >= min(registro[a][1], registro[b][1]) - 0.02  # pero la tercera tuvo que esperar un lugar


# --- Trabajos perdidos -----------------------------------------------------------------------------


def test_una_clase_tomada_sin_trabajador_se_da_por_perdida_y_se_reintenta(sala):
    perdida = sala.clase(iniciada_en=AHORA - datetime.timedelta(seconds=sg.GRACIA_PERDIDO_S + 1))
    with sala.fabrica() as db:
        sg._recoger_perdidos(db, AHORA)
    estado, _, error, _ = sala.ver(perdida)
    assert estado == E.ERROR and "se interrumpió inesperadamente" in error and "Se reintentará sola" in error


def test_no_se_da_por_perdida_una_recien_tomada(sala):
    nueva = sala.clase(iniciada_en=AHORA - datetime.timedelta(seconds=sg.GRACIA_PERDIDO_S - 1))
    with sala.fabrica() as db:
        sg._recoger_perdidos(db, AHORA)
    assert sala.ver(nueva)[0] == E.PROCESANDO


def test_no_se_da_por_perdida_una_con_hilo_vivo_ni_con_trabajador_vivo(sala):
    vieja = AHORA - datetime.timedelta(hours=1)
    con_hilo = sala.clase(iniciada_en=vieja)
    con_pid = sala.clase(iniciada_en=vieja)
    parar = threading.Event()
    hilo = threading.Thread(target=parar.wait, daemon=True)
    hilo.start()
    sg._hilos[con_hilo] = hilo
    (sg._carpeta(con_pid) / "trabajador.pid").write_text(str(os.getpid()))  # un proceso que sí vive
    with sala.fabrica() as db:
        sg._recoger_perdidos(db, AHORA)
    parar.set()
    assert sala.ver(con_hilo)[0] == E.PROCESANDO and sala.ver(con_pid)[0] == E.PROCESANDO


def test_un_hilo_que_ya_termino_no_cuenta_como_vivo(sala):
    vieja = AHORA - datetime.timedelta(hours=1)
    g = sala.clase(iniciada_en=vieja)
    hilo = threading.Thread(target=lambda: None)
    hilo.start()
    hilo.join()
    sg._hilos[g] = hilo
    with sala.fabrica() as db:
        sg._recoger_perdidos(db, AHORA)
    assert sala.ver(g)[0] == E.ERROR


def test_la_vigilancia_recoge_las_perdidas_y_despacha_lo_que_esperaba(sala, arranques):
    perdida = sala.clase(fecha=LUNES, iniciada_en=AHORA - datetime.timedelta(hours=1))
    esperando = sala.clase(fecha=LUNES + datetime.timedelta(days=1))
    with sala.fabrica() as db:
        sg.vigilar(db, sala.fabrica, utc=AHORA, local=AHORA)
    assert sala.ver(perdida)[0] == E.ERROR  # liberó su lugar...
    assert arranques == [(esperando, "clase")]  # ...y la que esperaba arrancó en la misma pasada


# --- Reintentos y regeneración ---------------------------------------------------------------------


def test_un_reintento_vuelve_a_la_cola_en_su_lugar_segun_el_plazo_no_al_final(sala):
    antigua = sala.clase(fecha=LUNES - datetime.timedelta(days=10), estado=E.ERROR, intentos=1, reintento_en=AHORA - datetime.timedelta(minutes=1))
    nueva = sala.clase(fecha=LUNES)
    with sala.fabrica() as db:
        sg.vigilar(db, sala.fabrica, utc=AHORA, local=AHORA)
    estado, iniciada, error, intentos = sala.ver(antigua)
    # (el arranque real no existe en las pruebas: la pasada la dejó «tomada» por el despachador)
    assert estado == E.PROCESANDO and intentos == 2 and error is None
    assert iniciada == AHORA and sala.ver(nueva)[1] is None  # la antigua pasó primero, aunque llegó después a la cola


def test_reintentar_la_deja_esperando_turno_y_cuenta_el_intento(sala):
    g = sala.clase(estado=E.ERROR, intentos=1, reintento_en=AHORA, iniciada_en=AHORA - datetime.timedelta(hours=1), error="Falló")
    with sala.fabrica() as db:
        sg._reintentar(db, db.get(Grabacion, g))
    assert sala.ver(g) == (E.PROCESANDO, None, None, 2)  # como una clase nueva: sin trabajador, sin error, esperando su turno


def test_un_reintento_sin_audio_ni_transcripcion_no_vuelve_a_la_cola(sala, arranques):
    g = sala.clase(estado=E.ERROR, intentos=1, reintento_en=AHORA - datetime.timedelta(minutes=1), audio=False, error="Falló")
    with sala.fabrica() as db:
        sg.vigilar(db, sala.fabrica, utc=AHORA, local=AHORA)
    estado, _, error, intentos = sala.ver(g)
    assert estado == E.ERROR and intentos == 1 and "No queda audio para reintentar" in error
    assert arranques == []


def test_regenerar_pone_la_clase_en_la_cola_en_modo_generacion(sala, arranques):
    g = sala.clase(estado=E.ERROR, audio=False, transcripcion="Hola a todos", error="Ollama apagado")
    with sala.fabrica() as db:
        sg.regenerar(db, db.get(Grabacion, g), sala.fabrica)
    assert arranques == [(g, "generacion")]
    assert sala.ver(g)[0] == E.PROCESANDO


def test_terminar_de_grabar_pone_la_clase_en_la_cola(sala, arranques):
    g = sala.clase(estado=E.TERMINANDO, audio=True, iniciada_en=None)
    with sala.fabrica() as db:
        sg._iniciar_procesamiento(db, db.get(Grabacion, g), sala.fabrica)
    assert arranques == [(g, "clase")] and sala.ver(g)[0] == E.PROCESANDO
