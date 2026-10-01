def test_salud(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_disponible(cliente):
    r = cliente.get("/docs")
    assert r.status_code == 200


def test_obtener_colegio_propio(cliente, colegio_id, headers_utp):
    r = cliente.get(f"/colegios/{colegio_id}", headers=headers_utp)
    assert r.status_code == 200
    assert r.json() == {"id": colegio_id, "nombre": "Liceo de Prueba"}


def test_colegio_requiere_login_y_es_solo_el_propio(cliente, colegio_id, otro_colegio, headers_utp):
    assert cliente.get(f"/colegios/{colegio_id}").status_code == 401
    # Ajeno e inexistente dan lo mismo: no se revela qué ids existen.
    assert cliente.get(f"/colegios/{otro_colegio[0]}", headers=headers_utp).status_code == 404
    assert cliente.get("/colegios/9999", headers=headers_utp).status_code == 404


def test_ya_no_se_puede_crear_ni_listar_colegios_por_api(cliente, headers_utp):
    assert cliente.post("/colegios", json={"nombre": "X"}, headers=headers_utp).status_code == 404
    assert cliente.get("/colegios", headers=headers_utp).status_code == 404


def test_crear_curso_sin_token_rechaza(cliente, colegio_id):
    r = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id})
    assert r.status_code == 401


def test_crear_curso_genera_codigo_invitacion(cliente, colegio_id, headers_utp):
    r = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp)
    assert r.status_code == 201
    curso = r.json()
    assert len(curso["codigo_invitacion"]) == 6


def test_crear_curso_en_otro_colegio_rechaza(cliente, headers_utp):
    r = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": 9999}, headers=headers_utp)
    assert r.status_code == 403


def test_crear_bloque_bajo_curso(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()

    r = cliente.post(
        f"/cursos/{curso['id']}/bloques",
        json={
            "tipo": "CLASE",
            "asignatura": "Matematica",
            "dia_semana": 0,
            "hora_inicio": "08:00:00",
            "hora_fin": "08:45:00",
        },
        headers=headers_utp,
    )
    assert r.status_code == 201
    bloque = r.json()
    assert bloque["curso_id"] == curso["id"]

    r = cliente.get(f"/cursos/{curso['id']}/bloques", headers=headers_utp)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_crear_bloque_con_profesor_inexistente_falla(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()

    r = cliente.post(
        f"/cursos/{curso['id']}/bloques",
        json={
            "tipo": "CLASE",
            "asignatura": "Matematica",
            "profesor_id": 9999,
            "dia_semana": 0,
            "hora_inicio": "08:00:00",
            "hora_fin": "08:45:00",
        },
        headers=headers_utp,
    )
    assert r.status_code == 409


def test_crear_bloque_dia_semana_invalido(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()

    r = cliente.post(
        f"/cursos/{curso['id']}/bloques",
        json={"tipo": "RECREO", "dia_semana": 7, "hora_inicio": "10:00:00", "hora_fin": "10:15:00"},
        headers=headers_utp,
    )
    assert r.status_code == 422


def test_crear_usuario_sin_token_rechaza(cliente, colegio_id, rut_valido):
    r = cliente.post(
        "/usuarios",
        json={"rut": rut_valido, "nombre": "Profe", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": "clave-segura-123"},
    )
    assert r.status_code == 401


def test_crear_usuario_con_roles(cliente, colegio_id, rut_valido, headers_utp):
    r = cliente.post(
        "/usuarios",
        json={
            "rut": rut_valido,
            "nombre": "Profe Test",
            "colegio_id": colegio_id,
            "roles": ["PROFESOR"],
            "password": "clave-segura-123",
        },
        headers=headers_utp,
    )
    assert r.status_code == 201
    usuario = r.json()
    assert usuario["roles"] == ["PROFESOR"]


def test_crear_usuario_rol_alumno_rechazado(cliente, colegio_id, rut_valido, headers_utp):
    r = cliente.post(
        "/usuarios",
        json={
            "rut": rut_valido,
            "nombre": "Alumno Colado",
            "colegio_id": colegio_id,
            "roles": ["ALUMNO"],
            "password": "clave-segura-123",
        },
        headers=headers_utp,
    )
    assert r.status_code == 422


def test_crear_usuario_rut_invalido_rechaza(cliente, colegio_id, headers_utp):
    r = cliente.post(
        "/usuarios",
        json={
            "rut": "12345678-9",
            "nombre": "Malo",
            "colegio_id": colegio_id,
            "roles": ["PROFESOR"],
            "password": "clave-segura-123",
        },
        headers=headers_utp,
    )
    assert r.status_code == 422


def test_crear_usuario_rut_duplicado_falla(cliente, colegio_id, rut_valido, headers_utp):
    datos = {
        "rut": rut_valido,
        "nombre": "Uno",
        "colegio_id": colegio_id,
        "roles": ["PROFESOR"],
        "password": "clave-segura-123",
    }
    assert cliente.post("/usuarios", json=datos, headers=headers_utp).status_code == 201

    datos["nombre"] = "Otro"
    r = cliente.post("/usuarios", json=datos, headers=headers_utp)
    assert r.status_code == 409


def test_crear_usuario_en_otro_colegio_rechaza(cliente, rut_valido, headers_utp):
    r = cliente.post(
        "/usuarios",
        json={
            "rut": rut_valido,
            "nombre": "Sin Colegio",
            "colegio_id": 9999,
            "roles": ["PROFESOR"],
            "password": "clave-segura-123",
        },
        headers=headers_utp,
    )
    assert r.status_code == 403


def test_obtener_usuario_sin_token_rechaza(cliente):
    r = cliente.get("/usuarios/9999")
    assert r.status_code == 401


def test_obtener_usuario_inexistente(cliente, headers_utp):
    r = cliente.get("/usuarios/9999", headers=headers_utp)
    assert r.status_code == 404
