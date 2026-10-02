"""El procesamiento de una clase corre en un proceso aparte con tope de memoria: si se pasa, cae solo él, no el servidor."""
import datetime
import os
import subprocess
import sys
import threading
import time

import pytest
from sqlalchemy.orm import sessionmaker

from infraestructura.modelos_orm import Bloque, Clase, Colegio, ContenidoClase, Curso, EstadoGrabacion as E, Grabacion, TipoBloque
from servicios import servicio_grabacion as sg
from servicios import trabajador

RAIZ = sg.RAIZ_DEL_PROYECTO


@pytest.fixture(autouse=True)
def _detener_los_vigilantes(monkeypatch):
    """Un vigilante que queda vivo al terminar el test sigue imprimiendo en segundo plano y, al cerrar el intérprete,
    provoca un error fatal: cada test que arma uno lo detiene al terminar."""
    armados = []
    original = trabajador.vigilar_memoria

    def armar(*a, **k):
        hilo = original(*a, **k)
        armados.append(hilo)
        return hilo

    monkeypatch.setattr(trabajador, "vigilar_memoria", armar)
    yield
    for hilo in armados:
        hilo.detener.set()
        hilo.join(timeout=2)
        assert not hilo.is_alive()


# --- El tope y el vigilante --------------------------------------------------------------------


@pytest.mark.parametrize(
    "total,esperado",
    [(8.0, 4.8), (16.0, 8.0), (64.0, 8.0), (4.0, 2.4), (None, 6.0)],  # 60 % de la RAM, con máximo de 8 GB
)
def test_el_tope_es_el_60_por_ciento_de_la_ram_con_maximo(monkeypatch, total, esperado):
    monkeypatch.delenv("LIMITE_MEMORIA_PROCESAMIENTO_GB", raising=False)
    monkeypatch.setattr(trabajador, "memoria_total_gb", lambda: total)
    assert trabajador.limite_de_memoria_gb() == pytest.approx(esperado)


def test_el_tope_se_puede_fijar_a_mano_y_un_valor_malo_se_ignora(monkeypatch):
    monkeypatch.setattr(trabajador, "memoria_total_gb", lambda: 16.0)
    monkeypatch.setenv("LIMITE_MEMORIA_PROCESAMIENTO_GB", "3.5")
    assert trabajador.limite_de_memoria_gb() == 3.5
    for malo in ("abc", "0", "-2", ""):
        monkeypatch.setenv("LIMITE_MEMORIA_PROCESAMIENTO_GB", malo)
        assert trabajador.limite_de_memoria_gb() == 8.0, malo


def _esperar(condicion, segundos=3.0):
    limite = time.time() + segundos
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_el_vigilante_corta_el_proceso_con_el_codigo_de_sin_memoria_cuando_se_pasa():
    salidas, usos = [], iter([1.0, 2.0, 5.0, 5.0, 5.0])
    trabajador.vigilar_memoria(3.0, intervalo_s=0.01, leer=lambda: next(usos, 5.0), salir=salidas.append)
    assert _esperar(lambda: salidas)
    assert salidas[0] == trabajador.CODIGO_SIN_MEMORIA == 75


def test_despues_de_cortar_el_vigilante_termina_y_no_repite_el_aviso(capsys):
    """Antes seguía vivo imprimiendo sin parar, y al cerrar el intérprete eso provocaba un error fatal."""
    salidas = []
    hilo = trabajador.vigilar_memoria(1.0, intervalo_s=0.01, leer=lambda: 9.0, salir=salidas.append)
    hilo.join(timeout=3)
    assert not hilo.is_alive() and salidas == [75]
    assert capsys.readouterr().out.count("AVISO") == 1


def test_un_vigilante_se_puede_detener():
    hilo = trabajador.vigilar_memoria(1.0, intervalo_s=0.01, leer=lambda: 0.5, salir=lambda c: None)
    assert hilo.is_alive()
    hilo.detener.set()
    hilo.join(timeout=3)
    assert not hilo.is_alive()


def test_el_vigilante_no_hace_nada_mientras_el_uso_esta_bajo_el_tope():
    salidas = []
    trabajador.vigilar_memoria(3.0, intervalo_s=0.01, leer=lambda: 3.0, salir=salidas.append)  # justo en el tope: no se pasa
    time.sleep(0.2)
    assert salidas == []


def test_una_lectura_que_falla_no_mata_al_vigilante_y_sigue_cuidando():
    """Si una lectura sin dato hiciera caer su hilo, el vigilante dejaría de proteger sin avisar."""
    salidas, lecturas = [], iter([None, None, None, 5.0])
    trabajador.vigilar_memoria(3.0, intervalo_s=0.01, leer=lambda: next(lecturas, 5.0), salir=salidas.append)
    assert _esperar(lambda: salidas)
    assert salidas[0] == trabajador.CODIGO_SIN_MEMORIA


def test_el_trabajador_arma_su_vigilante_con_el_tope_y_procesa_lo_pedido(monkeypatch):
    llamadas = []
    monkeypatch.setattr(trabajador, "vigilar_memoria", lambda limite: llamadas.append(("vigilante", limite)))
    monkeypatch.setattr(trabajador, "limite_de_memoria_gb", lambda: 4.8)
    monkeypatch.setattr(sg, "procesar", lambda gid, fabrica: llamadas.append(("clase", gid)))
    monkeypatch.setattr(sg, "procesar_generacion", lambda gid, fabrica: llamadas.append(("generacion", gid)))
    assert trabajador.main(["clase", "5"]) == 0
    assert trabajador.main(["generacion", "6"]) == 0
    assert llamadas == [("vigilante", 4.8), ("clase", 5), ("vigilante", 4.8), ("generacion", 6)]


def test_de_verdad_un_proceso_que_se_pasa_del_tope_sale_con_codigo_75():
    """Sin simulaciones: un proceso real con un tope diminuto se corta solo con el código que el servidor reconoce."""
    codigo = (
        "import time; from servicios.trabajador import vigilar_memoria; "
        "vigilar_memoria(0.001, intervalo_s=0.05); time.sleep(30)"
    )
    t0 = time.time()
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert resultado.returncode == 75
    assert time.time() - t0 < 25  # se cortó mucho antes de los 30 s del sueño
    assert "se corta para no agotar la memoria" in resultado.stdout


def test_el_trabajador_rechaza_argumentos_malos_sin_cargar_nada_pesado(capsys):
    for malo in ([], ["clase"], ["otro", "3"], ["clase", "abc"], ["clase", "3", "4"]):
        assert trabajador.main(malo) == 2, malo
    assert "uso:" in capsys.readouterr().err


# --- El servidor lanza el trabajador y se entera de cómo terminó -------------------------------


@pytest.fixture()
def sesion_procesando(sesion_db, monkeypatch, tmp_path):
    """Una grabación PROCESANDO con audio en disco, y la fábrica de sesiones para consultarla."""
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    colegio = Colegio(nombre="C")
    curso = Curso(nombre="8A", colegio=colegio, codigo_invitacion="ABC123")
    bloque = Bloque(curso=curso, tipo=TipoBloque.CLASE, asignatura="Mate", dia_semana=0, hora_inicio=datetime.time(8), hora_fin=datetime.time(9))
    clase = Clase(bloque=bloque, fecha=datetime.date(2026, 9, 28))
    grabacion = Grabacion(clase=clase, estado=E.PROCESANDO, corte_en=datetime.datetime(2026, 9, 28, 9, 15), trozos=1, mime="audio/webm")
    sesion_db.add(grabacion)
    sesion_db.commit()
    carpeta = sg._carpeta(grabacion.id)
    carpeta.mkdir(parents=True)
    (carpeta / "000000.parte").write_bytes(b"audio")
    fabrica = sessionmaker(bind=sesion_db.get_bind(), autoflush=False)
    return {"id": grabacion.id, "fabrica": fabrica, "carpeta": carpeta, "db": sesion_db}


def _estado(s):
    with s["fabrica"]() as db:
        g = db.get(Grabacion, s["id"])
        return g.estado, g.error


def _con_hijo(monkeypatch, codigo_python):
    monkeypatch.setattr(sg, "COMANDO_TRABAJADOR", [sys.executable, "-c", codigo_python])
    monkeypatch.setattr(sg, "esperar_memoria", lambda *a, **k: True)


def test_si_el_trabajador_termina_bien_el_servidor_no_toca_el_resultado(sesion_procesando, monkeypatch):
    _con_hijo(monkeypatch, "import sys; sys.exit(0)")
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert _estado(sesion_procesando)[0] == E.PROCESANDO  # el trabajador es quien deja TERMINADA; este de mentira no lo hace
    assert not sesion_procesando["carpeta"].exists()  # y el audio ya no existe


def test_si_el_trabajador_se_pasa_de_memoria_la_clase_queda_en_error_con_el_motivo_y_se_reintenta_sola(sesion_procesando, monkeypatch):
    _con_hijo(monkeypatch, "import sys; sys.exit(75)")
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and error.startswith(sg.MENSAJE_SIN_MEMORIA) and "Se reintentará sola" in error
    assert sesion_procesando["carpeta"].exists()  # el audio se conserva: el reintento lo necesita


def test_si_el_sistema_mata_al_trabajador_tambien_queda_en_error_y_se_reintenta_sola(sesion_procesando, monkeypatch):
    _con_hijo(monkeypatch, "import sys; sys.exit(137)")  # lo que ve el servidor si el sistema cierra el proceso
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and "137" in error and "interrumpió" in error and "Se reintentará sola" in error
    assert sesion_procesando["carpeta"].exists()


def test_el_servidor_no_pisa_un_resultado_que_el_trabajador_ya_dejo(sesion_procesando, monkeypatch):
    """Si el trabajador alcanzó a dejar la clase terminada y recién después salió con error, no se la pasa a error."""
    with sesion_procesando["fabrica"]() as db:
        db.get(Grabacion, sesion_procesando["id"]).estado = E.TERMINADA
        db.commit()
    _con_hijo(monkeypatch, "import sys; sys.exit(1)")
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert _estado(sesion_procesando)[0] == E.TERMINADA


def test_un_procesamiento_atascado_se_cancela_y_el_proceso_muere_pasado_el_tiempo_maximo(sesion_procesando, monkeypatch, tmp_path):
    pid_hijo = tmp_path / "pid.txt"
    _con_hijo(monkeypatch, f"import os, time; open(r'{pid_hijo}', 'w').write(str(os.getpid())); time.sleep(60)")
    monkeypatch.setattr(sg, "TIEMPO_MAXIMO_S", 1.5)
    t0 = time.time()
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert time.time() - t0 < 20  # no esperó el minuto del hijo
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and "tardó más" in error
    assert not sg._proceso_vivo(int(pid_hijo.read_text()))  # el proceso atascado ya no está consumiendo memoria ni CPU


def test_sin_memoria_libre_ni_siquiera_se_lanza_el_trabajador(sesion_procesando, monkeypatch):
    lanzados = []
    monkeypatch.setattr(sg.subprocess, "Popen", lambda *a, **k: lanzados.append(a) or pytest.fail("no debía lanzarse"))
    monkeypatch.setattr(sg, "esperar_memoria", lambda minimo, espera: False)
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert lanzados == []
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and error.startswith(sg.MENSAJE_SIN_MEMORIA) and "Se reintentará sola" in error
    assert sesion_procesando["carpeta"].exists()


def test_la_espera_de_memoria_usa_el_minimo_y_el_tiempo_configurados(sesion_procesando, monkeypatch):
    pedido = []
    _con_hijo(monkeypatch, "import sys; sys.exit(0)")
    monkeypatch.setattr(sg, "esperar_memoria", lambda minimo, espera: pedido.append((minimo, espera)) or True)
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert pedido == [(sg.MEMORIA_MINIMA_GB, sg.ESPERA_MEMORIA_S)] and sg.MEMORIA_MINIMA_GB >= 2


def test_si_no_se_puede_lanzar_el_trabajador_la_clase_queda_en_error(sesion_procesando, monkeypatch):
    monkeypatch.setattr(sg, "COMANDO_TRABAJADOR", ["/no/existe/este_programa"])
    monkeypatch.setattr(sg, "esperar_memoria", lambda *a, **k: True)
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and "No se pudo iniciar" in error and "Se reintentará sola" in error
    assert sesion_procesando["carpeta"].exists()


def test_el_trabajador_recibe_el_modo_y_el_id(sesion_procesando, monkeypatch, tmp_path):
    salida = tmp_path / "argumentos.txt"
    _con_hijo(monkeypatch, f"import sys; open(r'{salida}', 'w').write(' '.join(sys.argv[1:]))")
    sg._trabajar_aparte("generacion", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert salida.read_text() == f"generacion {sesion_procesando['id']}"


def test_regenerar_no_borra_el_audio_porque_no_hay_audio_pero_si_la_transcripcion(sesion_procesando, monkeypatch):
    _con_hijo(monkeypatch, "import sys; sys.exit(0)")
    sg._trabajar_aparte("generacion", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert sesion_procesando["carpeta"].exists()  # el modo «generacion» no toca la carpeta (otro flujo la maneja)


def test_se_procesa_una_clase_a_la_vez_aunque_lleguen_dos(sesion_procesando, monkeypatch, tmp_path):
    registro = tmp_path / "registro.txt"
    _con_hijo(monkeypatch, f"import time; a = time.time(); time.sleep(0.8); open(r'{registro}', 'a').write(f'{{a}} {{time.time()}}\\n')")
    hilos = [threading.Thread(target=sg._trabajar_aparte, args=("clase", sesion_procesando["id"], sesion_procesando["fabrica"])) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    (a1, b1), (a2, b2) = sorted(tuple(map(float, linea.split())) for linea in registro.read_text().splitlines())
    assert a2 >= b1 - 0.05  # el segundo empezó cuando el primero ya había terminado


# --- Cómo se elige dónde correr ------------------------------------------------------------------


def test_por_defecto_el_procesamiento_va_a_un_proceso_aparte(monkeypatch):
    llamados = []
    monkeypatch.delenv("PROCESAMIENTO_EN_HILO", raising=False)
    monkeypatch.setattr(sg, "_trabajar_aparte", lambda *a: llamados.append(a))
    sg._lanzar(sg.procesar, 7, "fabrica")
    sg._lanzar(sg.procesar_generacion, 8, "fabrica")
    assert _esperar(lambda: len(llamados) == 2)
    assert sorted(llamados) == [("clase", 7, "fabrica"), ("generacion", 8, "fabrica")]


def test_en_desarrollo_se_puede_procesar_en_un_hilo(monkeypatch):
    llamados = []
    monkeypatch.setenv("PROCESAMIENTO_EN_HILO", "1")
    monkeypatch.setattr(sg, "_trabajar_aparte", lambda *a: pytest.fail("no debía usar el proceso aparte"))
    sg._lanzar(lambda *a: llamados.append(a), 7, "fabrica")
    assert _esperar(lambda: llamados == [(7, "fabrica")])


# --- Un reinicio del servidor (por ejemplo un corte de luz) no pierde la clase -------------------


def test_tras_un_reinicio_una_clase_con_audio_en_disco_se_vuelve_a_procesar(sesion_procesando, monkeypatch):
    relanzados = []
    monkeypatch.setattr(sg, "_lanzar", lambda f, *a: relanzados.append((f.__name__, a[0])))
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    assert relanzados == [("procesar", sesion_procesando["id"])]
    assert (sesion_procesando["carpeta"] / "000000.parte").exists()  # el audio no se borra mientras se procesa
    assert _estado(sesion_procesando)[0] == E.PROCESANDO


def test_tras_un_reinicio_si_el_trabajador_sigue_vivo_no_se_duplica_el_trabajo(sesion_procesando, monkeypatch):
    relanzados = []
    monkeypatch.setattr(sg, "_lanzar", lambda f, *a: relanzados.append(f.__name__))
    (sesion_procesando["carpeta"] / "trabajador.pid").write_text(str(os.getpid()))  # un proceso que sí está vivo
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    assert relanzados == [] and sesion_procesando["carpeta"].exists()
    assert _estado(sesion_procesando)[0] == E.PROCESANDO


def test_tras_un_reinicio_sin_audio_pero_con_transcripcion_solo_se_regenera_el_material(sesion_procesando, monkeypatch):
    relanzados = []
    monkeypatch.setattr(sg, "_lanzar", lambda f, *a: relanzados.append(f.__name__))
    sg.borrar_audio(sesion_procesando["id"])
    with sesion_procesando["fabrica"]() as db:
        db.get(Grabacion, sesion_procesando["id"]).clase.contenido = ContenidoClase(transcripcion_texto="hola", retirado=True)
        db.commit()
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    assert relanzados == ["procesar_generacion"]


def test_tras_un_reinicio_sin_audio_ni_transcripcion_queda_en_error(sesion_procesando, monkeypatch):
    monkeypatch.setattr(sg, "_lanzar", lambda *a: pytest.fail("no hay nada que reanudar"))
    sg.borrar_audio(sesion_procesando["id"])
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    estado, error = _estado(sesion_procesando)
    assert estado == E.ERROR and "reinició" in error


def test_tras_un_reinicio_el_audio_de_una_sesion_con_reintento_pendiente_se_conserva(sesion_procesando, monkeypatch):
    """Encontrado probando con el servidor real: reiniciar borraba el audio que el reintento automático necesitaba."""
    monkeypatch.setattr(sg, "_lanzar", lambda *a: None)
    with sesion_procesando["fabrica"]() as db:
        sg.programar_reintento(db.get(Grabacion, sesion_procesando["id"]), "falló")
        db.commit()
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    assert (sesion_procesando["carpeta"] / "000000.parte").exists()


def test_el_audio_de_una_sesion_que_nadie_procesa_ni_graba_se_borra_al_arrancar(sesion_procesando, monkeypatch):
    monkeypatch.setattr(sg, "_lanzar", lambda *a: None)
    huerfano = sg.CARPETA_AUDIO / "999"
    huerfano.mkdir(parents=True)
    (huerfano / "000000.parte").write_bytes(b"x")
    sg.recuperar_al_iniciar(sesion_procesando["db"], sesion_procesando["fabrica"])
    assert not huerfano.exists() and sesion_procesando["carpeta"].exists()


def test_se_sabe_si_un_proceso_esta_vivo():
    assert sg._proceso_vivo(os.getpid()) is True
    assert sg._proceso_vivo(2_000_000_000) is False
