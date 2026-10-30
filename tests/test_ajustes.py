# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Ajustes del colegio que decide el UTP desde la aplicación (no un archivo de configuración): las fotos de la pizarra."""
import pytest

from servicios import servicio_modelos as sm
from servicios import servicio_pizarra as sp
from test_clases import esc  # noqa: F401


@pytest.fixture(autouse=True)
def ollama(monkeypatch):
    """Ollama de mentira: responde, sin el modelo instalado, y no baja nada de verdad."""
    sm._descargas.clear()
    estado = {"instalado": False, "responde": True, "pedidos": []}
    monkeypatch.setattr(sm, "instalado", lambda modelo, url: (estado["instalado"] if estado["responde"] else None))
    monkeypatch.setattr(sm, "_correr", lambda modelo, url: estado["pedidos"].append((modelo, url)))
    monkeypatch.setattr(sm.threading, "Thread", type("H", (), {"__init__": lambda self, target, args=(), **k: setattr(self, "t", (target, args)), "start": lambda self: self.t[0](*self.t[1])}))
    monkeypatch.setattr("interfaz.api.rutas_ajustes.memoria_total_gb", lambda: 15.64)
    yield estado
    sm._descargas.clear()


def ver(cliente, headers):
    return cliente.get("/ajustes/fotos-pizarra", headers=headers)


def test_un_colegio_nuevo_las_tiene_apagadas_y_el_utp_ve_lo_que_necesita_para_decidir(cliente, esc):
    r = ver(cliente, esc["utp"])
    assert r.status_code == 200
    d = r.json()
    assert d["activada"] is False and d["modelo"] == sp.MODELO_VISION
    assert d["ollama_responde"] is True and d["modelo_instalado"] is False
    assert d["memoria_total_gb"] == 15.6 and d["memoria_recomendada_gb"] == sp.MEMORIA_RECOMENDADA_GB
    assert d["descarga"] is None


def test_el_utp_las_activa_y_las_desactiva_y_se_recuerda(cliente, esc):
    assert cliente.put("/ajustes/fotos-pizarra", json={"activada": True}, headers=esc["utp"]).json()["activada"] is True
    assert ver(cliente, esc["utp"]).json()["activada"] is True  # quedó guardado en la base, no en memoria
    assert cliente.put("/ajustes/fotos-pizarra", json={"activada": False}, headers=esc["utp"]).json()["activada"] is False
    assert ver(cliente, esc["utp"]).json()["activada"] is False


def test_solo_el_utp_puede_ver_y_cambiar_los_ajustes(cliente, esc):
    url, cuerpo = "/ajustes/fotos-pizarra", {"activada": True}
    assert cliente.get(url).status_code == 401
    for quien in ("ana", "alumno"):  # un profesor y un alumno
        assert ver(cliente, esc[quien]).status_code == 403
        assert cliente.put(url, json=cuerpo, headers=esc[quien]).status_code == 403
        assert cliente.post(url + "/modelo", headers=esc[quien]).status_code == 403
    assert ver(cliente, esc["utp"]).json()["activada"] is False  # nada cambió


def test_cada_colegio_decide_por_su_cuenta(cliente, esc, otro_colegio):
    cliente.put("/ajustes/fotos-pizarra", json={"activada": True}, headers=esc["utp"])
    assert ver(cliente, otro_colegio[1]).json()["activada"] is False
    assert ver(cliente, esc["utp"]).json()["activada"] is True


def test_el_ajuste_vive_en_el_colegio_y_la_funcion_lo_lee_de_ahi(cliente, esc):
    from infraestructura.modelos_orm import Colegio

    with cliente.sesion() as db:
        colegio = db.query(Colegio).first()
        assert sp.activadas(colegio) is False
        colegio.fotos_pizarra = True
        db.commit()
        assert sp.activadas(colegio) is True


def test_descargar_el_modelo_arranca_la_descarga_y_el_estado_la_muestra(cliente, esc, ollama):
    r = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert r.status_code == 200
    assert ollama["pedidos"] == [(sp.MODELO_VISION, sp.url_ollama())]
    assert r.json()["descarga"]["estado"] == "descargando"
    assert ver(cliente, esc["utp"]).json()["descarga"]["estado"] == "descargando"


def test_no_se_baja_dos_veces_ni_lo_que_ya_esta_instalado(cliente, esc, ollama):
    assert cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"]).status_code == 200
    segundo = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert segundo.status_code == 409 and "Ya se está descargando" in segundo.json()["detail"]
    sm._descargas.clear()
    ollama["instalado"] = True
    ya = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert ya.status_code == 409 and "ya está instalado" in ya.json()["detail"]
    assert ver(cliente, esc["utp"]).json()["modelo_instalado"] is True


def test_si_ollama_no_responde_el_estado_lo_dice_sin_fallar(cliente, esc, ollama):
    ollama["responde"] = False
    d = ver(cliente, esc["utp"]).json()
    assert d["ollama_responde"] is False and d["modelo_instalado"] is False


def test_si_no_se_puede_medir_la_memoria_no_se_inventa(cliente, esc, monkeypatch):
    monkeypatch.setattr("interfaz.api.rutas_ajustes.memoria_total_gb", lambda: None)
    assert ver(cliente, esc["utp"]).json()["memoria_total_gb"] is None


def test_pedir_la_descarga_le_pregunta_una_sola_vez_a_ollama(cliente, esc, monkeypatch):
    """Cada pregunta a un Ollama cerrado cuesta ~2 s en Windows: el botón no puede hacer dos."""
    preguntas = []
    monkeypatch.setattr(sm, "instalado", lambda modelo, url: preguntas.append(1) or False)
    assert cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"]).status_code == 200
    assert preguntas == [1]
