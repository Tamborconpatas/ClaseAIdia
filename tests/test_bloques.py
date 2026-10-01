"""Edición del horario por el UTP: editar, borrar y las reglas que evitan choques."""
import datetime

import pytest

from infraestructura.modelos_orm import Clase


def _bloque(asignatura="Matemática", profesor_id=None, dia=0, ini="08:00", fin="08:45", tipo="CLASE", sala="S1"):
    return {"tipo": tipo, "asignatura": asignatura, "profesor_id": profesor_id, "sala": sala, "dia_semana": dia, "hora_inicio": ini, "hora_fin": fin}


@pytest.fixture()
def h(cliente, colegio_id, headers_utp):
    """Dos cursos, dos profesores y un bloque de Matemática (Ana) el lunes 08:00-08:45 en 8A."""
    def profesor(rut, nombre):
        r = cliente.post(
            "/usuarios",
            json={"rut": rut, "nombre": nombre, "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": "clave-segura-123"},
            headers=headers_utp,
        )
        return r.json()["id"]

    curso = lambda n: cliente.post("/cursos", json={"nombre": n, "colegio_id": colegio_id}, headers=headers_utp).json()["id"]
    ana, beto = profesor("5126663-3", "Ana"), profesor("6000000-K", "Beto")
    c8a, c8b = curso("8A"), curso("8B")
    r = cliente.post(f"/cursos/{c8a}/bloques", json=_bloque(profesor_id=ana), headers=headers_utp)
    assert r.status_code == 201
    return {"c": cliente, "u": headers_utp, "ana": ana, "beto": beto, "8a": c8a, "8b": c8b, "bloque": r.json()["id"]}


def _crear(h, curso, **kw):
    return h["c"].post(f"/cursos/{h[curso]}/bloques", json=_bloque(**kw), headers=h["u"])


def test_editar_un_bloque(h):
    r = h["c"].put(f"/bloques/{h['bloque']}", json=_bloque("Lenguaje", h["beto"], dia=2, ini="09:00", fin="09:45", sala="S9"), headers=h["u"])
    assert r.status_code == 200
    b = r.json()
    assert (b["asignatura"], b["profesor_nombre"], b["dia_semana"], b["hora_inicio"], b["sala"]) == ("Lenguaje", "Beto", 2, "09:00:00", "S9")
    assert b["curso_id"] == h["8a"]  # el curso no cambia
    assert [x["asignatura"] for x in h["c"].get(f"/cursos/{h['8a']}/bloques", headers=h["u"]).json()] == ["Lenguaje"]


def test_guardar_un_bloque_sin_cambios_no_choca_consigo_mismo(h):
    r = h["c"].put(f"/bloques/{h['bloque']}", json=_bloque(profesor_id=h["ana"]), headers=h["u"])
    assert r.status_code == 200


def test_no_se_puede_cruzar_con_otro_bloque_del_curso(h):
    assert _crear(h, "8a", asignatura="Historia", dia=0, ini="08:30", fin="09:15").status_code == 409
    assert _crear(h, "8a", asignatura="Historia", dia=0, ini="07:30", fin="08:15").status_code == 409
    # Bloques contiguos o en otro día sí.
    assert _crear(h, "8a", asignatura="Historia", dia=0, ini="08:45", fin="09:30").status_code == 201
    assert _crear(h, "8a", asignatura="Historia", dia=1, ini="08:00", fin="08:45").status_code == 201
    # Editar un bloque para que choque con otro también se rechaza.
    otro = _crear(h, "8a", asignatura="Artes", dia=3, ini="10:00", fin="10:45").json()["id"]
    r = h["c"].put(f"/bloques/{otro}", json=_bloque("Artes", dia=0, ini="08:00", fin="08:45"), headers=h["u"])
    assert r.status_code == 409


def test_un_profesor_no_puede_estar_en_dos_cursos_a_la_vez(h):
    r = _crear(h, "8b", asignatura="Matemática", profesor_id=h["ana"], dia=0, ini="08:15", fin="09:00")
    assert r.status_code == 409 and "8A" in r.json()["detail"]
    assert _crear(h, "8b", asignatura="Matemática", profesor_id=h["ana"], dia=0, ini="08:45", fin="09:30").status_code == 201
    # Otro profesor a la misma hora en otro curso, sin problema.
    assert _crear(h, "8b", asignatura="Lenguaje", profesor_id=h["beto"], dia=0, ini="08:00", fin="08:45").status_code == 201


def test_validaciones_del_bloque(h):
    assert _crear(h, "8a", dia=4, ini="10:00", fin="10:00").status_code == 422  # sin duración
    assert _crear(h, "8a", dia=4, ini="10:30", fin="10:00").status_code == 422  # termina antes de empezar
    assert _crear(h, "8a", asignatura="   ", dia=4, ini="10:00", fin="10:45").status_code == 422  # clase sin asignatura


def test_recreo_y_almuerzo_no_llevan_asignatura_ni_profesor(h):
    r = _crear(h, "8a", asignatura="Matemática", profesor_id=h["ana"], tipo="RECREO", dia=4, ini="09:30", fin="09:45")
    assert r.status_code == 201
    assert r.json()["asignatura"] is None and r.json()["profesor_id"] is None and r.json()["profesor_nombre"] is None


def test_el_profesor_debe_tener_el_rol_profesor(cliente, h, colegio_id, rut_utp):
    # El UTP del colegio no es profesor: no se le puede asignar un bloque.
    utp_id = next(u["id"] for u in cliente.get("/usuarios", headers=h["u"]).json() if u["rut"] == rut_utp)
    assert _crear(h, "8a", profesor_id=utp_id, dia=4, ini="10:00", fin="10:45").status_code == 409


def test_borrar_un_bloque(h):
    assert h["c"].delete(f"/bloques/{h['bloque']}", headers=h["u"]).status_code == 204
    assert h["c"].get(f"/cursos/{h['8a']}/bloques", headers=h["u"]).json() == []
    assert h["c"].delete(f"/bloques/{h['bloque']}", headers=h["u"]).status_code == 404


def test_no_se_puede_borrar_un_bloque_con_clases_registradas(cliente, h):
    with cliente.sesion() as db:
        db.add(Clase(bloque_id=h["bloque"], fecha=datetime.date(2026, 9, 28)))
        db.commit()
    r = h["c"].delete(f"/bloques/{h['bloque']}", headers=h["u"])
    assert r.status_code == 409
    assert len(h["c"].get(f"/cursos/{h['8a']}/bloques", headers=h["u"]).json()) == 1  # sigue ahí


def test_quien_puede_editar_el_horario(cliente, h, otro_colegio):
    b = h["bloque"]
    assert cliente.put(f"/bloques/{b}", json=_bloque()).status_code == 401
    assert cliente.delete(f"/bloques/{b}").status_code == 401
    # Un profesor no edita el horario.
    tp = cliente.post("/auth/login/staff", json={"rut": "5126663-3", "password": "clave-segura-123"}).json()["access_token"]
    hp = {"Authorization": f"Bearer {tp}"}
    assert cliente.put(f"/bloques/{b}", json=_bloque(), headers=hp).status_code == 403
    assert cliente.delete(f"/bloques/{b}", headers=hp).status_code == 403
    # El UTP de otro colegio no ve ese bloque.
    _, hb = otro_colegio
    assert cliente.put(f"/bloques/{b}", json=_bloque(), headers=hb).status_code == 404
    assert cliente.delete(f"/bloques/{b}", headers=hb).status_code == 404


def test_el_horario_no_restringe_las_horas_de_la_jornada(h):
    """Hay colegios que van de 8:30 a 18:15 (o más): no hay una hora mínima ni máxima de la jornada."""
    horas = [
        ("08:30", "09:15"), ("09:15", "10:00"), ("10:15", "11:00"), ("11:00", "11:45"), ("12:00", "12:45"),
        ("12:45", "13:30"), ("14:15", "15:00"), ("15:00", "15:45"), ("16:00", "16:45"), ("16:45", "17:30"),
        ("17:30", "18:15"), ("19:00", "20:30"), ("22:00", "23:59"), ("00:15", "00:45"),
    ]
    for i, (ini, fin) in enumerate(horas):
        r = _crear(h, "8b", asignatura=f"Clase {i}", dia=3, ini=ini, fin=fin)
        assert r.status_code == 201, (ini, fin, r.text)
    guardados = h["c"].get(f"/cursos/{h['8b']}/bloques", headers=h["u"]).json()
    assert len(guardados) == len(horas)
    assert max(b["hora_fin"] for b in guardados) == "23:59:00"
