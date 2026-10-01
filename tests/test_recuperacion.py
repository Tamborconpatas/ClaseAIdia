"""Recuperación de la contraseña del personal: código de un UTP, y la consola del servidor como último recurso."""
import datetime

import pytest

from scripts.restablecer_utp import ErrorRestablecer, restablecer_clave

CLAVE = "clave-segura-123"
NUEVA = "otra-clave-larga-9"


def _login(cliente, rut, password):
    return cliente.post("/auth/login/staff", json={"rut": rut, "password": password})


@pytest.fixture()
def p(cliente, colegio_id, headers_utp, rut_utp):
    """Un UTP (el del fixture), un profesor (Ana) y un segundo UTP (Beto)."""

    def crear(rut, nombre, rol):
        r = cliente.post(
            "/usuarios",
            json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": [rol], "password": CLAVE},
            headers=headers_utp,
        )
        assert r.status_code == 201
        return r.json()["id"]

    ids = {
        "ana": crear("5126663-3", "Ana", "PROFESOR"),
        "beto": crear("6000000-K", "Beto", "UTP"),
        "yo": next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["rut"] == rut_utp),
    }
    return {"c": cliente, "utp": headers_utp, "rut_utp": rut_utp, **ids}


def _resetear(p, usuario, headers=None):
    return p["c"].post(f"/usuarios/{p[usuario]}/reset-password", headers=headers or p["utp"])


# --- El UTP genera el código ---------------------------------------------------------------------


def test_el_utp_resetea_la_contraseña_de_un_profesor(p):
    r = _resetear(p, "ana")
    assert r.status_code == 200
    codigo = r.json()["codigo"]
    # La contraseña vieja deja de servir de inmediato.
    assert _login(p["c"], "5126663-3", CLAVE).status_code == 401
    # Con el código elige una nueva y entra.
    r = p["c"].post("/auth/restablecer-password", json={"rut": "5.126.663-3", "codigo": codigo.lower(), "password": NUEVA})
    assert r.status_code == 200 and r.json()["roles"] == ["PROFESOR"]
    assert _login(p["c"], "5126663-3", NUEVA).status_code == 200
    # Un solo uso.
    r = p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": "tercera-clave-77"})
    assert r.status_code == 401


def test_un_utp_puede_resetear_a_otro_utp(p):
    codigo = _resetear(p, "beto").json()["codigo"]
    r = p["c"].post("/auth/restablecer-password", json={"rut": "6000000-K", "codigo": codigo, "password": NUEVA})
    assert r.status_code == 200 and r.json()["roles"] == ["UTP"]


def test_nadie_resetea_su_propia_contraseña_ni_la_de_un_alumno(p, colegio_id):
    r = _resetear(p, "yo")
    assert r.status_code == 409 and "otro UTP" in r.json()["detail"]
    curso = p["c"].post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=p["utp"]).json()
    p["c"].post("/cursos/unirse", json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Zoe", "pin": "482915"})
    zoe = next(u["id"] for u in p["c"].get("/usuarios", headers=p["utp"]).json() if u["rut"] == "11222333-9")
    assert p["c"].post(f"/usuarios/{zoe}/reset-password", headers=p["utp"]).status_code == 409


def test_quien_puede_generar_el_codigo(p, otro_colegio):
    assert p["c"].post(f"/usuarios/{p['ana']}/reset-password").status_code == 401
    tp = {"Authorization": f"Bearer {_login(p['c'], '5126663-3', CLAVE).json()['access_token']}"}
    assert p["c"].post(f"/usuarios/{p['beto']}/reset-password", headers=tp).status_code == 403  # un profesor no
    assert p["c"].post(f"/usuarios/{p['ana']}/reset-password", headers=otro_colegio[1]).status_code == 404


# --- Usar el código ------------------------------------------------------------------------------


def test_el_codigo_vence_y_los_intentos_se_bloquean(p, monkeypatch):
    from interfaz.api import rutas_auth

    codigo = _resetear(p, "ana").json()["codigo"]
    en_16_min = rutas_auth.ahora_utc() + datetime.timedelta(minutes=16)
    monkeypatch.setattr(rutas_auth, "ahora_utc", lambda: en_16_min)
    assert p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": NUEVA}).status_code == 401
    monkeypatch.undo()

    codigo = _resetear(p, "ana").json()["codigo"]
    for _ in range(5):
        assert p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": "ZZZZZZ", "password": NUEVA}).status_code == 401
    # Bloqueado por intentos: ni el código bueno entra.
    assert p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": NUEVA}).status_code == 429


@pytest.mark.parametrize("password", ["corta", "a" * 129, "aaaaaaaaaaaa", "clave5126663clave"])
def test_la_contraseña_nueva_cumple_la_politica_y_no_gasta_el_codigo(p, password):
    codigo = _resetear(p, "ana").json()["codigo"]
    r = p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": password})
    assert r.status_code == 422 and password not in r.text
    assert p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": NUEVA}).status_code == 200


# --- Los códigos no se cruzan entre PIN (alumnos) y contraseña (personal) -------------------------


def test_el_codigo_de_personal_no_sirve_para_ponerse_un_pin(p):
    """Si sirviera, un profesor o UTP se dejaría una credencial de 6 dígitos en su cuenta."""
    codigo = _resetear(p, "ana").json()["codigo"]
    r = p["c"].post("/auth/restablecer-pin", json={"rut": "5126663-3", "codigo": codigo, "pin": "482915"})
    assert r.status_code == 401
    assert p["c"].post("/auth/login/alumno", json={"rut": "5126663-3", "pin": "482915"}).status_code == 401


def test_el_codigo_de_un_alumno_no_sirve_para_cambiar_una_contraseña(p, colegio_id):
    curso = p["c"].post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=p["utp"]).json()
    p["c"].post("/cursos/unirse", json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Zoe", "pin": "482915"})
    zoe = next(u["id"] for u in p["c"].get("/usuarios", headers=p["utp"]).json() if u["rut"] == "11222333-9")
    codigo = p["c"].post(f"/usuarios/{zoe}/reset-pin", headers=p["utp"]).json()["codigo"]
    r = p["c"].post("/auth/restablecer-password", json={"rut": "11222333-9", "codigo": codigo, "password": NUEVA})
    assert r.status_code == 401
    assert _login(p["c"], "11222333-9", NUEVA).status_code == 401  # el alumno no quedó con contraseña


def test_una_cuenta_de_personal_no_entra_por_el_login_de_alumno_aunque_tenga_pin(cliente, p):
    from infraestructura.modelos_orm import Usuario
    from infraestructura.seguridad import hashear_secreto

    with cliente.sesion() as db:
        db.get(Usuario, p["ana"]).pin_hash = hashear_secreto("482915")
        db.commit()
    assert cliente.post("/auth/login/alumno", json={"rut": "5126663-3", "pin": "482915"}).status_code == 401


# --- Último recurso: la consola del servidor -----------------------------------------------------


def test_la_consola_restablece_la_contraseña_de_un_utp_y_lo_desbloquea(cliente, p):
    for _ in range(5):
        _login(cliente, p["rut_utp"], "incorrecta")
    assert _login(cliente, p["rut_utp"], CLAVE).status_code == 429  # bloqueado
    with cliente.sesion() as db:
        assert restablecer_clave(db, p["rut_utp"], NUEVA).nombre == "UTP Test"
    assert _login(cliente, p["rut_utp"], CLAVE).status_code == 401  # la vieja ya no sirve
    assert _login(cliente, p["rut_utp"], NUEVA).status_code == 200  # y entra, sin esperar el bloqueo


@pytest.mark.parametrize(
    "rut, password",
    [
        ("12345678-9", NUEVA),  # RUT inválido
        ("11111111-1", NUEVA),  # no existe
        ("5126663-3", NUEVA),  # existe, pero es un profesor
        ("7654321-6", "corta"),  # contraseña débil
        ("7654321-6", "clave-7654321-xx"),  # contiene el RUT
    ],
)
def test_la_consola_rechaza_lo_que_no_corresponde_sin_cambiar_nada(cliente, p, rut, password):
    with cliente.sesion() as db:
        with pytest.raises(ErrorRestablecer):
            restablecer_clave(db, rut, password)
    assert _login(cliente, p["rut_utp"], CLAVE).status_code == 200  # la contraseña del UTP sigue igual
