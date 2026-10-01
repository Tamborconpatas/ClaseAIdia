"""Cursos y clases según el rol: el alumno solo ve lo publicado de su curso, el profesor solo lo que dicta."""
import datetime

import pytest

from infraestructura.modelos_orm import Clase, ContenidoClase


def _login(cliente, rut, password="clave-segura-123"):
    r = cliente.post("/auth/login/staff", json={"rut": rut, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _clase(db, bloque_id, dias_atras, contenido=None):
    c = Clase(bloque_id=bloque_id, fecha=datetime.date(2026, 9, 28) - datetime.timedelta(days=dias_atras))
    if contenido is not None:
        c.contenido = ContenidoClase(**contenido)
    db.add(c)
    db.flush()
    return c.id


@pytest.fixture()
def esc(cliente, colegio_id, headers_utp):
    """8°A y 8°B. Ana dicta Matemática en 8°A e Historia en 8°B; Beto dicta Lenguaje en 8°A.
    Clases: publicada (8°A, Ana), por aprobar (8°A, Ana), procesando (8°A, Beto), publicada (8°B, Ana)."""
    def profesor(rut, nombre):
        r = cliente.post(
            "/usuarios",
            json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": "clave-segura-123"},
            headers=headers_utp,
        )
        assert r.status_code == 201
        return r.json()["id"]

    ana, beto = profesor("5126663-3", "Ana"), profesor("6000000-K", "Beto")
    cursos = {n: cliente.post("/cursos", json={"nombre": n, "colegio_id": colegio_id}, headers=headers_utp).json() for n in ("8A", "8B")}

    def bloque(curso, asignatura, profesor_id, dia):
        b = {"tipo": "CLASE", "asignatura": asignatura, "profesor_id": profesor_id, "sala": "S1", "dia_semana": dia, "hora_inicio": "08:00", "hora_fin": "08:45"}
        r = cliente.post(f"/cursos/{cursos[curso]['id']}/bloques", json=b, headers=headers_utp)
        assert r.status_code == 201
        return r.json()["id"]

    b_mat, b_len, b_his = bloque("8A", "Matemática", ana, 0), bloque("8A", "Lenguaje", beto, 1), bloque("8B", "Historia", ana, 2)
    material = {"resumen": "Resumen X", "puntos_clave": "- uno\n- dos", "hoja_repaso": "Repaso", "tarjetas": [{"pregunta": "¿P?", "respuesta": "R"}], "transcripcion_texto": "texto"}
    with cliente.sesion() as db:
        ids = {
            "publicada": _clase(db, b_mat, 0, {**material, "aprobado": True}),
            "por_aprobar": _clase(db, b_mat, 7, {**material, "aprobado": False}),
            "procesando": _clase(db, b_len, 1),
            "publicada_8b": _clase(db, b_his, 2, {**material, "aprobado": True}),
        }
        db.commit()

    alumno = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": cursos["8A"]["codigo_invitacion"], "rut": "11222333-9", "nombre": "Alum", "pin": "482915"},
    ).json()["access_token"]
    return {
        "bloques": {"mat": b_mat, "len": b_len, "his": b_his},
        "ids": ids,
        "cursos": {n: c["id"] for n, c in cursos.items()},
        "utp": headers_utp,
        "ana": _login(cliente, "5126663-3"),
        "beto": _login(cliente, "6000000-K"),
        "alumno": {"Authorization": f"Bearer {alumno}"},
    }


def _ids(cliente, headers, **params):
    r = cliente.get("/clases", headers=headers, params=params)
    assert r.status_code == 200
    return {c["id"] for c in r.json()}


def test_clases_requieren_login(cliente, esc):
    assert cliente.get("/clases").status_code == 401
    assert cliente.get(f"/clases/{esc['ids']['publicada']}").status_code == 401


def test_alumno_solo_ve_clases_publicadas_de_su_curso(cliente, esc):
    i = esc["ids"]
    assert _ids(cliente, esc["alumno"]) == {i["publicada"]}  # no la por aprobar, ni la procesando, ni la de 8°B
    assert cliente.get(f"/clases/{i['publicada']}", headers=esc["alumno"]).status_code == 200
    for oculta in ("por_aprobar", "procesando", "publicada_8b"):
        assert cliente.get(f"/clases/{i[oculta]}", headers=esc["alumno"]).status_code == 404, oculta


def test_profesor_ve_sus_clases_en_cualquier_estado(cliente, esc):
    i = esc["ids"]
    assert _ids(cliente, esc["ana"]) == {i["publicada"], i["por_aprobar"], i["publicada_8b"]}
    assert _ids(cliente, esc["beto"]) == {i["procesando"]}
    assert _ids(cliente, esc["ana"], curso_id=esc["cursos"]["8B"]) == {i["publicada_8b"]}
    # Puede abrir su clase aunque aún no esté aprobada; la de otro profesor, no.
    assert cliente.get(f"/clases/{i['por_aprobar']}", headers=esc["ana"]).status_code == 200
    assert cliente.get(f"/clases/{i['por_aprobar']}", headers=esc["beto"]).status_code == 404


def test_estados_de_las_clases(cliente, esc):
    i = esc["ids"]
    estados = {c["id"]: c["estado"] for c in cliente.get("/clases", headers=esc["utp"]).json()}
    assert estados == {
        i["publicada"]: "publicada",
        i["por_aprobar"]: "por_aprobar",
        i["procesando"]: "procesando",
        i["publicada_8b"]: "publicada",
    }


def test_utp_ve_todas_las_del_colegio_y_otro_colegio_ninguna(cliente, esc, otro_colegio):
    assert _ids(cliente, esc["utp"]) == set(esc["ids"].values())
    _, hb = otro_colegio
    assert _ids(cliente, hb) == set()
    assert cliente.get(f"/clases/{esc['ids']['publicada']}", headers=hb).status_code == 404


def test_detalle_trae_el_material_y_el_orden_es_del_mas_reciente(cliente, esc):
    d = cliente.get(f"/clases/{esc['ids']['publicada']}", headers=esc["alumno"]).json()
    assert d["bloque_id"] == cliente.get(f"/cursos/{esc['cursos']['8A']}/bloques", headers=esc["alumno"]).json()[0]["id"]
    assert d["curso_nombre"] == "8A" and d["asignatura"] == "Matemática" and d["estado"] == "publicada"
    assert d["contenido"]["resumen"] == "Resumen X"
    assert d["contenido"]["tarjetas"] == [{"pregunta": "¿P?", "respuesta": "R"}]
    fechas = [c["fecha"] for c in cliente.get("/clases", headers=esc["utp"]).json()]
    assert fechas == sorted(fechas, reverse=True)


def test_clase_sin_material_no_trae_contenido(cliente, esc):
    d = cliente.get(f"/clases/{esc['ids']['procesando']}", headers=esc["beto"]).json()
    assert d["estado"] == "procesando" and d["contenido"] is None


def test_profesor_solo_ve_los_cursos_donde_dicta(cliente, esc):
    assert [c["nombre"] for c in cliente.get("/cursos", headers=esc["beto"]).json()] == ["8A"]
    assert sorted(c["nombre"] for c in cliente.get("/cursos", headers=esc["ana"]).json()) == ["8A", "8B"]
    assert cliente.get(f"/cursos/{esc['cursos']['8B']}", headers=esc["beto"]).status_code == 404
    assert cliente.get(f"/cursos/{esc['cursos']['8B']}/bloques", headers=esc["beto"]).status_code == 404
    assert cliente.get(f"/cursos/{esc['cursos']['8B']}/codigo", headers=esc["beto"]).status_code == 404
    # El UTP sigue viendo todos.
    assert len(cliente.get("/cursos", headers=esc["utp"]).json()) == 2


# --- Revisión del profesor y publicación provisoria -----------------------------------------------

MATERIAL = {"resumen": "R", "puntos_clave": "- a", "hoja_repaso": "H", "tarjetas": [], "transcripcion_texto": "t"}


def _ahora():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _con_material(cliente, bloque_id, horas_atras, dias_atras=20, **flags):
    """Crea una clase con material generado hace `horas_atras` horas."""
    with cliente.sesion() as db:
        cid = _clase(db, bloque_id, dias_atras, {**MATERIAL, "generado_en": _ahora() - datetime.timedelta(hours=horas_atras), **flags})
        db.commit()
    return cid


def _estado(cliente, headers, clase_id):
    """Estado de la clase vista por ese usuario, o None si no la ve."""
    r = cliente.get(f"/clases/{clase_id}", headers=headers)
    return r.json()["estado"] if r.status_code == 200 else None


def test_dentro_del_plazo_el_profesor_aun_puede_revisar_y_el_alumno_no_la_ve(cliente, esc):
    cid = _con_material(cliente, esc["bloques"]["mat"], horas_atras=23)
    assert _estado(cliente, esc["ana"], cid) == "por_aprobar"
    assert _estado(cliente, esc["alumno"], cid) is None
    # Informa hasta cuándo puede revisarla (en UTC, con zona, para que el navegador lo convierta).
    vence = cliente.get(f"/clases/{cid}", headers=esc["ana"]).json()["revision_vence"]
    assert vence.endswith("Z") or vence.endswith("+00:00")
    horas = (datetime.datetime.fromisoformat(vence.replace("Z", "+00:00")) - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
    assert 0.5 < horas < 1.5  # 24 h de plazo - 23 h transcurridas


def test_pasado_el_plazo_sin_revisar_se_publica_como_provisoria(cliente, esc):
    cid = _con_material(cliente, esc["bloques"]["mat"], horas_atras=25)
    assert _estado(cliente, esc["ana"], cid) == "provisoria"
    assert _estado(cliente, esc["alumno"], cid) == "provisoria"  # el alumno la ve, marcada como provisoria
    assert cid in _ids(cliente, esc["alumno"])
    assert cliente.get(f"/clases/{cid}", headers=esc["ana"]).json()["revision_vence"] is None


def test_una_clase_retirada_nunca_se_publica_sola(cliente, esc):
    cid = _con_material(cliente, esc["bloques"]["mat"], horas_atras=100, retirado=True)
    assert _estado(cliente, esc["ana"], cid) == "retirada"
    assert _estado(cliente, esc["alumno"], cid) is None
    assert cid not in _ids(cliente, esc["alumno"])


def test_el_plazo_es_configurable(cliente, esc, monkeypatch):
    from interfaz.api import rutas_clases

    cid = _con_material(cliente, esc["bloques"]["mat"], horas_atras=2)
    assert _estado(cliente, esc["alumno"], cid) is None  # con 24 h de plazo, aún no
    monkeypatch.setattr(rutas_clases, "HORAS_REVISION", 1)
    assert _estado(cliente, esc["alumno"], cid) == "provisoria"


def test_el_profesor_aprueba_y_el_alumno_la_ve_sin_advertencia(cliente, esc):
    cid = esc["ids"]["por_aprobar"]
    assert _estado(cliente, esc["alumno"], cid) is None
    r = cliente.post(f"/clases/{cid}/aprobar", headers=esc["ana"])
    assert r.status_code == 200 and r.json()["estado"] == "publicada"
    assert _estado(cliente, esc["alumno"], cid) == "publicada"


def test_aprobar_una_provisoria_le_quita_la_advertencia(cliente, esc):
    cid = _con_material(cliente, esc["bloques"]["mat"], horas_atras=30)
    assert _estado(cliente, esc["alumno"], cid) == "provisoria"
    cliente.post(f"/clases/{cid}/aprobar", headers=esc["ana"])
    assert _estado(cliente, esc["alumno"], cid) == "publicada"


def test_retirar_oculta_a_los_alumnos_y_se_puede_volver_a_aprobar(cliente, esc):
    cid = esc["ids"]["publicada"]
    assert _estado(cliente, esc["alumno"], cid) == "publicada"
    r = cliente.post(f"/clases/{cid}/retirar", headers=esc["ana"])
    assert r.status_code == 200 and r.json()["estado"] == "retirada"
    assert _estado(cliente, esc["alumno"], cid) is None
    cliente.post(f"/clases/{cid}/aprobar", headers=esc["ana"])
    assert _estado(cliente, esc["alumno"], cid) == "publicada"


def test_quien_puede_aprobar_o_retirar(cliente, esc):
    cid = esc["ids"]["por_aprobar"]  # clase de Ana
    for accion in ("aprobar", "retirar"):
        assert cliente.post(f"/clases/{cid}/{accion}").status_code == 401  # sin sesión
        assert cliente.post(f"/clases/{cid}/{accion}", headers=esc["alumno"]).status_code == 403
        assert cliente.post(f"/clases/{cid}/{accion}", headers=esc["beto"]).status_code == 404  # otro profesor
    assert cliente.post(f"/clases/{cid}/aprobar", headers=esc["utp"]).status_code == 200


def test_aprobar_y_retirar_en_otro_colegio_no_funcionan(cliente, esc, otro_colegio):
    _, hb = otro_colegio
    assert cliente.post(f"/clases/{esc['ids']['por_aprobar']}/aprobar", headers=hb).status_code == 404


def test_no_se_puede_revisar_una_clase_sin_material(cliente, esc):
    r = cliente.post(f"/clases/{esc['ids']['procesando']}/aprobar", headers=esc["beto"])
    assert r.status_code == 409


def test_el_horario_trae_el_nombre_del_profesor(cliente, esc):
    """El alumno no puede consultar usuarios, así que el nombre viaja en el bloque (y solo el nombre)."""
    bloques = cliente.get(f"/cursos/{esc['cursos']['8A']}/bloques", headers=esc["alumno"]).json()
    por_asignatura = {b["asignatura"]: b["profesor_nombre"] for b in bloques}
    assert por_asignatura == {"Matemática": "Ana", "Lenguaje": "Beto"}
    assert all("rut" not in b and "password_hash" not in b for b in bloques)


def test_un_bloque_sin_profesor_no_trae_nombre(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8C", "colegio_id": colegio_id}, headers=headers_utp).json()
    recreo = {"tipo": "RECREO", "dia_semana": 0, "hora_inicio": "10:00", "hora_fin": "10:15"}
    r = cliente.post(f"/cursos/{curso['id']}/bloques", json=recreo, headers=headers_utp)
    assert r.status_code == 201 and r.json()["profesor_nombre"] is None
