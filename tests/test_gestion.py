# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Gestión del UTP y del profesor: alumnos por curso, renombrar/borrar cursos y resetear PIN."""
import pytest


def _login(cliente, rut, password="clave-segura-123"):
    r = cliente.post("/auth/login/staff", json={"rut": rut, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def g(cliente, colegio_id, headers_utp):
    """8A (Ana dicta, con 2 alumnos: Zoe y Bruno) y 8B (solo Beto dicta, con 1 alumno: Carla)."""

    def profesor(rut, nombre):
        r = cliente.post(
            "/usuarios",
            json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": "clave-segura-123"},
            headers=headers_utp,
        )
        return r.json()["id"]

    ana, beto = profesor("5126663-3", "Ana"), profesor("6000000-K", "Beto")
    c8a = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    c8b = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()
    for curso, prof, dia in ((c8a, ana, 0), (c8b, beto, 1)):
        b = {"tipo": "CLASE", "asignatura": "Mat", "profesor_id": prof, "dia_semana": dia, "hora_inicio": "08:00", "hora_fin": "08:45"}
        assert cliente.post(f"/cursos/{curso['id']}/bloques", json=b, headers=headers_utp).status_code == 201

    def alumno(curso, rut, nombre):
        r = cliente.post(
            "/cursos/unirse",
            json={"codigo_invitacion": curso["codigo_invitacion"], "rut": rut, "nombre": nombre, "pin": "482915"},
        )
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return {
        "utp": headers_utp,
        "c8a": c8a["id"],
        "c8b": c8b["id"],
        "ana": _login(cliente, "5126663-3"),
        "beto": _login(cliente, "6000000-K"),
        "zoe": alumno(c8a, "11222333-9", "Zoe"),
        "bruno": alumno(c8a, "21000001-1", "Bruno"),
        "carla": alumno(c8b, "21000002-K", "Carla"),
    }


def _id_de(cliente, headers, rut):
    return next(u["id"] for u in cliente.get("/usuarios", headers=headers).json() if u["rut"] == rut)


# --- Alumnos del curso ---------------------------------------------------------------------------


def test_alumnos_del_curso_ordenados_por_nombre(cliente, g):
    for quien in ("utp", "ana"):
        r = cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g[quien])
        assert r.status_code == 200
        assert [(a["nombre"], a["rut"]) for a in r.json()] == [("Bruno", "21000001-1"), ("Zoe", "11222333-9")]
    # Solo lo necesario: nada de hashes ni de datos de acceso.
    assert set(cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["utp"]).json()[0]) == {"id", "nombre", "rut"}


def test_quien_ve_los_alumnos_de_un_curso(cliente, g, otro_colegio):
    ruta = f"/cursos/{g['c8a']}/alumnos"
    assert cliente.get(ruta).status_code == 401
    assert cliente.get(ruta, headers=g["zoe"]).status_code == 403  # un alumno no ve a sus compañeros
    assert cliente.get(ruta, headers=g["beto"]).status_code == 404  # un profesor que no dicta ahí
    assert cliente.get(ruta, headers=otro_colegio[1]).status_code == 404


# --- Resetear PIN: el profesor solo a los alumnos de sus cursos -----------------------------------


def test_el_profesor_resetea_el_pin_solo_de_sus_alumnos(cliente, g):
    zoe, carla = _id_de(cliente, g["utp"], "11222333-9"), _id_de(cliente, g["utp"], "21000002-K")
    assert cliente.post(f"/usuarios/{zoe}/reset-pin", headers=g["ana"]).status_code == 200
    assert cliente.post(f"/usuarios/{carla}/reset-pin", headers=g["ana"]).status_code == 404  # alumna de 8B
    # El UTP puede con cualquiera.
    assert cliente.post(f"/usuarios/{carla}/reset-pin", headers=g["utp"]).status_code == 200


# --- Renombrar y borrar cursos --------------------------------------------------------------------


def test_renombrar_un_curso(cliente, g):
    r = cliente.put(f"/cursos/{g['c8a']}", json={"nombre": "  8°A  "}, headers=g["utp"])
    assert r.status_code == 200 and r.json()["nombre"] == "8°A"
    assert cliente.put(f"/cursos/{g['c8a']}", json={"nombre": "   "}, headers=g["utp"]).status_code == 422
    assert cliente.put(f"/cursos/{g['c8a']}", json={"nombre": "x" * 61}, headers=g["utp"]).status_code == 422


def test_solo_se_borra_un_curso_vacio(cliente, g, colegio_id):
    assert cliente.delete(f"/cursos/{g['c8a']}", headers=g["utp"]).status_code == 409  # tiene bloques y alumnos
    nuevo = cliente.post("/cursos", json={"nombre": "9A", "colegio_id": colegio_id}, headers=g["utp"]).json()
    # Con un alumno inscrito pero sin bloques tampoco.
    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": nuevo["codigo_invitacion"], "rut": "11222333-9", "nombre": "Zoe", "pin": "482915"},
    )
    assert cliente.delete(f"/cursos/{nuevo['id']}", headers=g["utp"]).status_code == 409
    vacio = cliente.post("/cursos", json={"nombre": "9B", "colegio_id": colegio_id}, headers=g["utp"]).json()
    assert cliente.delete(f"/cursos/{vacio['id']}", headers=g["utp"]).status_code == 204
    assert cliente.get(f"/cursos/{vacio['id']}", headers=g["utp"]).status_code == 404


def test_quien_puede_renombrar_o_borrar_cursos(cliente, g, otro_colegio):
    ruta = f"/cursos/{g['c8a']}"
    for llamar, cuerpo in ((cliente.put, {"json": {"nombre": "X"}}), (cliente.delete, {})):
        assert llamar(ruta, **cuerpo).status_code == 401
        assert llamar(ruta, headers=g["ana"], **cuerpo).status_code == 403
        assert llamar(ruta, headers=otro_colegio[1], **cuerpo).status_code == 404
