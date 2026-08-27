def test_bootstrap_utp_crea_primer_usuario(cliente, colegio_id, rut_utp):
    r = cliente.post(
        "/auth/bootstrap-utp",
        json={"rut": rut_utp, "nombre": "UTP Test", "password": "clave-segura-123", "colegio_id": colegio_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["roles"] == ["UTP"]
    assert "access_token" in body


def test_bootstrap_utp_segunda_vez_falla(cliente, colegio_id, rut_utp, token_utp):
    r = cliente.post(
        "/auth/bootstrap-utp",
        json={"rut": "1000005-K", "nombre": "Otro UTP", "password": "clave-segura-123", "colegio_id": colegio_id},
    )
    assert r.status_code == 409


def test_login_staff_exitoso(cliente, colegio_id, rut_utp, token_utp):
    r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "clave-segura-123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_staff_password_incorrecta(cliente, rut_utp, token_utp):
    r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "incorrecta"})
    assert r.status_code == 401


def test_login_staff_rut_inexistente(cliente):
    r = cliente.post("/auth/login/staff", json={"rut": "11222333-9", "password": "lo-que-sea"})
    assert r.status_code == 401


def test_login_staff_bloqueo_tras_intentos_fallidos(cliente, rut_utp, token_utp):
    for _ in range(5):
        r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "incorrecta"})
        assert r.status_code == 401

    # Al 5to fallo ya debería estar bloqueado — incluso con la password correcta.
    r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "clave-segura-123"})
    assert r.status_code == 429


def test_unirse_curso_crea_alumno_nuevo(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()

    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "123456"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["roles"] == ["ALUMNO"]


def test_unirse_a_segundo_curso_con_pin_correcto(cliente, colegio_id, headers_utp):
    curso1 = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    curso2 = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()

    datos = {"rut": "11222333-9", "nombre": "Alumno Uno", "pin": "123456"}
    r1 = cliente.post("/cursos/unirse", json={**datos, "codigo_invitacion": curso1["codigo_invitacion"]})
    assert r1.status_code == 200

    r2 = cliente.post("/cursos/unirse", json={**datos, "codigo_invitacion": curso2["codigo_invitacion"]})
    assert r2.status_code == 200


def test_unirse_con_pin_incorrecto_sobre_cuenta_existente_falla(cliente, colegio_id, headers_utp):
    curso1 = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    curso2 = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()

    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso1["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "123456"},
    )
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso2["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "000000"},
    )
    assert r.status_code == 401


def test_unirse_con_codigo_invalido_falla(cliente):
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": "NOEXISTE", "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "123456"},
    )
    assert r.status_code == 404


def test_alumno_no_puede_crear_curso(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    ingreso = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "123456"},
    )
    headers_alumno = {"Authorization": f"Bearer {ingreso.json()['access_token']}"}

    r = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_alumno)
    assert r.status_code == 403
