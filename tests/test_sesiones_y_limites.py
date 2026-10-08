"""Cierre de sesiones, límite de intentos por dirección, cuentas inexistentes que se bloquean igual y docs apagadas."""
import datetime

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from infraestructura import seguridad
from interfaz.api import limites
from interfaz.api.aplicacion import crear_app
from interfaz.api.ip_cliente import ip_del_cliente
from interfaz.api.red_local import es_red_local
from nucleo.limitador import FallosDeCuentasInexistentes, LimitadorDeFallos

CLAVE = "clave-segura-123"
RUT_PROF = "5126663-3"
RUT_ALUMNO = "11222333-9"


def _con(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def g(cliente, colegio_id, headers_utp):
    """Un UTP, una profesora y un alumno con curso, todos con sesión abierta."""
    r = cliente.post("/usuarios", json={"rut": RUT_PROF, "nombre": "Ana", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, headers=headers_utp)
    assert r.status_code == 201
    c = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    r = cliente.post("/cursos/unirse", json={"codigo_invitacion": c["codigo_invitacion"], "rut": RUT_ALUMNO, "nombre": "Luis", "pin": "482915"})
    assert r.status_code == 200
    ana = cliente.post("/auth/login/staff", json={"rut": RUT_PROF, "password": CLAVE}).json()["access_token"]
    ids = {u["rut"]: u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json()}
    return {"c": cliente, "utp": headers_utp, "ana": _con(ana), "alumno": _con(r.json()["access_token"]), "ids": ids}


# --- Sesiones que se cierran -----------------------------------------------------------------------------------------


def test_cerrar_sesiones_invalida_los_tokens_anteriores_pero_no_los_nuevos(g):
    c = g["c"]
    assert c.get("/auth/me", headers=g["ana"]).status_code == 200
    assert c.post("/auth/cerrar-sesiones", headers=g["ana"]).status_code == 204
    assert c.get("/auth/me", headers=g["ana"]).status_code == 401
    nuevo = c.post("/auth/login/staff", json={"rut": RUT_PROF, "password": CLAVE}).json()["access_token"]
    assert c.get("/auth/me", headers=_con(nuevo)).status_code == 200


def test_cerrar_sesiones_no_toca_las_de_otras_personas(g):
    g["c"].post("/auth/cerrar-sesiones", headers=g["ana"])
    assert g["c"].get("/auth/me", headers=g["utp"]).status_code == 200
    assert g["c"].get("/auth/me", headers=g["alumno"]).status_code == 200


def test_resetear_la_clave_de_una_profesora_cierra_su_sesion_robada(g):
    assert g["c"].post(f"/usuarios/{g['ids'][RUT_PROF]}/reset-password", headers=g["utp"]).status_code == 200
    assert g["c"].get("/auth/me", headers=g["ana"]).status_code == 401


def test_resetear_el_pin_de_un_alumno_cierra_su_sesion_robada(g):
    assert g["c"].post(f"/usuarios/{g['ids'][RUT_ALUMNO]}/reset-pin", headers=g["ana"]).status_code in (200, 404)
    r = g["c"].post(f"/usuarios/{g['ids'][RUT_ALUMNO]}/reset-pin", headers=g["utp"])
    assert r.status_code == 200
    assert g["c"].get("/auth/me", headers=g["alumno"]).status_code == 401


def test_elegir_pin_nuevo_con_el_codigo_cierra_las_sesiones_anteriores_y_entrega_una_valida(g):
    codigo = g["c"].post(f"/usuarios/{g['ids'][RUT_ALUMNO]}/reset-pin", headers=g["utp"]).json()["codigo"]
    r = g["c"].post("/auth/restablecer-pin", json={"rut": RUT_ALUMNO, "codigo": codigo, "pin": "739158"})
    assert r.status_code == 200
    assert g["c"].get("/auth/me", headers=g["alumno"]).status_code == 401
    assert g["c"].get("/auth/me", headers=_con(r.json()["access_token"])).status_code == 200


def test_elegir_clave_nueva_con_el_codigo_cierra_las_sesiones_anteriores_y_entrega_una_valida(g):
    codigo = g["c"].post(f"/usuarios/{g['ids'][RUT_PROF]}/reset-password", headers=g["utp"]).json()["codigo"]
    r = g["c"].post("/auth/restablecer-password", json={"rut": RUT_PROF, "codigo": codigo, "password": "otra-clave-segura-9"})
    assert r.status_code == 200
    assert g["c"].get("/auth/me", headers=g["ana"]).status_code == 401
    assert g["c"].get("/auth/me", headers=_con(r.json()["access_token"])).status_code == 200


def _dejar_codigo_sin_pasar_por_el_reseteo(g, rut):
    """Un código de un solo uso vigente puesto directo en la base: así se prueba que usarlo cierra las sesiones por sí
    mismo, sin apoyarse en que el reseteo del staff ya lo hizo."""
    from infraestructura.modelos_orm import Usuario

    with g["c"].sesion() as db:
        u = db.query(Usuario).filter_by(rut=rut).one()
        u.codigo_reset_hash = seguridad.hashear_secreto("ABCDEF")
        u.codigo_reset_vence = seguridad.ahora_utc() + datetime.timedelta(minutes=10)
        db.commit()


def test_usar_el_codigo_de_pin_cierra_las_sesiones_aunque_el_reseteo_no_lo_hiciera(g):
    _dejar_codigo_sin_pasar_por_el_reseteo(g, RUT_ALUMNO)
    assert g["c"].get("/auth/me", headers=g["alumno"]).status_code == 200
    assert g["c"].post("/auth/restablecer-pin", json={"rut": RUT_ALUMNO, "codigo": "ABCDEF", "pin": "739158"}).status_code == 200
    assert g["c"].get("/auth/me", headers=g["alumno"]).status_code == 401


def test_usar_el_codigo_de_clave_cierra_las_sesiones_aunque_el_reseteo_no_lo_hiciera(g):
    _dejar_codigo_sin_pasar_por_el_reseteo(g, RUT_PROF)
    assert g["c"].get("/auth/me", headers=g["ana"]).status_code == 200
    assert g["c"].post("/auth/restablecer-password", json={"rut": RUT_PROF, "codigo": "ABCDEF", "password": "otra-clave-segura-9"}).status_code == 200
    assert g["c"].get("/auth/me", headers=g["ana"]).status_code == 401


def test_desactivar_y_reactivar_no_revive_las_sesiones_de_antes(g):
    g["c"].post(f"/usuarios/{g['ids'][RUT_PROF]}/desactivar", headers=g["utp"])
    g["c"].post(f"/usuarios/{g['ids'][RUT_PROF]}/activar", headers=g["utp"])
    assert g["c"].get("/auth/me", headers=g["ana"]).status_code == 401


def test_un_token_viejo_sin_numero_de_sesion_sigue_valiendo_mientras_no_se_revoque(g):
    """Los tokens emitidos antes de esta versión no traen `v`: cuentan como la sesión 0."""
    payload = seguridad.decodificar_token(g["ana"]["Authorization"].split()[1])
    payload.pop("v")
    payload.pop("exp")
    viejo = seguridad.crear_token(payload)
    assert g["c"].get("/auth/me", headers=_con(viejo)).status_code == 200
    g["c"].post("/auth/cerrar-sesiones", headers=g["ana"])
    assert g["c"].get("/auth/me", headers=_con(viejo)).status_code == 401


# --- Límite por dirección ---------------------------------------------------------------------------------------------


def _fallar_logins(c, n, rut="1000005-K"):
    return [c.post("/auth/login/staff", json={"rut": rut, "password": "mala-clave-123"}).status_code for _ in range(n)]


def test_una_direccion_con_demasiados_fallos_queda_fuera_aunque_pruebe_cuentas_distintas(cliente, setup_inicial, monkeypatch):
    ruts = ["1000005-K", "5126663-3", "6000000-K", "7654321-6", "11222333-9", "12345678-5", "9999999-3", "8888888-5", "7777777-3", "6666666-4"]
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(5, 600))
    estados = [cliente.post("/auth/login/staff", json={"rut": r, "password": "mala-clave-123"}).status_code for r in ruts[:5]]
    assert estados == [401] * 5  # ninguna cuenta llegó a su propio bloqueo
    r = cliente.post("/auth/login/staff", json={"rut": ruts[5], "password": "mala-clave-123"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_el_limite_de_una_direccion_no_afecta_a_otra(cliente, cliente_remoto, setup_inicial, monkeypatch):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(3, 600))
    assert _fallar_logins(cliente, 4, "5126663-3")[-1] == 429
    assert cliente_remoto.post("/auth/login/staff", json={"rut": "5126663-3", "password": "x" * 12}).status_code == 401


def test_un_login_correcto_no_cuenta_como_fallo(cliente, setup_inicial, rut_utp, monkeypatch):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(2, 600))
    for _ in range(5):
        assert cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": CLAVE}).status_code == 200


def test_el_limite_no_toca_las_rutas_que_no_adivinan_nada(cliente, setup_inicial, headers_utp, monkeypatch):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(1, 600))
    _fallar_logins(cliente, 2)
    assert cliente.get("/auth/me", headers=headers_utp).status_code == 200


def test_adivinar_codigos_de_curso_tambien_cuenta(cliente, setup_inicial, monkeypatch):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(3, 600))
    cuerpo = {"codigo_invitacion": "ZZZZZZ", "rut": RUT_ALUMNO, "nombre": "Luis", "pin": "482915"}
    assert [cliente.post("/cursos/unirse", json=cuerpo).status_code for _ in range(4)] == [404, 404, 404, 429]


def test_el_limitador_libera_cuando_caducan_los_fallos():
    t = [0.0]
    lim = LimitadorDeFallos(2, 60, reloj=lambda: t[0])
    lim.registrar("ip")
    lim.registrar("ip")
    assert lim.segundos_de_espera("ip") > 0
    t[0] = 61
    assert lim.segundos_de_espera("ip") == 0


def test_el_limitador_acota_la_memoria():
    lim = LimitadorDeFallos(2, 60, max_claves=100)
    for i in range(1000):
        lim.registrar(f"ip{i}")
    assert len(lim._fallos) == 100


# --- Cuentas que no existen -------------------------------------------------------------------------------------------


def _cinco_fallos(c, ruta, rut, cuerpo):
    return [c.post(ruta, json={"rut": rut, **cuerpo}).status_code for _ in range(6)]


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/auth/login/staff", {"password": "mala-clave-123"}),
    ("/auth/login/alumno", {"pin": "135792"}),
    ("/auth/restablecer-pin", {"codigo": "ABCDEF", "pin": "135792"}),
    ("/auth/restablecer-password", {"codigo": "ABCDEF", "password": "otra-clave-segura-9"}),
])
def test_un_rut_inexistente_responde_igual_que_uno_real_tras_cinco_fallos(cliente, setup_inicial, monkeypatch, ruta, cuerpo):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(1000, 600))  # aquí se prueba solo el bloqueo por cuenta
    inexistente = _cinco_fallos(cliente, ruta, "13579246-7", cuerpo)
    assert inexistente == [401] * 5 + [429]


def test_una_cuenta_real_y_una_inexistente_dan_la_misma_secuencia(cliente, setup_inicial, rut_utp, monkeypatch):
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(1000, 600))
    real = _cinco_fallos(cliente, "/auth/login/staff", rut_utp, {"password": "mala-clave-123"})
    falso = _cinco_fallos(cliente, "/auth/login/staff", "13579246-7", {"password": "mala-clave-123"})
    assert real == falso == [401] * 5 + [429]
    assert cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": CLAVE}).status_code == 429


def test_el_bloqueo_de_un_rut_inexistente_crece_como_el_de_uno_real():
    ahora = datetime.datetime(2026, 1, 1)
    f = FallosDeCuentasInexistentes(seguridad.LIMITE_INTENTOS, seguridad.calcular_bloqueo)
    for _ in range(5):
        f.registrar("r", ahora)
    assert f.bloqueado_hasta("r", ahora) == ahora + datetime.timedelta(minutes=1)
    f.registrar("r", ahora)
    assert f.bloqueado_hasta("r", ahora) == ahora + datetime.timedelta(minutes=2)
    assert f.bloqueado_hasta("r", ahora + datetime.timedelta(minutes=3)) is None


def test_los_rut_inexistentes_no_llenan_la_memoria():
    f = FallosDeCuentasInexistentes(5, seguridad.calcular_bloqueo, max_claves=50)
    ahora = datetime.datetime(2026, 1, 1)
    for i in range(500):
        f.registrar(f"r{i}", ahora)
    assert len(f._estado) == 50


# --- Dirección real detrás del proxy ----------------------------------------------------------------------------------


def _pedido(host, cabeceras=None):
    return Request({"type": "http", "client": (host, 1234), "headers": [(k.lower().encode(), v.encode()) for k, v in (cabeceras or {}).items()]})


def test_sin_proxy_la_direccion_es_la_de_la_conexion(monkeypatch):
    monkeypatch.delenv("CABECERA_IP_CLIENTE", raising=False)
    assert str(ip_del_cliente(_pedido("93.184.216.34", {"X-IP-Cliente": "10.0.0.5"}))) == "93.184.216.34"


def test_detras_del_proxy_se_usa_la_cabecera_del_proxy(monkeypatch):
    monkeypatch.setenv("CABECERA_IP_CLIENTE", "X-IP-Cliente")
    assert str(ip_del_cliente(_pedido("172.18.0.3", {"X-IP-Cliente": "93.184.216.34"}))) == "93.184.216.34"


def test_la_cabecera_no_se_cree_si_la_conexion_no_viene_del_proxy(monkeypatch):
    monkeypatch.setenv("CABECERA_IP_CLIENTE", "X-IP-Cliente")
    assert str(ip_del_cliente(_pedido("93.184.216.34", {"X-IP-Cliente": "10.0.0.5"}))) == "93.184.216.34"


def test_si_el_proxy_no_manda_la_cabecera_o_viene_rota_no_se_sabe_quien_es(monkeypatch):
    monkeypatch.setenv("CABECERA_IP_CLIENTE", "X-IP-Cliente")
    assert ip_del_cliente(_pedido("172.18.0.3")) is None
    assert ip_del_cliente(_pedido("172.18.0.3", {"X-IP-Cliente": "no-es-una-ip"})) is None


def test_detras_del_proxy_un_pc_de_la_sala_es_local_y_uno_de_internet_no(monkeypatch):
    monkeypatch.setenv("CABECERA_IP_CLIENTE", "X-IP-Cliente")
    assert es_red_local(_pedido("172.18.0.3", {"X-IP-Cliente": "192.168.1.20"})) is True
    assert es_red_local(_pedido("172.18.0.3", {"X-IP-Cliente": "93.184.216.34"})) is False
    assert es_red_local(_pedido("172.18.0.3")) is False  # sin saber quién es, no se da por local


def test_detras_del_proxy_un_tunel_sigue_sin_parecer_local(monkeypatch):
    """Un túnel (cloudflared) llega al proxy desde la red de Docker y trae su propia cabecera: no es la red del colegio."""
    monkeypatch.setenv("CABECERA_IP_CLIENTE", "X-IP-Cliente")
    assert es_red_local(_pedido("172.18.0.3", {"X-IP-Cliente": "172.18.0.9", "CF-Connecting-IP": "93.184.216.34"})) is False


# --- Documentación de la API ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json"])
def test_sin_pedirlo_la_documentacion_de_la_api_no_se_publica(monkeypatch, ruta):
    monkeypatch.delenv("API_DOCS", raising=False)
    assert TestClient(crear_app()).get(ruta).status_code == 404


@pytest.mark.parametrize("ruta", ["/docs", "/redoc", "/openapi.json"])
def test_con_api_docs_la_documentacion_se_publica(monkeypatch, ruta):
    monkeypatch.setenv("API_DOCS", "1")
    assert TestClient(crear_app()).get(ruta).status_code == 200
