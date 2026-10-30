# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Mapa conceptual: las relaciones entre conceptos las propone un modelo (solo uno de 3B o más), las corrige el profesor y las
dibuja el lector. Se guardan datos, no código Mermaid."""
import json

import pytest

from infraestructura import cliente_ollama as co
from servicios import servicio_grabacion as sg
from servicios import servicio_material_estudio as sme
from test_clases import esc  # noqa: F401
from servicios.servicio_grabacion import generar_mapa as generar_mapa_real
from test_grabaciones import _en_curso, _estado, _terminar_con_audio, g, tiempo  # noqa: F401

REL = [
    {"de": "Aprendizaje supervisado", "relacion": "usa", "a": "Etiquetas"},
    {"de": "Aprendizaje supervisado", "relacion": "incluye", "a": "Regresión"},
    {"de": "Aprendizaje no supervisado", "relacion": "busca", "a": "Patrones"},
]


# --- Limpieza de lo que devuelve el modelo ----------------------------------------------------------------------------


def test_limpia_vacios_flechas_a_si_mismo_y_repetidas():
    crudas = [
        {"de": " A  b ", "relacion": "x", "a": "C"},
        {"de": "a B", "relacion": "otra", "a": "c"},  # la misma flecha escrita distinto
        {"de": "C", "relacion": "z", "a": "c"},  # a sí mismo
        {"de": "", "relacion": "z", "a": "D"},
        {"de": "D", "relacion": "z", "a": "  "},
        "no soy un dict",
        {"de": "C", "a": "E"},  # sin relación: se acepta
    ]
    assert sme._limpiar_relaciones(crudas) == [{"de": "A b", "relacion": "x", "a": "C"}, {"de": "C", "relacion": "", "a": "E"}]


def test_un_mismo_concepto_conserva_la_primera_escritura():
    r = sme._limpiar_relaciones([{"de": "Python", "relacion": "es", "a": "lenguaje"}, {"de": "PYTHON", "relacion": "tiene", "a": "Librerías"}])
    assert [x["de"] for x in r] == ["Python", "Python"]


def test_tope_de_relaciones_y_basura_que_no_es_una_lista():
    muchas = [{"de": f"A{i}", "relacion": "r", "a": f"B{i}"} for i in range(40)]
    assert len(sme._limpiar_relaciones(muchas)) == sme._MAX_RELACIONES
    assert sme._limpiar_relaciones(None) == [] and sme._limpiar_relaciones("x") == [] and sme._limpiar_relaciones({"de": "a"}) == []


# --- Generación -------------------------------------------------------------------------------------------------------


@pytest.fixture()
def ollama(monkeypatch):
    """Modelo configurado y respuestas de Ollama a mano; devuelve lo que se le pidió."""
    pedidos = []
    monkeypatch.setattr(sme.app_config, "get_param", lambda k: {"ollama_model": "llama3.2:3b", "ollama_url": "http://x"}.get(k, "x"))
    monkeypatch.setattr(sme, "_modelo_que_cabe", lambda modelo, es_auto: modelo)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    box = {"respuesta": json.dumps({"relaciones": REL})}

    def generate(prompt, model, max_tokens, ollama_url, **kw):
        pedidos.append({"prompt": prompt, "model": model, **kw})
        return box["respuesta"]

    monkeypatch.setattr(sme.ollama_client, "generate", generate)
    return pedidos, box


def test_con_un_modelo_de_3b_devuelve_las_relaciones_limpias_y_pide_json_con_esquema(ollama):
    pedidos, _ = ollama
    assert sme.generar_mapa_conceptual("Resumen de la clase", "- punto", "Inteligencia artificial") == REL
    assert pedidos[0]["formato"] == sme._ESQUEMA_MAPA and pedidos[0]["model"] == "llama3.2:3b"
    assert "Resumen de la clase" in pedidos[0]["prompt"] and "Inteligencia artificial" in pedidos[0]["prompt"]


def test_con_el_modelo_de_1b_no_se_intenta_porque_no_arma_relaciones_utiles(ollama, monkeypatch):
    pedidos, _ = ollama
    monkeypatch.setattr(sme, "_modelo_que_cabe", lambda modelo, es_auto: sme._OLLAMA_MODEL_CPU)
    assert sme.generar_mapa_conceptual("Resumen", "- punto") == [] and pedidos == []


def test_si_la_respuesta_no_sirve_no_hay_mapa(ollama):
    _, box = ollama
    for mala in ["no es json", json.dumps({"otra": 1}), json.dumps({"relaciones": REL[:2]}), json.dumps({"relaciones": "x"}), json.dumps([1, 2])]:
        box["respuesta"] = mala
        assert sme.generar_mapa_conceptual("Resumen", "") == [], mala


def test_si_ollama_falla_no_hay_mapa_y_sin_texto_ni_se_pregunta(ollama, monkeypatch):
    pedidos, _ = ollama
    assert sme.generar_mapa_conceptual("", "  ") == [] and pedidos == []
    monkeypatch.setattr(sme.ollama_client, "generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Ollama caído")))
    assert sme.generar_mapa_conceptual("Resumen", "") == []


def test_ollama_recibe_el_esquema_en_format(monkeypatch):
    enviados = []

    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"response": "{}"}

    monkeypatch.setattr(co.requests, "post", lambda url, json, timeout: enviados.append(json) or R())
    co.generate("p", "m", 10, formato={"type": "object"})
    co.generate("p", "m", 10)
    assert enviados[0]["format"] == {"type": "object"} and "format" not in enviados[1]


# --- En el procesamiento de la clase ----------------------------------------------------------------------------------


def test_el_mapa_generado_se_guarda_y_el_alumno_lo_ve(g, monkeypatch):
    monkeypatch.setattr(sg, "generar_mapa", lambda resumen, puntos, asignatura: REL)
    gid = _en_curso(g)
    assert _terminar_con_audio(g, gid)["estado"] == "terminada"
    cid = g["c"].get("/clases", headers=g["ana"]).json()[0]["id"]
    assert g["c"].post(f"/clases/{cid}/aprobar", headers=g["ana"]).json()["contenido"]["mapa"] == REL
    assert g["c"].get(f"/clases/{cid}", headers=g["alumno"]).json()["contenido"]["mapa"] == REL


def test_si_el_mapa_falla_la_clase_se_procesa_igual(g, monkeypatch):
    monkeypatch.setattr(sg, "generar_mapa", generar_mapa_real)  # la envoltura de verdad (la de los fixtures la reemplaza por una de mentira)
    monkeypatch.setattr(sme, "generar_mapa_conceptual", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    gid = _en_curso(g)
    s = _terminar_con_audio(g, gid)
    assert s["estado"] == "terminada"
    cid = g["c"].get("/clases", headers=g["ana"]).json()[0]["id"]
    assert g["c"].get(f"/clases/{cid}", headers=g["ana"]).json()["contenido"]["mapa"] == []


# --- Edición por el profesor ------------------------------------------------------------------------------------------


def _mapa(cliente, headers, clase_id, relaciones):
    return cliente.put(f"/clases/{clase_id}/mapa", json={"relaciones": relaciones}, headers=headers)


def test_el_profesor_arma_el_mapa_y_el_alumno_lo_ve_normalizado(cliente, esc):
    cid = esc["ids"]["publicada"]
    r = _mapa(cliente, esc["ana"], cid, [{"de": "  Idea\n  uno ", "relacion": " lleva a ", "a": "Idea dos"}])
    assert r.status_code == 200
    assert r.json()["contenido"]["mapa"] == [{"de": "Idea uno", "relacion": "lleva a", "a": "Idea dos"}]
    assert cliente.get(f"/clases/{cid}", headers=esc["alumno"]).json()["contenido"]["mapa"][0]["de"] == "Idea uno"


def test_una_lista_vacia_quita_el_mapa(cliente, esc):
    cid = esc["ids"]["publicada"]
    _mapa(cliente, esc["ana"], cid, [{"de": "A", "relacion": "r", "a": "B"}])
    assert _mapa(cliente, esc["ana"], cid, []).json()["contenido"]["mapa"] == []


def test_quien_puede_editar_el_mapa(cliente, esc, otro_colegio):
    cid, uno = esc["ids"]["publicada"], [{"de": "A", "relacion": "r", "a": "B"}]
    assert cliente.put(f"/clases/{cid}/mapa", json={"relaciones": uno}).status_code == 401
    assert _mapa(cliente, esc["alumno"], cid, uno).status_code == 403
    assert _mapa(cliente, esc["beto"], cid, uno).status_code == 404  # otro profesor
    assert _mapa(cliente, otro_colegio[1], cid, uno).status_code == 404
    assert _mapa(cliente, esc["utp"], cid, uno).status_code == 200
    assert _mapa(cliente, esc["beto"], esc["ids"]["procesando"], uno).status_code == 409  # sin material todavía


def test_validaciones_del_mapa(cliente, esc):
    cid = esc["ids"]["publicada"]
    assert _mapa(cliente, esc["ana"], cid, [{"de": "  ", "relacion": "r", "a": "B"}]).status_code == 422
    assert _mapa(cliente, esc["ana"], cid, [{"de": "A", "relacion": "r", "a": ""}]).status_code == 422
    assert _mapa(cliente, esc["ana"], cid, [{"de": "x" * 61, "relacion": "r", "a": "B"}]).status_code == 422
    assert _mapa(cliente, esc["ana"], cid, [{"de": "A", "relacion": "r" * 41, "a": "B"}]).status_code == 422
    assert _mapa(cliente, esc["ana"], cid, [{"de": f"A{i}", "relacion": "r", "a": "B"} for i in range(31)]).status_code == 422
    assert cliente.get(f"/clases/{cid}", headers=esc["ana"]).json()["contenido"]["mapa"] == []  # lo rechazado no cambió nada
