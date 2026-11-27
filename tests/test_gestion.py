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
    assert set(cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["utp"]).json()[0]) == {"id", "nombre", "rut", "revisar_nombre"}


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
        json={"codigo_invitacion": nuevo["codigo_invitacion"], "rut": "21000004-6", "nombre": "Nuevo", "pin": "482915"},
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


# --- UTP: agregar, renombrar, quitar y mover alumnos -----------------------------------------------


def test_solo_el_utp_gestiona_alumnos(cliente, g):
    zoe = _id_de(cliente, g["utp"], "11222333-9")
    c = g["c8a"]
    assert cliente.put(f"/usuarios/{zoe}", json={"nombre": "Otro"}, headers=g["zoe"]).status_code == 403  # ni el propio alumno
    for quien in ("ana", "zoe"):
        assert cliente.delete(f"/cursos/{c}/alumnos/{zoe}", headers=g[quien]).status_code == 403
        assert cliente.post(f"/cursos/{c}/alumnos/{zoe}/mover", json={"curso_destino_id": g["c8b"]}, headers=g[quien]).status_code == 403


def test_utp_corrige_el_nombre_de_un_alumno(cliente, g):
    zoe = _id_de(cliente, g["utp"], "11222333-9")
    r = cliente.put(f"/usuarios/{zoe}", json={"nombre": "Zoé Rojas"}, headers=g["utp"])
    assert r.status_code == 200 and r.json()["nombre"] == "Zoé Rojas"
    assert cliente.put(f"/usuarios/{zoe}", json={"nombre": " "}, headers=g["utp"]).status_code == 422
    assert cliente.put("/usuarios/99999", json={"nombre": "X"}, headers=g["utp"]).status_code == 404


def test_utp_mueve_y_quita_alumnos(cliente, g):
    zoe = _id_de(cliente, g["utp"], "11222333-9")
    nombres = lambda c: [a["nombre"] for a in cliente.get(f"/cursos/{c}/alumnos", headers=g["utp"]).json()]  # noqa: E731
    assert cliente.post(f"/cursos/{g['c8a']}/alumnos/{zoe}/mover", json={"curso_destino_id": g["c8b"]}, headers=g["utp"]).status_code == 204
    assert nombres(g["c8a"]) == ["Bruno"] and nombres(g["c8b"]) == ["Carla", "Zoe"]
    # Ya no está en el origen: 404; mover al mismo curso: 409; destino inexistente: 404.
    assert cliente.post(f"/cursos/{g['c8a']}/alumnos/{zoe}/mover", json={"curso_destino_id": g["c8b"]}, headers=g["utp"]).status_code == 404
    assert cliente.post(f"/cursos/{g['c8b']}/alumnos/{zoe}/mover", json={"curso_destino_id": g["c8b"]}, headers=g["utp"]).status_code == 409
    assert cliente.post(f"/cursos/{g['c8b']}/alumnos/{zoe}/mover", json={"curso_destino_id": 99999}, headers=g["utp"]).status_code == 404
    assert cliente.delete(f"/cursos/{g['c8b']}/alumnos/{zoe}", headers=g["utp"]).status_code == 204
    assert nombres(g["c8b"]) == ["Carla"]
    assert cliente.delete(f"/cursos/{g['c8b']}/alumnos/{zoe}", headers=g["utp"]).status_code == 404
    # La cuenta se conserva: Zoe puede volver a unirse con el código del curso.
    assert cliente.get("/cursos", headers=g["zoe"]).json() == []


def test_un_rut_no_puede_estar_en_dos_cursos(cliente, g):
    codigo_8a = cliente.get(f"/cursos/{g['c8a']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]
    # Carla (8B) intenta unirse a 8A con el código: no. Si repite en su propio curso, simplemente entra.
    r = cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo_8a, "rut": "21000002-K", "nombre": "Carla", "pin": "482915"})
    assert r.status_code == 409 and "8B" in r.json()["detail"]
    assert cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["utp"]).json().__len__() == 2
    codigo_8b = cliente.get(f"/cursos/{g['c8b']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]
    r = cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo_8b, "rut": "21000002-K", "nombre": "Carla", "pin": "482915"})
    assert r.status_code == 200


def test_utp_elimina_un_alumno_pero_no_al_personal(cliente, g):
    zoe = _id_de(cliente, g["utp"], "11222333-9")
    ana = _id_de(cliente, g["utp"], "5126663-3")
    assert cliente.delete(f"/usuarios/{zoe}", headers=g["ana"]).status_code == 403
    assert cliente.delete(f"/usuarios/{ana}", headers=g["utp"]).status_code == 409
    assert cliente.delete(f"/usuarios/{zoe}", headers=g["utp"]).status_code == 204
    assert [a["nombre"] for a in cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["utp"]).json()] == ["Bruno"]
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "482915"}).status_code == 401
    assert cliente.delete(f"/usuarios/{zoe}", headers=g["utp"]).status_code == 404
    # Con el RUT libre, el alumno (o el UTP) puede volver a inscribirlo, esta vez en otro curso.
    codigo_8b = cliente.get(f"/cursos/{g['c8b']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]
    assert cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo_8b, "rut": "11222333-9", "nombre": "Zoe", "pin": "482915"}).status_code == 200


def test_rut_falso_y_nombre_inapropiado_se_rechazan_al_unirse(cliente, g):
    codigo = cliente.get(f"/cursos/{g['c8a']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]

    def unirse(rut, nombre):
        return cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo, "rut": rut, "nombre": nombre, "pin": "482915"})

    # RUT con dígito verificador válido pero falso: repetido, secuencia, o de otra generación.
    for falso in ("11111111-1", "12345678-5", "9999999-3"):
        assert unirse(falso, "Juan Soto").status_code == 422
    # Nombres: groserías (con trucos), símbolos y números.
    for malo in ("Juan Weon", "Pedro H.u.e.v.o.n", "Luis Cu1iao", "Ana Puuuta", "Admin Colegio", "Tito 123", "Juan 😀"):
        assert unirse("21000003-8", malo).status_code == 422, malo
    # Los nombres reales, con tilde, ñ y apostrofe/guion, pasan.
    assert unirse("21000003-8", "María José O'Higgins-Núñez").status_code == 200


def test_el_alumno_tiene_una_sola_sesion_a_la_vez(cliente, g):
    pin = {"rut": "11222333-9", "pin": "482915"}
    viejo = cliente.post("/auth/login/alumno", json=pin).json()["access_token"]
    assert cliente.get("/auth/me", headers={"Authorization": f"Bearer {viejo}"}).status_code == 200
    nuevo = cliente.post("/auth/login/alumno", json=pin).json()["access_token"]
    # Manda el equipo que entró último: el anterior queda cerrado.
    assert cliente.get("/auth/me", headers={"Authorization": f"Bearer {viejo}"}).status_code == 401
    assert cliente.get("/auth/me", headers={"Authorization": f"Bearer {nuevo}"}).status_code == 200


def test_el_utp_fija_el_maximo_de_alumnos_de_cada_curso(cliente, g):
    c = g["c8a"]  # tiene 2 alumnos; cursos nuevos parten con 45
    assert cliente.get(f"/cursos/{c}", headers=g["utp"]).json()["cupo"] == 45
    # Solo el UTP; no menos de 1, no más de 100, ni bajo los alumnos que ya tiene.
    for quien in ("ana", "zoe"):
        assert cliente.put(f"/cursos/{c}/cupo", json={"cupo": 30}, headers=g[quien]).status_code == 403
    for malo in (0, 101, -1):
        assert cliente.put(f"/cursos/{c}/cupo", json={"cupo": malo}, headers=g["utp"]).status_code == 422
    assert cliente.put(f"/cursos/{c}/cupo", json={"cupo": 1}, headers=g["utp"]).status_code == 409
    assert cliente.put(f"/cursos/{c}/cupo", json={"cupo": 3}, headers=g["utp"]).json()["cupo"] == 3

    codigo = cliente.get(f"/cursos/{c}/codigo", headers=g["utp"]).json()["codigo_invitacion"]

    def unirse(rut, nombre):
        return cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo, "rut": rut, "nombre": nombre, "pin": "482915"})

    assert unirse("21000003-8", "Tercero").status_code == 200
    lleno = unirse("21000004-6", "Cuarto")
    assert lleno.status_code == 409 and "lleno (3 alumnos)" in lleno.json()["detail"]
    # Quien ya está dentro sigue entrando; el UTP tampoco puede mover a un curso lleno, pero sí si sube el máximo.
    assert unirse("21000003-8", "Tercero").status_code == 200
    carla = _id_de(cliente, g["utp"], "21000002-K")
    mover = {"curso_destino_id": c}
    assert cliente.post(f"/cursos/{g['c8b']}/alumnos/{carla}/mover", json=mover, headers=g["utp"]).status_code == 409
    cliente.put(f"/cursos/{c}/cupo", json={"cupo": 4}, headers=g["utp"])
    assert cliente.post(f"/cursos/{g['c8b']}/alumnos/{carla}/mover", json=mover, headers=g["utp"]).status_code == 204


# --- Nombres que suenan a broma: aviso, confirmación y revisión del profesor -------------------------


def test_nombre_que_suena_a_broma_pide_confirmacion_y_queda_marcado(cliente, g):
    from nucleo.nombres import suena_a_broma

    for broma in ("Armando Casas", "armando  KASAS", "Alán Brito", "El Sapato", "Aquiles Vaeza", "Rosa Melo", "Débora Soto", "Alan Brito Soto"):
        assert suena_a_broma(broma), broma
    for normal in ("Juan Soto", "María Casas", "Armando Pérez", "Rosa Mella Díaz"):
        assert not suena_a_broma(normal), normal

    codigo = cliente.get(f"/cursos/{g['c8a']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]
    datos = {"codigo_invitacion": codigo, "rut": "21000003-8", "nombre": "Armando Casas", "pin": "482915"}
    # Sin confirmar: no se crea nada y se pide confirmar. Normal: entra directo y sin marca.
    assert cliente.post("/cursos/unirse", json=datos).status_code == 428
    assert cliente.post("/auth/login/alumno", json={"rut": "21000003-8", "pin": "482915"}).status_code == 401
    assert cliente.post("/cursos/unirse", json={**datos, "confirmar_nombre": True}).status_code == 200

    marcados = {a["nombre"]: a["revisar_nombre"] for a in cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["ana"]).json()}
    assert marcados == {"Armando Casas": True, "Bruno": False, "Zoe": False}
    # Al volver a entrar no se pregunta de nuevo ni se puede cambiar el nombre por su cuenta.
    otra = cliente.post("/cursos/unirse", json={**datos, "nombre": "Otro Nombre"})
    assert otra.status_code == 200
    nombres = [a["nombre"] for a in cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["utp"]).json()]
    assert "Armando Casas" in nombres and "Otro Nombre" not in nombres


def test_el_profesor_corrige_o_da_por_bueno_un_nombre_marcado(cliente, g):
    codigo = cliente.get(f"/cursos/{g['c8a']}/codigo", headers=g["utp"]).json()["codigo_invitacion"]
    cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo, "rut": "21000003-8", "nombre": "Alan Brito", "pin": "482915", "confirmar_nombre": True})
    cliente.post("/cursos/unirse", json={"codigo_invitacion": codigo, "rut": "21000004-6", "nombre": "Rosa Melo", "pin": "482915", "confirmar_nombre": True})
    por_rut = {a["rut"]: a for a in cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["ana"]).json()}
    alan, rosa = por_rut["21000003-8"]["id"], por_rut["21000004-6"]["id"]
    assert por_rut["21000003-8"]["revisar_nombre"] and por_rut["21000004-6"]["revisar_nombre"]

    # Ana dicta en 8A: corrige a Alan (queda sin marca) y da por buena a Rosa.
    assert cliente.put(f"/usuarios/{alan}", json={"nombre": "Alan Britos"}, headers=g["ana"]).status_code == 200
    assert cliente.post(f"/usuarios/{rosa}/nombre-revisado", headers=g["ana"]).status_code == 200
    despues = {a["rut"]: a for a in cliente.get(f"/cursos/{g['c8a']}/alumnos", headers=g["ana"]).json()}
    assert despues["21000003-8"]["nombre"] == "Alan Britos"
    assert not despues["21000003-8"]["revisar_nombre"] and not despues["21000004-6"]["revisar_nombre"]
    # Beto no dicta en 8A, el alumno no puede, y al personal no se le cambia el nombre por acá.
    assert cliente.put(f"/usuarios/{alan}", json={"nombre": "X Y"}, headers=g["beto"]).status_code == 404
    assert cliente.post(f"/usuarios/{rosa}/nombre-revisado", headers=g["beto"]).status_code == 404
    assert cliente.post(f"/usuarios/{rosa}/nombre-revisado", headers=g["zoe"]).status_code == 403
    ana = _id_de(cliente, g["utp"], "5126663-3")
    assert cliente.put(f"/usuarios/{ana}", json={"nombre": "Ana Z"}, headers=g["utp"]).status_code == 404
