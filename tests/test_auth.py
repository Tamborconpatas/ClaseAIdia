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


# --- Regresiones de la auditoría de seguridad (2026-09-29, ver QA.md) ---


def _crear_curso(cliente, colegio_id, headers_utp):
    return cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()


def test_listar_cursos_no_expone_codigo(cliente, colegio_id, headers_utp):
    _crear_curso(cliente, colegio_id, headers_utp)
    cursos = cliente.get("/cursos").json()
    assert cursos and "codigo_invitacion" not in cursos[0]


def test_unirse_con_rut_de_staff_no_toma_la_cuenta(cliente, colegio_id, rut_utp, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": rut_utp, "nombre": "x", "pin": "123456"},
    )
    assert r.status_code == 409
    assert cliente.post("/auth/login/alumno", json={"rut": rut_utp, "pin": "123456"}).status_code == 401


def test_unirse_aplica_bloqueo_de_intentos(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    datos = {"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "123456"}
    assert cliente.post("/cursos/unirse", json=datos).status_code == 200

    for _ in range(5):
        assert cliente.post("/cursos/unirse", json={**datos, "pin": "000000"}).status_code == 401
    # Bloqueado: ni el PIN correcto entra, ni por unirse ni por login.
    assert cliente.post("/cursos/unirse", json=datos).status_code == 429
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "123456"}).status_code == 429


def test_utp_no_puede_escribir_en_otro_colegio(cliente, colegio_id, headers_utp):
    curso_a = _crear_curso(cliente, colegio_id, headers_utp)
    otro = cliente.post("/colegios", json={"nombre": "Otro"}).json()["id"]
    token_b = cliente.post(
        "/auth/bootstrap-utp", json={"rut": "1000005-K", "nombre": "UTP B", "password": "x", "colegio_id": otro}
    ).json()["access_token"]
    hb = {"Authorization": f"Bearer {token_b}"}

    r = cliente.post(
        "/usuarios",
        json={"rut": "11222333-9", "nombre": "i", "colegio_id": colegio_id, "roles": ["UTP"], "password": "x"},
        headers=hb,
    )
    assert r.status_code == 403
    assert cliente.post("/cursos", json={"nombre": "X", "colegio_id": colegio_id}, headers=hb).status_code == 403
    bloque = {"tipo": "RECREO", "dia_semana": 0, "hora_inicio": "10:00", "hora_fin": "10:15"}
    assert cliente.post(f"/cursos/{curso_a['id']}/bloques", json=bloque, headers=hb).status_code == 403
    assert all(u["colegio_id"] == otro for u in cliente.get("/usuarios", headers=hb).json())


def test_pin_debe_tener_6_digitos(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    for pin in ["", "12345", "1234567", "abcdef", "١٢٣٤٥٦"]:
        r = cliente.post(
            "/cursos/unirse",
            json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": pin},
        )
        assert r.status_code == 422, pin


def test_rut_con_puntos_es_la_misma_cuenta(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    datos = {"codigo_invitacion": curso["codigo_invitacion"], "nombre": "A", "pin": "123456"}
    cliente.post("/cursos/unirse", json={**datos, "rut": "11222333-9"})
    assert cliente.post("/cursos/unirse", json={**datos, "rut": "11.222.333-9", "pin": "999999"}).status_code == 401
    assert cliente.post("/auth/login/alumno", json={"rut": "11.222.333-9", "pin": "123456"}).status_code == 200


def test_alumno_no_ve_a_otros_usuarios(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    token = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "123456"},
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    yo = cliente.get("/usuarios", headers=headers_utp).json()
    id_alumno = next(u["id"] for u in yo if u["rut"] == "11222333-9")
    id_utp = next(u["id"] for u in yo if u["rut"] != "11222333-9")
    assert cliente.get(f"/usuarios/{id_alumno}", headers=h).status_code == 200
    assert cliente.get(f"/usuarios/{id_utp}", headers=h).status_code == 404
