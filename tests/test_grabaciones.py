"""Control de clase en vivo: sesión de grabación, equipo grabador, trozos de audio, procesamiento y corte automático."""
import datetime

import pytest

from infraestructura.modelos_orm import Clase, EstadoGrabacion, Grabacion
from servicios import servicio_grabacion as sg

CLAVE = "clave-segura-123"
LUNES_0930 = datetime.datetime(2026, 9, 28, 9, 30)  # lunes: el bloque de prueba es de lunes 09:00-10:00
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
CLUSTER = b"\x1f\x43\xb6\x75" + b"\x00" * 200  # lo que empieza cada trozo siguiente de un mismo flujo
EQUIPO_A, EQUIPO_B = "equipo-sala-0001", "celular-prof-0002"


def _login(cliente, rut):
    r = cliente.post("/auth/login/staff", json={"rut": rut, "password": CLAVE})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def tiempo(monkeypatch, tmp_path):
    """Reloj controlable, carpeta de audio temporal, y el procesamiento pesado (Whisper, Ollama) reemplazado."""
    reloj = {"local": LUNES_0930, "utc": datetime.datetime(2026, 9, 28, 12, 30)}
    monkeypatch.setattr(sg, "ahora_local", lambda: reloj["local"])
    monkeypatch.setattr(sg, "ahora_utc", lambda: reloj["utc"])
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    monkeypatch.setattr(sg, "_lanzar", lambda f, *a: f(*a))  # sin hilos: el procesamiento corre al instante
    monkeypatch.setattr(sg, "transcribir", lambda ruta: ("Hoy vimos la fotosíntesis.", "1\n00:00:00,000 --> 00:00:02,000\nHoy vimos la fotosíntesis.\n"))
    monkeypatch.setattr(sg, "generar_material", lambda t, asignatura=None: ("Resumen X", "- punto", "hoja", [{"pregunta": "¿P?", "respuesta": "R"}]))
    reloj["avanzar"] = lambda **kw: reloj.update(local=reloj["local"] + datetime.timedelta(**kw), utc=reloj["utc"] + datetime.timedelta(**kw))
    return reloj


@pytest.fixture()
def g(cliente, colegio_id, headers_utp, tiempo, tmp_path):
    """Dos profesoras (Ana y Beta), cursos 8A y 8B, un bloque de Ana el lunes 09:00-10:00 y otro de Beta."""

    def profesor(rut, nombre):
        r = cliente.post("/usuarios", json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, headers=headers_utp)
        return r.json()["id"]

    def bloque(curso, prof, dia=0, ini="09:00", fin="10:00", tipo="CLASE"):
        r = cliente.post(f"/cursos/{curso}/bloques", json={"tipo": tipo, "asignatura": "Matemática", "profesor_id": prof, "sala": "S1", "dia_semana": dia, "hora_inicio": ini, "hora_fin": fin}, headers=headers_utp)
        assert r.status_code == 201
        return r.json()["id"]

    ana, beta = profesor("5126663-3", "Ana"), profesor("6000000-K", "Beta")
    c8a = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    c8b = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()
    d = {
        "c": cliente, "ana": _login(cliente, "5126663-3"), "beta": _login(cliente, "6000000-K"), "utp": headers_utp,
        "bloque": bloque(c8a["id"], ana), "bloque_beta": bloque(c8b["id"], beta),
        "bloque_martes": bloque(c8a["id"], ana, dia=1), "recreo": bloque(c8a["id"], None, dia=0, ini="10:00", fin="10:15", tipo="RECREO"),
        "curso": c8a, "audio": tmp_path / "audio",
    }
    # un alumno del 8A, para comprobar qué ve
    cliente.post("/cursos/unirse", json={"codigo_invitacion": c8a["codigo_invitacion"], "rut": "11222333-9", "nombre": "Luis", "pin": "482915"})
    r = cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "482915"})
    d["alumno"] = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return d


def _crear(g, quien="ana", bloque="bloque"):
    return g["c"].post("/grabaciones", json={"bloque_id": g[bloque]}, headers=g[quien])


def _comando(g, gid, accion, quien="ana"):
    return g["c"].post(f"/grabaciones/{gid}/comando", json={"accion": accion}, headers=g[quien])


def _grabador(g, gid, equipo=EQUIPO_A, forzar=False):
    return g["c"].post(f"/grabaciones/{gid}/grabador", json={"dispositivo": equipo, "forzar": forzar}, headers=g["ana"])


def _latido(g, gid, equipo=EQUIPO_A, segundos=0, nivel=0.2):
    return g["c"].post(f"/grabaciones/{gid}/latido", json={"dispositivo": equipo, "segundos": segundos, "nivel": nivel}, headers=g["ana"])


def _trozo(g, gid, n, datos=None, equipo=EQUIPO_A, tipo="audio/webm;codecs=opus"):
    if datos is None:  # solo el primer trozo de un flujo lleva la cabecera; los demás empiezan con un "cluster"
        datos = WEBM if n == 0 else CLUSTER
    return g["c"].put(f"/grabaciones/{gid}/trozos/{n}", params={"dispositivo": equipo}, content=datos, headers={**g["ana"], "Content-Type": tipo})


def _en_curso(g):
    """Sesión creada, equipo A conectado y grabando."""
    gid = _crear(g).json()["id"]
    assert _grabador(g, gid).status_code == 200
    assert _comando(g, gid, "iniciar").status_code == 200
    return gid


def _estado(g, gid):
    return g["c"].get(f"/grabaciones/{gid}", headers=g["ana"]).json()


# --- Solo la red del colegio, solo el profesor del bloque ---------------------------------------


def test_desde_internet_no_se_puede_ni_ver_ni_controlar(g, cliente_remoto):
    gid = _crear(g).json()["id"]
    for metodo, url, cuerpo in [
        ("get", "/grabaciones/hoy", None),
        ("post", "/grabaciones", {"bloque_id": g["bloque"]}),
        ("get", f"/grabaciones/{gid}", None),
        ("post", f"/grabaciones/{gid}/comando", {"accion": "iniciar"}),
        ("post", f"/grabaciones/{gid}/grabador", {"dispositivo": EQUIPO_A, "forzar": False}),
    ]:
        r = getattr(cliente_remoto, metodo)(url, headers=g["ana"], **({"json": cuerpo} if cuerpo else {}))
        assert r.status_code == 403, url
    r = cliente_remoto.put(f"/grabaciones/{gid}/trozos/0", params={"dispositivo": EQUIPO_A}, content=WEBM, headers={**g["ana"], "Content-Type": "audio/webm"})
    assert r.status_code == 403


def test_pasar_por_un_tunel_o_proxy_cuenta_como_internet_aunque_venga_de_localhost(g):
    """Un túnel de Cloudflare se conecta desde este mismo equipo: lo delatan sus cabeceras."""
    for cabecera in ("X-Forwarded-For", "CF-Connecting-IP", "X-Real-IP", "Forwarded"):
        r = g["c"].get("/grabaciones/hoy", headers={**g["ana"], cabecera: "198.51.100.7"})
        assert r.status_code == 403, cabecera
    assert g["c"].get("/grabaciones/hoy", headers=g["ana"]).status_code == 200


def test_una_direccion_privada_de_la_red_del_colegio_si_es_local(g, cliente):
    from fastapi.testclient import TestClient

    for ip in ("192.168.1.40", "10.0.0.5", "172.16.3.3"):
        c = TestClient(cliente.app, client=(ip, 50000))
        assert c.get("/grabaciones/hoy", headers=g["ana"]).status_code == 200, ip
    publica = TestClient(cliente.app, client=("8.8.8.8", 50000))
    assert publica.get("/grabaciones/hoy", headers=g["ana"]).status_code == 403


def test_solo_el_profesor_de_ese_bloque(g):
    assert _crear(g, quien="beta").status_code == 404  # no revela que el bloque existe
    assert _crear(g, quien="utp").status_code == 403
    assert _crear(g, quien="alumno").status_code == 403
    gid = _crear(g).json()["id"]
    assert g["c"].get(f"/grabaciones/{gid}", headers=g["beta"]).status_code == 404
    assert _comando(g, gid, "cancelar", quien="beta").status_code == 404
    assert g["c"].post(f"/grabaciones/{gid}/grabador", json={"dispositivo": EQUIPO_A, "forzar": False}, headers=g["beta"]).status_code == 404


# --- Crear la sesión ---------------------------------------------------------------------------


def test_los_bloques_de_hoy_del_profesor(g):
    hoy = g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()
    assert [(b["bloque_id"], b["puede_grabar"], b["grabacion"]) for b in hoy] == [(g["bloque"], True, None)]  # sin el del martes, ni el recreo, ni el de Beta
    _crear(g)
    assert g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]["grabacion"]["estado"] == "esperando"


def test_solo_se_graba_un_bloque_de_clase_de_hoy_y_antes_del_corte(g, tiempo):
    assert _crear(g, bloque="bloque_martes").status_code == 409  # no es de hoy
    assert _crear(g, bloque="recreo").status_code == 404  # sin profesor: no es de Ana
    tiempo["local"] = datetime.datetime(2026, 9, 28, 10, 16)  # 16 min después del término (gracia de 15)
    r = _crear(g)
    assert r.status_code == 409 and "terminó" in r.json()["detail"]
    hoy = g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]
    assert hoy["puede_grabar"] is False and "terminó" in hoy["motivo"]
    tiempo["local"] = datetime.datetime(2026, 9, 28, 10, 14)  # aún dentro de la gracia
    assert _crear(g).status_code == 201


def test_crear_dos_veces_retoma_la_misma_sesion_y_no_duplica(g):
    a = _crear(g)
    b = _crear(g)
    assert a.status_code == 201 and b.json()["id"] == a.json()["id"]
    assert g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]["grabacion"]["id"] == a.json()["id"]


def test_una_clase_que_ya_tiene_material_no_se_vuelve_a_grabar(g):
    gid = _crear(g).json()["id"]
    _grabador(g, gid)
    _comando(g, gid, "iniciar")
    _trozo(g, gid, 0)
    _comando(g, gid, "terminar")
    g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": EQUIPO_A}, headers=g["ana"])
    r = _crear(g)
    assert r.status_code == 409


# --- El flujo completo, con el PC de la sala y con el celular -----------------------------------


@pytest.mark.parametrize("equipo", [EQUIPO_A, EQUIPO_B], ids=["pc-de-la-sala", "celular-del-profesor"])
def test_flujo_completo_de_una_clase(g, tiempo, equipo):
    """Da igual qué equipo graba: la sesión, los comandos y el audio funcionan igual."""
    gid = _crear(g).json()["id"]
    assert _grabador(g, gid, equipo).json()["grabador_conectado"] is True
    assert _comando(g, gid, "iniciar").json()["estado"] == "grabando"

    for n in range(3):
        assert _trozo(g, gid, n, equipo=equipo).status_code == 200
        tiempo["avanzar"](seconds=10)
        assert _latido(g, gid, equipo, segundos=(n + 1) * 10, nivel=0.4).json()["estado"] == "grabando"
    assert _comando(g, gid, "pausar").json()["estado"] == "pausada"
    assert _latido(g, gid, equipo, segundos=30).json()["estado"] == "pausada"  # el equipo se entera con su latido
    assert _comando(g, gid, "silenciar").json()["silenciada"] is True
    assert _comando(g, gid, "reanudar").json()["estado"] == "grabando"
    assert _comando(g, gid, "activar_audio").json()["silenciada"] is False

    assert _comando(g, gid, "terminar").json()["estado"] == "terminando"
    assert _trozo(g, gid, 3, equipo=equipo).status_code == 200  # lo último que subía el equipo
    r = g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": equipo}, headers=g["ana"])
    assert r.status_code == 200 and r.json()["estado"] in ("procesando", "terminada")  # en producción procesa en un hilo aparte
    assert _estado(g, gid)["estado"] == "terminada"

    # Quedó el material, esperando que el profesor lo apruebe; los alumnos aún no lo ven; el audio ya no existe.
    clases = g["c"].get("/clases", headers=g["ana"]).json()
    assert [(c["estado"], c["bloque_id"]) for c in clases] == [("por_aprobar", g["bloque"])]
    detalle = g["c"].get(f"/clases/{clases[0]['id']}", headers=g["ana"]).json()["contenido"]
    assert detalle["resumen"] == "Resumen X" and "fotosíntesis" in detalle["transcripcion_texto"]
    assert g["c"].get("/clases", headers=g["alumno"]).json() == []
    assert not (g["audio"] / str(gid)).exists()


def test_iniciar_exige_un_equipo_grabador_conectado(g, tiempo):
    gid = _crear(g).json()["id"]
    assert _comando(g, gid, "iniciar").status_code == 409  # nadie graba todavía
    _grabador(g, gid)
    tiempo["avanzar"](seconds=sg.LATIDO_VIGENTE_S + 1)  # el equipo dejó de latir
    assert _estado(g, gid)["grabador_conectado"] is False
    assert _comando(g, gid, "iniciar").status_code == 409
    _latido(g, gid)
    assert _comando(g, gid, "iniciar").status_code == 200


def test_cambiar_de_equipo_pide_confirmacion_y_el_anterior_queda_fuera(g):
    gid = _en_curso(g)
    assert _grabador(g, gid, EQUIPO_B).status_code == 409  # el equipo A sigue conectado: hay que forzar
    assert _grabador(g, gid, EQUIPO_B, forzar=True).json()["grabador_id"] == EQUIPO_B
    assert _latido(g, gid, EQUIPO_A).status_code == 409  # el anterior se entera y debe parar
    assert _trozo(g, gid, 0, equipo=EQUIPO_A).status_code == 409
    assert _trozo(g, gid, 0, equipo=EQUIPO_B).status_code == 200
    assert _latido(g, gid, EQUIPO_B).status_code == 200


def test_un_equipo_que_dejo_de_latir_se_puede_reemplazar_sin_forzar(g, tiempo):
    gid = _en_curso(g)
    tiempo["avanzar"](seconds=sg.LATIDO_VIGENTE_S + 5)
    assert _grabador(g, gid, EQUIPO_B).status_code == 200


def test_los_comandos_fuera_de_orden_se_rechazan(g):
    gid = _crear(g).json()["id"]
    for accion in ("pausar", "reanudar", "terminar"):
        assert _comando(g, gid, accion).status_code == 409, accion
    _grabador(g, gid)
    _comando(g, gid, "iniciar")
    assert _comando(g, gid, "iniciar").status_code == 409
    assert _comando(g, gid, "reanudar").status_code == 409
    assert _comando(g, gid, "cancelar").status_code == 409  # ya empezó
    assert g["c"].post(f"/grabaciones/{gid}/comando", json={"accion": "borrar_todo"}, headers=g["ana"]).status_code == 422


def test_cancelar_antes_de_empezar_no_deja_nada(g):
    gid = _crear(g).json()["id"]
    r = _comando(g, gid, "cancelar")
    assert r.status_code == 200 and r.json() is None
    assert g["c"].get(f"/grabaciones/{gid}", headers=g["ana"]).status_code == 404
    assert g["c"].get("/clases", headers=g["ana"]).json() == []


def test_marcar_la_clase_como_prioritaria(g):
    gid = _crear(g).json()["id"]
    assert _comando(g, gid, "marcar_prioritaria").json()["prioritaria"] is True
    assert _comando(g, gid, "quitar_prioritaria").json()["prioritaria"] is False


def test_la_clase_aparece_como_grabando_al_profesor_y_no_a_los_alumnos(g):
    _en_curso(g)
    assert [c["estado"] for c in g["c"].get("/clases", headers=g["ana"]).json()] == ["grabando"]
    assert g["c"].get("/clases", headers=g["alumno"]).json() == []
    assert [c["estado"] for c in g["c"].get("/clases", headers=g["utp"]).json()] == ["grabando"]


def test_el_tiempo_grabado_nunca_retrocede(g):
    gid = _en_curso(g)
    _latido(g, gid, segundos=120)
    assert _latido(g, gid, segundos=60).json()["segundos_grabados"] == 120  # llegó un latido viejo


# --- El audio que sube el equipo ---------------------------------------------------------------


def test_los_trozos_se_validan(g):
    gid = _en_curso(g)
    assert _trozo(g, gid, 0, tipo="text/html").status_code == 415
    assert _trozo(g, gid, 0, tipo="application/octet-stream").status_code == 415
    assert _trozo(g, gid, 0, datos=b"<script>alert(1)</script>" + b"x" * 50).status_code == 415  # dice audio/webm pero no lo es
    assert _trozo(g, gid, 0, datos=b"").status_code == 413
    assert _trozo(g, gid, 0, datos=WEBM + b"x" * sg.MAX_TROZO_BYTES).status_code == 413
    assert _trozo(g, gid, -1).status_code == 422
    assert _trozo(g, gid, sg.MAX_TROZOS).status_code == 422
    assert _trozo(g, gid, 0).status_code == 200
    assert _trozo(g, gid, 1, tipo="audio/ogg").status_code == 415  # no puede cambiar de formato a mitad
    assert _estado(g, gid)["trozos"] == 1


def test_el_nombre_del_archivo_lo_pone_el_servidor(g):
    gid = _en_curso(g)
    assert _trozo(g, gid, 7).status_code == 200
    assert [f.name for f in (g["audio"] / str(gid)).iterdir()] == ["000007.parte"]
    # La ruta con ../ no llega a ningún lado: el número de trozo es un entero.
    r = g["c"].put(f"/grabaciones/{gid}/trozos/..%2F..%2Fx", params={"dispositivo": EQUIPO_A}, content=WEBM, headers={**g["ana"], "Content-Type": "audio/webm"})
    assert r.status_code in (404, 422)


def test_reintentar_un_trozo_lo_reemplaza_no_lo_duplica(g):
    gid = _en_curso(g)
    _trozo(g, gid, 0)
    _trozo(g, gid, 0)
    s = _estado(g, gid)
    assert s["trozos"] == 1 and len(list((g["audio"] / str(gid)).iterdir())) == 1


def test_no_se_sube_audio_antes_de_iniciar_ni_despues_de_terminar(g):
    gid = _crear(g).json()["id"]
    _grabador(g, gid)
    assert _trozo(g, gid, 0).status_code == 409  # aún esperando
    _comando(g, gid, "iniciar")
    _trozo(g, gid, 0)
    _comando(g, gid, "terminar")
    g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": EQUIPO_A}, headers=g["ana"])
    assert _trozo(g, gid, 1).status_code == 409


def test_el_tamano_total_tiene_tope(g, monkeypatch):
    monkeypatch.setattr(sg, "MAX_TOTAL_BYTES", 500)
    gid = _en_curso(g)
    assert _trozo(g, gid, 0, datos=WEBM).status_code == 200  # 204 bytes
    assert _trozo(g, gid, 1, datos=WEBM).status_code == 200  # 408
    assert _trozo(g, gid, 2, datos=WEBM).status_code == 413  # 612 > 500


def test_los_ids_de_equipo_malos_se_rechazan(g):
    gid = _crear(g).json()["id"]
    for malo in ("corto", "con espacios y !!!", "x" * 65, "../../etc/passwd"):
        r = g["c"].post(f"/grabaciones/{gid}/grabador", json={"dispositivo": malo, "forzar": False}, headers=g["ana"])
        assert r.status_code == 422, malo


# --- El audio nunca sobrevive ------------------------------------------------------------------


def _terminar_con_audio(g, gid):
    """Termina la grabación y devuelve cómo quedó la sesión una vez procesada."""
    _trozo(g, gid, 0)
    _comando(g, gid, "terminar")
    assert g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": EQUIPO_A}, headers=g["ana"]).status_code == 200
    return _estado(g, gid)


def test_un_fallo_del_procesamiento_se_reintenta_solo_y_el_audio_se_conserva_solo_mientras_queden_intentos(g, monkeypatch, tiempo):
    """Nadie está frente al computador cuando algo falla: se reintenta solo (5, 15 y 45 min) y, al último fallo, el audio se borra."""
    intentos = []

    def explota(_):
        intentos.append(1)
        raise RuntimeError("se cayó Whisper")

    monkeypatch.setattr(sg, "transcribir", explota)
    gid = _en_curso(g)
    r = _terminar_con_audio(g, gid)
    assert r["estado"] == "error" and "Se reintentará sola" in r["error"] and "intento 2 de 4" in r["error"]
    assert r["reintento_en"] is not None
    assert (g["audio"] / str(gid)).exists()  # se conserva: el reintento lo necesita
    assert [c["estado"] for c in g["c"].get("/clases", headers=g["ana"]).json()] == ["error"]
    for minutos, intento in zip(sg.REINTENTOS_MIN, (2, 3, 4)):
        _vigilar(g, None)
        assert len(intentos) == intento - 1  # todavía no le toca
        tiempo["avanzar"](minutes=minutos, seconds=1)
        _vigilar(g, None)
        assert len(intentos) == intento
    final = _estado(g, gid)
    assert final["estado"] == "error" and final["reintento_en"] is None and "Ya se reintentó 3 veces" in final["error"]
    assert not (g["audio"] / str(gid)).exists()  # sin más intentos, el audio ya no se conserva
    _vigilar(g, None)
    tiempo["avanzar"](hours=5)
    _vigilar(g, None)
    assert len(intentos) == 4  # y no se reintenta de nuevo


def test_si_el_reintento_funciona_la_clase_queda_terminada_y_sin_audio(g, monkeypatch, tiempo):
    llamadas = []
    original = sg.transcribir

    def falla_la_primera_vez(ruta):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("falla pasajera")
        return original(ruta)

    monkeypatch.setattr(sg, "transcribir", falla_la_primera_vez)
    gid = _en_curso(g)
    assert _terminar_con_audio(g, gid)["estado"] == "error"
    tiempo["avanzar"](minutes=sg.REINTENTOS_MIN[0], seconds=1)
    _vigilar(g, None)
    s = _estado(g, gid)
    assert s["estado"] == "terminada" and s["error"] is None and s["reintento_en"] is None
    assert not (g["audio"] / str(gid)).exists()
    assert [c["estado"] for c in g["c"].get("/clases", headers=g["ana"]).json()] == ["por_aprobar"]


def test_se_puede_adelantar_el_reintento_sin_esperar(g, monkeypatch, tiempo):
    llamadas = []
    original = sg.transcribir
    monkeypatch.setattr(sg, "transcribir", lambda ruta: (llamadas.append(1), (_ for _ in ()).throw(RuntimeError("x")) if len(llamadas) == 1 else original(ruta))[1])
    gid = _en_curso(g)
    _terminar_con_audio(g, gid)
    assert g["c"].post(f"/grabaciones/{gid}/reintentar-ahora", headers=g["beta"]).status_code == 404  # solo el profesor de la clase
    assert g["c"].post(f"/grabaciones/{gid}/reintentar-ahora", headers=g["ana"]).status_code == 200
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminada"
    assert g["c"].post(f"/grabaciones/{gid}/reintentar-ahora", headers=g["ana"]).status_code == 409  # ya no hay nada pendiente


def test_reintentar_a_mano_no_pisa_una_sesion_que_se_reintenta_sola(g, monkeypatch):
    """Reiniciar la sesión borraría el audio que el reintento automático necesita."""
    monkeypatch.setattr(sg, "transcribir", lambda ruta: (_ for _ in ()).throw(RuntimeError("x")))
    gid = _en_curso(g)
    _terminar_con_audio(g, gid)
    r = _crear(g)
    assert r.status_code == 201 and r.json()["id"] == gid and r.json()["estado"] == "error" and r.json()["reintento_en"]
    assert (g["audio"] / str(gid)).exists()


def test_sin_voz_no_se_reintenta_porque_no_lo_arregla(g, monkeypatch):
    monkeypatch.setattr(sg, "transcribir", lambda ruta: ("   ", ""))
    gid = _en_curso(g)
    r = _terminar_con_audio(g, gid)
    assert r["estado"] == "error" and "voz" in r["error"] and r["reintento_en"] is None
    assert not (g["audio"] / str(gid)).exists()


def test_si_falla_la_generacion_se_conserva_la_transcripcion_oculta_a_los_alumnos(g, monkeypatch):
    def sin_ollama(_, asignatura=None):
        raise sg.ErrorProceso("No se pudo conectar con Ollama")

    monkeypatch.setattr(sg, "generar_material", sin_ollama)
    gid = _en_curso(g)
    r = _terminar_con_audio(g, gid)
    assert r["estado"] == "error" and "Ollama" in r["error"] and "Se reintentará sola" in r["error"]
    assert not (g["audio"] / str(gid)).exists()  # la transcripción quedó guardada: el audio ya no hace falta
    with g["c"].sesion() as db:
        clase = db.query(Clase).one()
        assert "fotosíntesis" in clase.contenido.transcripcion_texto and clase.contenido.retirado is True
    assert g["c"].get("/clases", headers=g["alumno"]).json() == []
    assert [c["estado"] for c in g["c"].get("/clases", headers=g["ana"]).json()] == ["error"]  # no "retirada": nadie la retiró


def test_sin_voz_es_un_error_claro(g, monkeypatch):
    monkeypatch.setattr(sg, "transcribir", lambda ruta: ("   ", ""))
    gid = _en_curso(g)
    r = _terminar_con_audio(g, gid)
    assert r["estado"] == "error" and "voz" in r["error"]


def test_terminar_sin_haber_recibido_audio_es_un_error_y_se_puede_reintentar(g):
    gid = _en_curso(g)
    _comando(g, gid, "terminar")
    assert g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": EQUIPO_A}, headers=g["ana"]).status_code == 200
    r = _estado(g, gid)
    assert r["estado"] == "error" and "audio" in r["error"]
    nueva = _crear(g)  # reintento: la misma sesión vuelve a empezar
    assert nueva.json()["id"] == gid and nueva.json()["estado"] == "esperando" and nueva.json()["error"] is None
    assert _grabador(g, gid).status_code == 200


def test_tras_un_reinicio_lo_que_se_procesaba_pasa_a_error_y_el_audio_huerfano_se_borra(g, tiempo):
    gid = _en_curso(g)
    _trozo(g, gid, 0)
    huerfano = g["audio"] / "999"
    huerfano.mkdir(parents=True)
    (huerfano / "000000.parte").write_bytes(WEBM)
    with g["c"].sesion() as db:
        db.get(Grabacion, gid).estado = EstadoGrabacion.PROCESANDO
        db.commit()
        sg.recuperar_al_iniciar(db)
        assert db.get(Grabacion, gid).estado == EstadoGrabacion.ERROR
    assert not huerfano.exists()
    assert not (g["audio"] / str(gid)).exists()  # la sesión quedó en error: su audio tampoco se conserva


# --- Corte automático --------------------------------------------------------------------------


def _vigilar(g, fabrica_db):
    with g["c"].sesion() as db:
        sg.vigilar(db, g["c"].sesion)


def test_el_corte_automatico_termina_y_procesa_lo_grabado(g, tiempo):
    gid = _en_curso(g)
    _trozo(g, gid, 0)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "grabando"  # aún no es la hora
    tiempo["local"] = datetime.datetime(2026, 9, 28, 10, 16)  # pasó el término + 15 min
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminando"  # el equipo grabador lo ve en su latido y sube lo último
    _trozo(g, gid, 1)
    g["c"].post(f"/grabaciones/{gid}/finalizar", json={"dispositivo": EQUIPO_A}, headers=g["ana"])
    assert _estado(g, gid)["estado"] == "terminada"


def test_si_el_equipo_no_finaliza_el_servidor_procesa_lo_que_llego(g, tiempo):
    gid = _en_curso(g)
    _trozo(g, gid, 0)
    tiempo["local"] = datetime.datetime(2026, 9, 28, 10, 16)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminando"
    tiempo["avanzar"](seconds=sg.ESPERA_FINALIZAR_S - 5)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminando"
    tiempo["avanzar"](seconds=10)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminada"
    assert not (g["audio"] / str(gid)).exists()


def test_una_sesion_que_nunca_empezo_se_elimina_pasado_el_bloque(g, tiempo):
    gid = _crear(g).json()["id"]
    tiempo["local"] = datetime.datetime(2026, 9, 28, 10, 16)
    _vigilar(g, None)
    assert g["c"].get(f"/grabaciones/{gid}", headers=g["ana"]).status_code == 404
    assert g["c"].get("/clases", headers=g["ana"]).json() == []


def test_sin_ningun_equipo_conectado_por_mucho_tiempo_se_termina_con_lo_recibido(g, tiempo):
    gid = _en_curso(g)
    _trozo(g, gid, 0)
    tiempo["avanzar"](seconds=sg.MAX_SIN_GRABADOR_S - 1)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "grabando"
    tiempo["avanzar"](seconds=5)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminando"


def test_la_vigilancia_no_toca_sesiones_ya_terminadas_o_en_error(g, tiempo):
    gid = _en_curso(g)
    _terminar_con_audio(g, gid)
    tiempo["local"] = datetime.datetime(2026, 9, 28, 12, 0)
    _vigilar(g, None)
    assert _estado(g, gid)["estado"] == "terminada"


def test_el_tipo_de_audio_se_revisa_aunque_el_primer_trozo_que_llega_no_sea_el_cero(g):
    gid = _en_curso(g)
    assert _trozo(g, gid, 1, tipo="text/html").status_code == 415
    assert _trozo(g, gid, 1, tipo="application/x-msdownload").status_code == 415
    assert not (g["audio"] / str(gid)).exists()  # no se escribió nada
    assert _estado(g, gid)["trozos"] == 0


def test_el_servicio_tambien_limita_el_tamano_del_trozo(g):
    gid = _en_curso(g)
    with g["c"].sesion() as db:
        grabacion = db.get(Grabacion, gid)
        with pytest.raises(sg.ErrorGrabacion) as e:
            sg.guardar_trozo(db, grabacion, EQUIPO_A, 0, WEBM + b"x" * sg.MAX_TROZO_BYTES, "audio/webm")
        assert e.value.estado == 413


def test_una_clase_de_hoy_que_ya_tiene_material_sin_sesion_de_grabacion_no_se_graba(g):
    """Por ejemplo, material que existía de antes: grabar encima lo pisaría."""
    from infraestructura.modelos_orm import ContenidoClase

    with g["c"].sesion() as db:
        clase = Clase(bloque_id=g["bloque"], fecha=LUNES_0930.date())
        clase.contenido = ContenidoClase(resumen="ya estaba")
        db.add(clase)
        db.commit()
    r = _crear(g)
    assert r.status_code == 409 and "material" in r.json()["detail"]
    assert g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]["puede_grabar"] is False


def test_si_fallo_solo_la_generacion_se_regenera_sin_volver_a_grabar(g, monkeypatch):
    def sin_ollama(_, asignatura=None):
        raise sg.ErrorProceso("No se pudo conectar con Ollama")

    original = sg.generar_material
    monkeypatch.setattr(sg, "generar_material", sin_ollama)
    gid = _en_curso(g)
    assert _terminar_con_audio(g, gid)["estado"] == "error"
    # Retomar la sesión devuelve la misma (con el error), no un "ya tiene material".
    assert _crear(g).json()["estado"] == "error"
    assert g["c"].post(f"/grabaciones/{gid}/regenerar", headers=g["ana"]).status_code == 200
    assert _estado(g, gid)["estado"] == "error"  # Ollama sigue apagado: vuelve al error, la transcripción se conserva
    monkeypatch.setattr(sg, "generar_material", original)  # Ollama volvió
    assert g["c"].post(f"/grabaciones/{gid}/regenerar", headers=g["ana"]).status_code == 200
    assert _estado(g, gid)["estado"] == "terminada"
    clase = g["c"].get("/clases", headers=g["ana"]).json()[0]
    assert clase["estado"] == "por_aprobar"
    det = g["c"].get(f"/clases/{clase['id']}", headers=g["ana"]).json()["contenido"]
    assert det["resumen"] == "Resumen X" and "fotosíntesis" in det["transcripcion_texto"]
    assert not (g["audio"] / str(gid)).exists()


def test_regenerar_solo_cuando_corresponde(g):
    gid = _crear(g).json()["id"]
    assert g["c"].post(f"/grabaciones/{gid}/regenerar", headers=g["ana"]).status_code == 409  # esperando
    _grabador(g, gid)
    _comando(g, gid, "iniciar")
    _terminar_con_audio(g, gid)  # terminó bien
    assert g["c"].post(f"/grabaciones/{gid}/regenerar", headers=g["ana"]).status_code == 409
    assert g["c"].post(f"/grabaciones/{gid}/regenerar", headers=g["beta"]).status_code == 404


# --- Un equipo que se corta y vuelve (celular que se duerme, página recargada) ------------------


def _webm_de_tono(ruta, segundos):
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg no está instalado")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}", "-c:a", "libopus", str(ruta)], check=True)
    return ruta.read_bytes()


def _partir(datos, n):
    paso = len(datos) // n + 1
    return [datos[i:i + paso] for i in range(0, len(datos), paso)]


def test_un_solo_flujo_se_une_tal_cual(tmp_path):
    flujo = _webm_de_tono(tmp_path / "a.webm", 2)
    carpeta = tmp_path / "c"
    carpeta.mkdir()
    for i, parte in enumerate(_partir(flujo, 3)):
        (carpeta / f"{i:06d}.parte").write_bytes(parte)
    unido = sg._unir_trozos(carpeta, "audio/webm")
    assert unido.name == "clase.webm" and unido.read_bytes() == flujo


def test_si_el_equipo_volvio_cada_flujo_se_convierte_aparte_y_se_juntan(tmp_path):
    import wave

    a, b = _webm_de_tono(tmp_path / "a.webm", 2), _webm_de_tono(tmp_path / "b.webm", 1)
    carpeta = tmp_path / "c"
    carpeta.mkdir()
    partes = _partir(a, 2) + _partir(b, 2)  # el equipo se cortó tras el trozo 1 y volvió con una cabecera nueva
    for i, parte in enumerate(partes):
        (carpeta / f"{i:06d}.parte").write_bytes(parte)
    assert [len(f) for f in sg._flujos(sorted(carpeta.glob("*.parte")), "audio/webm")] == [2, 2]
    unido = sg._unir_trozos(carpeta, "audio/webm")
    assert unido.name == "clase.wav"
    with wave.open(str(unido), "rb") as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 16000)
        assert 2.7 < w.getnframes() / 16000 < 3.4  # 2 s + 1 s: no se perdió ninguno de los dos flujos
    assert not list(carpeta.glob("flujo*")) and not list(carpeta.glob("opt_*"))  # sin temporales de más


def test_la_materia_de_la_clase_llega_al_generador_del_material(g, monkeypatch):
    recibidas = []

    def espia(texto, asignatura=None):
        recibidas.append(asignatura)
        return "Resumen X", "- punto", "hoja", [{"pregunta": "¿P?", "respuesta": "R"}]

    monkeypatch.setattr(sg, "generar_material", espia)
    gid = _en_curso(g)
    assert _terminar_con_audio(g, gid)["estado"] == "terminada"
    assert recibidas == ["Matemática"]  # el modelo sabe de qué materia es y corrige mejor términos y siglas


def test_tras_transcribir_se_libera_la_memoria_de_whisper_para_que_la_use_ollama(monkeypatch):
    """En una GPU de 4 GB compiten: con Whisper cargado, parte del LLM se iba a la CPU y la generación tardaba el doble."""
    import servicios.servicio_transcripcion as st

    liberada = []

    class MotorFalso:
        current_model = "cargado"

        def free_memory(self):
            liberada.append(True)

    class ServicioFalso:
        engine = MotorFalso()

        def set_enhancement_config(self, config):
            pass

        def load_model(self, modelo):
            pass

        def transcribe_file(self, ruta):
            yield {"status": "✅ Completado", "text": "hola", "srt": "s"}

    monkeypatch.setattr(st, "TranscriptionService", ServicioFalso)
    monkeypatch.setattr(sg, "_servicio", None)
    assert sg.transcribir("x") == ("hola", "s")
    assert liberada == [True]
    monkeypatch.setattr(sg, "_servicio", None)  # que no se filtre el servicio falso a otras pruebas
