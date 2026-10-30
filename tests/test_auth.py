# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

def test_setup_crea_colegio_y_primer_utp(cliente, rut_utp):
    r = cliente.post(
        "/auth/setup",
        json={"colegio_nombre": "Liceo Nuevo", "rut": rut_utp, "nombre": "UTP Test", "password": "clave-segura-123"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["roles"] == ["UTP"]
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert cliente.get(f"/colegios/{body['colegio_id']}", headers=headers).json()["nombre"] == "Liceo Nuevo"


def test_setup_se_cierra_tras_la_primera_vez(cliente, setup_inicial):
    r = cliente.post(
        "/auth/setup",
        json={"colegio_nombre": "Otro", "rut": "1000005-K", "nombre": "Intruso", "password": "clave-segura-123"},
    )
    assert r.status_code == 409
    assert cliente.post("/auth/login/staff", json={"rut": "1000005-K", "password": "clave-segura-123"}).status_code == 401


def test_setup_valida_rut(cliente):
    r = cliente.post(
        "/auth/setup",
        json={"colegio_nombre": "L", "rut": "12345678-9", "nombre": "U", "password": "clave-segura-123"},
    )
    assert r.status_code == 422


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
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "482915"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["roles"] == ["ALUMNO"]


def test_unirse_a_segundo_curso_con_pin_correcto(cliente, colegio_id, headers_utp):
    curso1 = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    curso2 = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()

    datos = {"rut": "11222333-9", "nombre": "Alumno Uno", "pin": "482915"}
    r1 = cliente.post("/cursos/unirse", json={**datos, "codigo_invitacion": curso1["codigo_invitacion"]})
    assert r1.status_code == 200

    r2 = cliente.post("/cursos/unirse", json={**datos, "codigo_invitacion": curso2["codigo_invitacion"]})
    assert r2.status_code == 200


def test_unirse_con_pin_incorrecto_sobre_cuenta_existente_falla(cliente, colegio_id, headers_utp):
    curso1 = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    curso2 = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()

    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso1["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "482915"},
    )
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso2["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "000000"},
    )
    assert r.status_code == 401


def test_unirse_con_codigo_invalido_falla(cliente):
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": "NOEXISTE", "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "482915"},
    )
    assert r.status_code == 404


def test_alumno_no_puede_crear_curso(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    ingreso = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alumno Uno", "pin": "482915"},
    )
    headers_alumno = {"Authorization": f"Bearer {ingreso.json()['access_token']}"}

    r = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_alumno)
    assert r.status_code == 403


# --- Regresiones de la auditoría de seguridad (2026-09-29, ver QA.md) ---


def _crear_curso(cliente, colegio_id, headers_utp):
    return cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()


def test_listar_cursos_no_expone_codigo(cliente, colegio_id, headers_utp):
    _crear_curso(cliente, colegio_id, headers_utp)
    cursos = cliente.get("/cursos", headers=headers_utp).json()
    assert cursos and "codigo_invitacion" not in cursos[0]


def test_unirse_con_rut_de_staff_no_toma_la_cuenta(cliente, colegio_id, rut_utp, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": rut_utp, "nombre": "x", "pin": "482915"},
    )
    assert r.status_code == 409
    assert cliente.post("/auth/login/alumno", json={"rut": rut_utp, "pin": "482915"}).status_code == 401


def test_unirse_aplica_bloqueo_de_intentos(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    datos = {"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "482915"}
    assert cliente.post("/cursos/unirse", json=datos).status_code == 200

    for _ in range(5):
        assert cliente.post("/cursos/unirse", json={**datos, "pin": "000000"}).status_code == 401
    # Bloqueado: ni el PIN correcto entra, ni por unirse ni por login.
    assert cliente.post("/cursos/unirse", json=datos).status_code == 429
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "482915"}).status_code == 429


def test_utp_no_puede_escribir_en_otro_colegio(cliente, colegio_id, headers_utp, otro_colegio):
    curso_a = _crear_curso(cliente, colegio_id, headers_utp)
    otro, hb = otro_colegio

    r = cliente.post(
        "/usuarios",
        json={"rut": "11222333-9", "nombre": "i", "colegio_id": colegio_id, "roles": ["UTP"], "password": "clave-segura-123"},
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
    datos = {"codigo_invitacion": curso["codigo_invitacion"], "nombre": "A", "pin": "482915"}
    cliente.post("/cursos/unirse", json={**datos, "rut": "11222333-9"})
    assert cliente.post("/cursos/unirse", json={**datos, "rut": "11.222.333-9", "pin": "999999"}).status_code == 401
    assert cliente.post("/auth/login/alumno", json={"rut": "11.222.333-9", "pin": "482915"}).status_code == 200


def test_alumno_no_ve_a_otros_usuarios(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    token = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "482915"},
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    yo = cliente.get("/usuarios", headers=headers_utp).json()
    id_alumno = next(u["id"] for u in yo if u["rut"] == "11222333-9")
    id_utp = next(u["id"] for u in yo if u["rut"] != "11222333-9")
    assert cliente.get(f"/usuarios/{id_alumno}", headers=h).status_code == 200
    assert cliente.get(f"/usuarios/{id_utp}", headers=h).status_code == 404


# --- Reseteo de PIN por staff ---


def _alumno_con_id(cliente, colegio_id, headers_utp, pin="482915"):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": pin},
    )
    return next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["rut"] == "11222333-9")


def _resetear(cliente, id_alumno, headers_utp):
    r = cliente.post(f"/usuarios/{id_alumno}/reset-pin", headers=headers_utp)
    assert r.status_code == 200
    return r.json()["codigo"]


def test_reset_pin_con_codigo_de_un_solo_uso(cliente, colegio_id, headers_utp):
    id_alumno = _alumno_con_id(cliente, colegio_id, headers_utp)
    # Bloqueado por intentos fallidos: el reseteo también lo desbloquea.
    for _ in range(5):
        cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "000000"})

    codigo = _resetear(cliente, id_alumno, headers_utp)
    datos = {"rut": "11.222.333-9", "codigo": codigo.lower(), "pin": "730164"}
    assert cliente.post("/auth/restablecer-pin", json=datos).status_code == 200
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "730164"}).status_code == 200
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "482915"}).status_code == 401
    # Un solo uso.
    assert cliente.post("/auth/restablecer-pin", json={**datos, "pin": "111111"}).status_code == 401


def test_tras_reset_saber_el_rut_no_alcanza(cliente, colegio_id, headers_utp):
    """El riesgo que motivó el código: entre el reseteo y el alumno, alguien con
    solo el RUT (o además el código del curso) no puede fijar el PIN."""
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "482915"},
    )
    id_alumno = next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["rut"] == "11222333-9")
    codigo = _resetear(cliente, id_alumno, headers_utp)

    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "999999"}).status_code == 401
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "999999"},
    )
    assert r.status_code == 409
    # Adivinar el código cuenta intentos: al 5° queda bloqueado, ni el código real entra.
    for _ in range(5):
        cliente.post("/auth/restablecer-pin", json={"rut": "11222333-9", "codigo": "ZZZZZZ", "pin": "999999"})
    r = cliente.post("/auth/restablecer-pin", json={"rut": "11222333-9", "codigo": codigo, "pin": "999999"})
    assert r.status_code == 429


def test_codigo_reset_vencido(cliente, colegio_id, headers_utp, monkeypatch):
    import datetime

    from interfaz.api import rutas_auth

    id_alumno = _alumno_con_id(cliente, colegio_id, headers_utp)
    codigo = _resetear(cliente, id_alumno, headers_utp)
    en_16_min = rutas_auth.ahora_utc() + datetime.timedelta(minutes=16)
    monkeypatch.setattr(rutas_auth, "ahora_utc", lambda: en_16_min)
    r = cliente.post("/auth/restablecer-pin", json={"rut": "11222333-9", "codigo": codigo, "pin": "730164"})
    assert r.status_code == 401


def test_reset_pin_solo_staff_del_mismo_colegio(cliente, colegio_id, headers_utp, otro_colegio):
    id_alumno = _alumno_con_id(cliente, colegio_id, headers_utp)
    token_alumno = cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "482915"}).json()["access_token"]
    r = cliente.post(f"/usuarios/{id_alumno}/reset-pin", headers={"Authorization": f"Bearer {token_alumno}"})
    assert r.status_code == 403

    r = cliente.post(f"/usuarios/{id_alumno}/reset-pin", headers=otro_colegio[1])
    assert r.status_code == 404


def test_reset_pin_no_aplica_a_staff(cliente, rut_utp, headers_utp):
    id_utp = cliente.get("/usuarios", headers=headers_utp).json()[0]["id"]
    assert cliente.post(f"/usuarios/{id_utp}/reset-pin", headers=headers_utp).status_code == 409
    # Y el staff (sin PIN) no puede fijarse uno vía login alumno.
    assert cliente.post("/auth/login/alumno", json={"rut": rut_utp, "pin": "482915"}).status_code == 401


# --- Secretos fuera de respuestas y configuración ---


def test_422_no_devuelve_el_valor_recibido(cliente):
    r = cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": "55831"})
    assert r.status_code == 422
    assert "55831" not in r.text
    assert r.json()["detail"][0]["loc"] == ["body", "pin"]


def test_cargar_env_no_pisa_variables_del_sistema(tmp_path, monkeypatch):
    from nucleo.configuracion import cargar_env

    env = tmp_path / ".env"
    env.write_text('# comentario\nCLASEAIDIA_A="desde_archivo"\nCLASEAIDIA_B=desde_archivo\n\n', encoding="utf-8")
    monkeypatch.setenv("CLASEAIDIA_B", "desde_sistema")
    monkeypatch.delenv("CLASEAIDIA_A", raising=False)
    cargar_env(str(env))
    import os

    assert os.environ["CLASEAIDIA_A"] == "desde_archivo"
    assert os.environ["CLASEAIDIA_B"] == "desde_sistema"
    monkeypatch.delenv("CLASEAIDIA_A")


# --- Lecturas con login, visibilidad por rol y código del curso ---


def _alumno_en_curso(cliente, curso, rut="11222333-9"):
    token = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": rut, "nombre": "A", "pin": "482915"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_lecturas_de_cursos_requieren_login(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    for ruta in ["/cursos", f"/cursos/{curso['id']}", f"/cursos/{curso['id']}/bloques", f"/cursos/{curso['id']}/codigo"]:
        assert cliente.get(ruta).status_code == 401, ruta


def test_alumno_solo_ve_sus_cursos(cliente, colegio_id, headers_utp):
    curso_a = _crear_curso(cliente, colegio_id, headers_utp)
    curso_b = cliente.post("/cursos", json={"nombre": "8B", "colegio_id": colegio_id}, headers=headers_utp).json()
    h = _alumno_en_curso(cliente, curso_a)

    assert [c["id"] for c in cliente.get("/cursos", headers=h).json()] == [curso_a["id"]]
    assert cliente.get(f"/cursos/{curso_a['id']}/bloques", headers=h).status_code == 200
    assert cliente.get(f"/cursos/{curso_b['id']}", headers=h).status_code == 404
    assert cliente.get(f"/cursos/{curso_b['id']}/bloques", headers=h).status_code == 404
    # El staff ve todos los de su colegio.
    assert len(cliente.get("/cursos", headers=headers_utp).json()) == 2


def test_cursos_de_otro_colegio_no_se_ven(cliente, colegio_id, headers_utp, otro_colegio):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    _, hb = otro_colegio
    assert cliente.get("/cursos", headers=hb).json() == []
    assert cliente.get(f"/cursos/{curso['id']}", headers=hb).status_code == 404
    assert cliente.get(f"/cursos/{curso['id']}/codigo", headers=hb).status_code == 404


def test_codigo_del_curso_solo_para_staff_del_colegio(cliente, colegio_id, headers_utp):
    curso = _crear_curso(cliente, colegio_id, headers_utp)
    r = cliente.get(f"/cursos/{curso['id']}/codigo", headers=headers_utp)
    assert r.status_code == 200
    assert r.json() == {"codigo_invitacion": curso["codigo_invitacion"]}

    # Un profesor puede mostrarlo en clase, pero solo el de los cursos donde dicta.
    profe = cliente.post(
        "/usuarios",
        json={"rut": "5126663-3", "nombre": "Profe", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": "clave-segura-123"},
        headers=headers_utp,
    ).json()
    tp = cliente.post("/auth/login/staff", json={"rut": "5126663-3", "password": "clave-segura-123"}).json()["access_token"]
    hp = {"Authorization": f"Bearer {tp}"}
    assert cliente.get(f"/cursos/{curso['id']}/codigo", headers=hp).status_code == 404  # aún no dicta ahí
    bloque = {"tipo": "CLASE", "asignatura": "Matemática", "profesor_id": profe["id"], "dia_semana": 0, "hora_inicio": "08:00", "hora_fin": "08:45"}
    assert cliente.post(f"/cursos/{curso['id']}/bloques", json=bloque, headers=headers_utp).status_code == 201
    assert cliente.get(f"/cursos/{curso['id']}/codigo", headers=hp).status_code == 200

    # Un alumno, aunque esté inscrito, no.
    h = _alumno_en_curso(cliente, curso)
    assert cliente.get(f"/cursos/{curso['id']}/codigo", headers=h).status_code == 403


def test_estado_indica_si_el_servidor_ya_fue_configurado(cliente, rut_utp):
    assert cliente.get("/auth/estado").json() == {"configurado": False}
    cliente.post(
        "/auth/setup",
        json={"colegio_nombre": "L", "rut": rut_utp, "nombre": "U", "password": "clave-segura-123"},
    )
    assert cliente.get("/auth/estado").json() == {"configurado": True}


def test_me_devuelve_al_usuario_de_la_sesion(cliente, rut_utp, headers_utp, colegio_id):
    assert cliente.get("/auth/me").status_code == 401
    r = cliente.get("/auth/me", headers=headers_utp)
    assert r.status_code == 200
    assert r.json()["rut"] == rut_utp and r.json()["roles"] == ["UTP"] and r.json()["colegio_id"] == colegio_id
