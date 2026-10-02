"""Lo leído de la pizarra llega al lector: el alumno solo lo ve cuando la clase está publicada y el profesor puede corregirlo."""
import datetime

from infraestructura.modelos_orm import EstadoGrabacion, FotoPizarra, Grabacion
from test_clases import esc  # noqa: F401


def con_fotos(cliente, clase_id, fotos):
    with cliente.sesion() as db:
        g = Grabacion(clase_id=clase_id, estado=EstadoGrabacion.TERMINADA, corte_en=datetime.datetime(2026, 9, 28, 9, 0))
        db.add(g)
        db.flush()
        db.add_all([FotoPizarra(grabacion_id=g.id, segundo=s, estado=e, texto=t, error=None if e == "leida" else "x") for s, e, t in fotos])
        db.commit()
        return {f.segundo: f.id for f in g.fotos}  # por el segundo de la clase en que se sacó


FOTOS = [(900, "leida", "$$x = \\frac{4620}{420}$$"), (60, "leida", "Hw: p. 44"), (100, "error", None), (200, "leida", "   ")]


def test_el_alumno_ve_la_pizarra_de_una_clase_publicada_en_orden_y_sin_lo_que_fallo(cliente, esc):
    cid = esc["ids"]["publicada"]
    con_fotos(cliente, cid, FOTOS)
    k = cliente.get(f"/clases/{cid}", headers=esc["alumno"]).json()["contenido"]
    assert [(p["segundo"], p["texto"]) for p in k["pizarra"]] == [(60, "Hw: p. 44"), (900, "$$x = \\frac{4620}{420}$$")]


def test_sin_fotos_la_pizarra_es_una_lista_vacia(cliente, esc):
    assert cliente.get(f"/clases/{esc['ids']['publicada']}", headers=esc["alumno"]).json()["contenido"]["pizarra"] == []


def test_el_alumno_no_ve_la_pizarra_de_una_clase_que_aun_no_se_publica(cliente, esc):
    cid = esc["ids"]["por_aprobar"]
    con_fotos(cliente, cid, FOTOS)
    assert cliente.get(f"/clases/{cid}", headers=esc["alumno"]).status_code == 404
    assert len(cliente.get(f"/clases/{cid}", headers=esc["ana"]).json()["contenido"]["pizarra"]) == 2


def test_el_profesor_corrige_el_texto_y_el_alumno_ve_la_version_corregida(cliente, esc):
    cid = esc["ids"]["publicada"]
    ids = con_fotos(cliente, cid, FOTOS)
    r = cliente.put(f"/clases/{cid}/pizarra/{ids[900]}", json={"texto": "  $$x = 11$$  "}, headers=esc["ana"])
    assert r.status_code == 200
    textos = {p["id"]: p["texto"] for p in cliente.get(f"/clases/{cid}", headers=esc["alumno"]).json()["contenido"]["pizarra"]}
    assert textos[ids[900]] == "$$x = 11$$"


def test_el_profesor_quita_una_foto_mal_leida(cliente, esc):
    cid = esc["ids"]["publicada"]
    ids = con_fotos(cliente, cid, FOTOS)
    r = cliente.delete(f"/clases/{cid}/pizarra/{ids[900]}", headers=esc["ana"])
    assert r.status_code == 200 and [p["texto"] for p in r.json()["contenido"]["pizarra"]] == ["Hw: p. 44"]
    assert cliente.delete(f"/clases/{cid}/pizarra/{ids[900]}", headers=esc["ana"]).status_code == 404  # ya no existe


def test_quien_puede_corregir_la_pizarra(cliente, esc, otro_colegio):
    cid = esc["ids"]["publicada"]
    ids = con_fotos(cliente, cid, FOTOS)
    url, cuerpo = f"/clases/{cid}/pizarra/{ids[900]}", {"texto": "x"}
    assert cliente.put(url, json=cuerpo).status_code == 401
    assert cliente.put(url, json=cuerpo, headers=esc["alumno"]).status_code == 403
    assert cliente.delete(url, headers=esc["alumno"]).status_code == 403
    assert cliente.put(url, json=cuerpo, headers=esc["beto"]).status_code == 404  # otro profesor
    assert cliente.delete(url, headers=esc["beto"]).status_code == 404
    assert cliente.put(url, json=cuerpo, headers=otro_colegio[1]).status_code == 404
    assert cliente.put(url, json=cuerpo, headers=esc["utp"]).status_code == 200


def test_no_se_toca_una_foto_de_otra_clase_ni_una_que_no_se_leyo(cliente, esc):
    c1, c2 = esc["ids"]["publicada"], esc["ids"]["publicada_8b"]  # las dos de Ana
    f1 = con_fotos(cliente, c1, FOTOS)
    f2 = con_fotos(cliente, c2, [(5, "leida", "otra")])
    assert cliente.put(f"/clases/{c2}/pizarra/{f1[900]}", json={"texto": "x"}, headers=esc["ana"]).status_code == 404
    assert cliente.put(f"/clases/{c1}/pizarra/{f2[5]}", json={"texto": "x"}, headers=esc["ana"]).status_code == 404
    assert cliente.put(f"/clases/{c1}/pizarra/{f1[100]}", json={"texto": "x"}, headers=esc["ana"]).status_code == 404  # la que dio error


def test_validaciones_del_texto_de_la_pizarra(cliente, esc):
    cid = esc["ids"]["publicada"]
    ids = con_fotos(cliente, cid, FOTOS)
    url = f"/clases/{cid}/pizarra/{ids[900]}"
    assert cliente.put(url, json={"texto": "   "}, headers=esc["ana"]).status_code == 422
    assert cliente.put(url, json={"texto": "x" * 8_001}, headers=esc["ana"]).status_code == 422
    assert cliente.get(f"/clases/{cid}", headers=esc["ana"]).json()["contenido"]["pizarra"][1]["texto"] == "$$x = \\frac{4620}{420}$$"
