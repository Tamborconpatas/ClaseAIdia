def test_salud(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_disponible(cliente):
    r = cliente.get("/docs")
    assert r.status_code == 200


def test_crear_y_listar_colegio(cliente):
    r = cliente.post("/colegios", json={"nombre": "Liceo A"})
    assert r.status_code == 201
    colegio = r.json()
    assert colegio["nombre"] == "Liceo A"

    r = cliente.get("/colegios")
    assert r.status_code == 200
    assert any(c["id"] == colegio["id"] for c in r.json())


def test_obtener_colegio_inexistente(cliente):
    r = cliente.get("/colegios/9999")
    assert r.status_code == 404


def test_crear_curso_genera_codigo_invitacion(cliente, colegio_id):
    r = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id})
    assert r.status_code == 201
    curso = r.json()
    assert len(curso["codigo_invitacion"]) == 6


def test_crear_curso_con_colegio_inexistente_falla(cliente):
    r = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": 9999})
    assert r.status_code == 409


def test_crear_bloque_bajo_curso(cliente, colegio_id):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}).json()

    r = cliente.post(
        f"/cursos/{curso['id']}/bloques",
        json={
            "tipo": "CLASE",
            "asignatura": "Matematica",
            "dia_semana": 0,
            "hora_inicio": "08:00:00",
            "hora_fin": "08:45:00",
        },
    )
    assert r.status_code == 201
    bloque = r.json()
    assert bloque["curso_id"] == curso["id"]

    r = cliente.get(f"/cursos/{curso['id']}/bloques")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_crear_bloque_con_profesor_inexistente_falla(cliente, colegio_id):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}).json()

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
    )
    assert r.status_code == 409


def test_crear_bloque_dia_semana_invalido(cliente, colegio_id):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}).json()

    r = cliente.post(
        f"/cursos/{curso['id']}/bloques",
        json={"tipo": "RECREO", "dia_semana": 7, "hora_inicio": "10:00:00", "hora_fin": "10:15:00"},
    )
    assert r.status_code == 422


def test_crear_usuario_con_roles(cliente, colegio_id, rut_valido):
    r = cliente.post(
        "/usuarios",
        json={"rut": rut_valido, "nombre": "Profe Test", "colegio_id": colegio_id, "roles": ["PROFESOR"]},
    )
    assert r.status_code == 201
    usuario = r.json()
    assert usuario["roles"] == ["PROFESOR"]


def test_crear_usuario_rut_invalido_rechaza(cliente, colegio_id):
    r = cliente.post(
        "/usuarios",
        json={"rut": "12345678-9", "nombre": "Malo", "colegio_id": colegio_id, "roles": []},
    )
    assert r.status_code == 422


def test_crear_usuario_rut_duplicado_falla(cliente, colegio_id, rut_valido):
    datos = {"rut": rut_valido, "nombre": "Uno", "colegio_id": colegio_id, "roles": []}
    assert cliente.post("/usuarios", json=datos).status_code == 201

    datos["nombre"] = "Otro"
    r = cliente.post("/usuarios", json=datos)
    assert r.status_code == 409


def test_crear_usuario_colegio_inexistente_falla(cliente, rut_valido):
    r = cliente.post(
        "/usuarios",
        json={"rut": rut_valido, "nombre": "Sin Colegio", "colegio_id": 9999, "roles": []},
    )
    assert r.status_code == 409


def test_obtener_usuario_inexistente(cliente):
    r = cliente.get("/usuarios/9999")
    assert r.status_code == 404
