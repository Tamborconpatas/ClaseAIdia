# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Desactivar al personal que se fue: no entra (ni con la sesión abierta), conserva su historial, se puede reactivar."""
import datetime

import pytest

from infraestructura.seguridad import ahora_utc, hashear_secreto

CLAVE = "clave-segura-123"


def _login(cliente, rut, password=CLAVE):
    return cliente.post("/auth/login/staff", json={"rut": rut, "password": password})


@pytest.fixture()
def p(cliente, colegio_id, headers_utp, rut_utp):
    """El UTP del fixture, una profesora (Ana, con un bloque en 8A), un segundo UTP (Beto) y un alumno."""

    def crear(rut, nombre, rol):
        r = cliente.post(
            "/usuarios",
            json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": [rol], "password": CLAVE},
            headers=headers_utp,
        )
        assert r.status_code == 201
        return r.json()["id"]

    ana, beto = crear("5126663-3", "Ana", "PROFESOR"), crear("6000000-K", "Beto", "UTP")
    c = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    curso = c["id"]
    cliente.post("/cursos/unirse", json={"codigo_invitacion": c["codigo_invitacion"], "rut": "11222333-9", "nombre": "Luis", "pin": "482915"})
    usuarios = cliente.get("/usuarios", headers=headers_utp).json()
    yo, alumno = (next(u["id"] for u in usuarios if u["rut"] == r) for r in (rut_utp, "11222333-9"))
    bloque = {"tipo": "CLASE", "asignatura": "Matemática", "profesor_id": ana, "sala": "S1", "dia_semana": 0, "hora_inicio": "08:00", "hora_fin": "08:45"}
    r = cliente.post(f"/cursos/{curso}/bloques", json=bloque, headers=headers_utp)
    assert r.status_code == 201
    return {"c": cliente, "u": headers_utp, "ana": ana, "beto": beto, "alumno": alumno, "yo": yo, "curso": curso, "bloque": r.json()["id"], "datos_bloque": bloque}


def _desactivar(p, quien, headers=None):
    return p["c"].post(f"/usuarios/{p[quien]}/desactivar", headers=headers or p["u"])


def test_el_utp_desactiva_y_reactiva_a_un_profesor(p):
    r = _desactivar(p, "ana")
    assert r.status_code == 200 and r.json()["activo"] is False
    listado = {u["nombre"]: u["activo"] for u in p["c"].get("/usuarios", headers=p["u"]).json()}
    assert listado["Ana"] is False and listado["Beto"] is True
    r = p["c"].post(f"/usuarios/{p['ana']}/activar", headers=p["u"])
    assert r.status_code == 200 and r.json()["activo"] is True
    assert _login(p["c"], "5126663-3").status_code == 200


def test_una_cuenta_desactivada_no_puede_entrar(p):
    _desactivar(p, "ana")
    r = _login(p["c"], "5126663-3")  # con la clave correcta
    assert r.status_code == 401 and r.json()["detail"] == "Credenciales inválidas"  # igual que una clave mala: no delata nada


def test_la_sesion_abierta_se_corta_al_desactivar(p):
    token = _login(p["c"], "5126663-3").json()["access_token"]
    h_ana = {"Authorization": f"Bearer {token}"}
    assert p["c"].get("/auth/me", headers=h_ana).status_code == 200
    _desactivar(p, "ana")
    r = p["c"].get("/auth/me", headers=h_ana)
    assert r.status_code == 401 and r.json()["detail"] == "Cuenta desactivada"
    assert p["c"].get("/cursos", headers=h_ana).status_code == 401


def test_un_utp_desactivado_tampoco_entra(p):
    _desactivar(p, "beto")
    assert _login(p["c"], "6000000-K").status_code == 401


def test_solo_un_utp_puede_desactivar(p):
    h_ana = {"Authorization": f"Bearer {_login(p['c'], '5126663-3').json()['access_token']}"}
    assert _desactivar(p, "beto", headers=h_ana).status_code == 403
    assert p["c"].post(f"/usuarios/{p['beto']}/activar", headers=h_ana).status_code == 403


def test_un_utp_no_se_desactiva_a_si_mismo_asi_siempre_queda_uno(p):
    r = _desactivar(p, "yo")
    assert r.status_code == 409
    assert p["c"].get("/auth/me", headers=p["u"]).status_code == 200


def test_no_se_desactiva_a_un_alumno_ni_a_gente_de_otro_colegio(p, otro_colegio):
    assert _desactivar(p, "alumno").status_code == 409
    _, h_otro = otro_colegio
    assert _desactivar(p, "ana", headers=h_otro).status_code == 404  # no revela que existe
    assert p["c"].post("/usuarios/9999/desactivar", headers=p["u"]).status_code == 404


def test_desactivar_no_borra_su_historial_pero_no_se_le_asignan_bloques_nuevos(p):
    _desactivar(p, "ana")
    bloques = p["c"].get(f"/cursos/{p['curso']}/bloques", headers=p["u"]).json()
    assert [b["profesor_nombre"] for b in bloques] == ["Ana"]  # su nombre sigue en el horario
    nuevo = {**p["datos_bloque"], "dia_semana": 2}
    assert p["c"].post(f"/cursos/{p['curso']}/bloques", json=nuevo, headers=p["u"]).status_code == 409
    # Pero se puede seguir editando la hora de un bloque que ya era suyo.
    editado = {**p["datos_bloque"], "hora_fin": "09:00"}
    assert p["c"].put(f"/bloques/{p['bloque']}", json=editado, headers=p["u"]).status_code == 200
    # Y moverlo a otro profesor activo también.
    assert p["c"].put(f"/bloques/{p['bloque']}", json={**editado, "profesor_id": p["beto"]}, headers=p["u"]).status_code == 409  # Beto es UTP, no profesor


def test_un_codigo_de_reset_pendiente_no_sirve_en_una_cuenta_desactivada(p):
    from infraestructura.modelos_orm import Usuario

    codigo = p["c"].post(f"/usuarios/{p['ana']}/reset-password", headers=p["u"]).json()["codigo"]
    _desactivar(p, "ana")
    with p["c"].sesion() as db:  # desactivar ya borra el código; se deja uno puesto para probar la defensa de la ruta por sí sola
        ana = db.get(Usuario, p["ana"])
        ana.codigo_reset_hash = hashear_secreto(codigo)
        ana.codigo_reset_vence = ahora_utc() + datetime.timedelta(minutes=10)
        db.commit()
    r = p["c"].post("/auth/restablecer-password", json={"rut": "5126663-3", "codigo": codigo, "password": "otra-clave-larga-9"})
    assert r.status_code == 401
    p["c"].post(f"/usuarios/{p['ana']}/activar", headers=p["u"])
    assert _login(p["c"], "5126663-3", "otra-clave-larga-9").status_code == 401  # tampoco quedó con esa contraseña


def test_desactivar_borra_el_codigo_de_reset_pendiente(p):
    from infraestructura.modelos_orm import Usuario

    p["c"].post(f"/usuarios/{p['ana']}/reset-password", headers=p["u"])
    _desactivar(p, "ana")
    with p["c"].sesion() as db:
        assert db.get(Usuario, p["ana"]).codigo_reset_hash is None
