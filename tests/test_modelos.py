"""Instalar un modelo de IA desde la aplicación (sin consola): estado, avance, errores entendibles y una descarga a la vez."""
import json

import pytest
import requests

from servicios import servicio_modelos as sm

URL = "http://localhost:11434"
MODELO = "qwen2.5vl:3b"


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    sm._descargas.clear()
    monkeypatch.setattr(sm, "asegurar_ollama", lambda url: True)
    yield
    sm._descargas.clear()


class Respuesta:
    def __init__(self, lineas=(), codigo=200, texto="", json_=None):
        self.status_code, self.text, self._lineas, self._json = codigo, texto, lineas, json_

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_lines(self):
        return iter(json.dumps(l).encode() if isinstance(l, dict) else l for l in self._lineas)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


# --- ¿Está instalado? ---------------------------------------------------------------------------------------------------


def test_instalado_reconoce_el_nombre_exacto_y_la_etiqueta_latest(monkeypatch):
    modelos = [{"name": "llama3.2:1b", "model": "llama3.2:1b"}, {"name": "otro:latest", "model": "otro:latest"}]
    monkeypatch.setattr(sm.requests, "get", lambda url, timeout: Respuesta(json_={"models": modelos}))
    assert sm.instalado("llama3.2:1b", URL) is True
    assert sm.instalado("otro", URL) is True  # `otro` es `otro:latest`
    assert sm.instalado(MODELO, URL) is False
    assert sm.instalado("llama3.2", URL) is False  # otro modelo de la misma familia no cuenta


def test_si_ollama_no_responde_no_se_sabe_y_no_se_dice_que_falta(monkeypatch):
    def cae(url, timeout):
        raise requests.ConnectionError("rechazada")

    monkeypatch.setattr(sm.requests, "get", cae)
    assert sm.instalado(MODELO, URL) is None
    monkeypatch.setattr(sm.requests, "get", lambda url, timeout: Respuesta(codigo=500))
    assert sm.instalado(MODELO, URL) is None


# --- La descarga ---------------------------------------------------------------------------------------------------------


def test_el_avance_suma_las_capas_y_termina_en_lista(monkeypatch):
    lineas = [
        {"status": "pulling manifest"},
        {"status": "pulling aaa", "digest": "aaa", "total": 1000, "completed": 250},
        {"status": "pulling bbb", "digest": "bbb", "total": 3000, "completed": 0},
        {"status": "pulling aaa", "digest": "aaa", "total": 1000, "completed": 1000},
        {"status": "pulling bbb", "digest": "bbb", "total": 3000, "completed": 1500},
        {"status": "pulling bbb", "digest": "bbb", "total": 3000, "completed": 3000},  # todo bajado, falta verificar
        {"status": "verifying sha256 digest"},
        {"status": "success"},
    ]
    vistos = []
    original = sm._poner
    monkeypatch.setattr(sm, "_poner", lambda m, **c: (vistos.append(dict(c)), original(m, **c))[1])
    monkeypatch.setattr(sm.requests, "post", lambda *a, **k: Respuesta(lineas))
    sm._correr(MODELO, URL)
    porcentajes = [v["porcentaje"] for v in vistos if "porcentaje" in v and v.get("estado") != "lista"]
    assert 25.0 in porcentajes and 62.5 in porcentajes  # 250/4000 y (1000+1500)/4000
    assert max(porcentajes) == 99.0  # con todo bajado pero sin verificar aún se muestra 99 %: el 100 % solo cuando de verdad terminó
    assert sm.estado_de_descarga(MODELO) == {"estado": "lista", "porcentaje": 100.0, "mensaje": "Listo"}


def test_los_mensajes_del_avance_estan_en_espanol():
    assert sm._traducir("pulling manifest") == "Preparando la descarga…"
    assert sm._traducir("pulling 6e4c38e1172f") == "Descargando…"
    assert sm._traducir("verifying sha256 digest") == "Verificando lo descargado…"
    assert sm._traducir("success") == "Listo"


@pytest.mark.parametrize("texto", ["pull model manifest: Get https://registry.ollama.ai: dial tcp: lookup registry.ollama.ai: no such host", "i/o timeout"])
def test_sin_internet_se_dice_en_palabras_de_persona(monkeypatch, texto):
    monkeypatch.setattr(sm.requests, "post", lambda *a, **k: Respuesta([{"error": texto}]))
    sm._poner(MODELO, estado="descargando", porcentaje=0.0, mensaje="")
    sm._correr(MODELO, URL)
    d = sm.estado_de_descarga(MODELO)
    assert d["estado"] == "error" and "internet" in d["mensaje"] and "dial tcp" not in d["mensaje"]


def test_otros_errores_se_muestran_acortados(monkeypatch):
    monkeypatch.setattr(sm.requests, "post", lambda *a, **k: Respuesta([{"error": "x" * 400}]))
    sm._correr(MODELO, URL)
    d = sm.estado_de_descarga(MODELO)
    assert d["estado"] == "error" and d["mensaje"].startswith("No se pudo descargar el modelo: xxx") and len(d["mensaje"]) < 200


def test_un_error_de_http_o_de_conexion_queda_como_error_sin_lanzar(monkeypatch):
    monkeypatch.setattr(sm.requests, "post", lambda *a, **k: Respuesta(codigo=500, texto="boom"))
    sm._correr(MODELO, URL)
    assert sm.estado_de_descarga(MODELO)["estado"] == "error"

    def cae(*a, **k):
        raise requests.ConnectionError("se cortó")

    monkeypatch.setattr(sm.requests, "post", cae)
    sm._correr(MODELO, URL)
    assert sm.estado_de_descarga(MODELO)["estado"] == "error"


def test_si_ollama_no_esta_abierto_se_explica_que_hacer(monkeypatch):
    monkeypatch.setattr(sm, "asegurar_ollama", lambda url: False)
    monkeypatch.setattr(sm.requests, "post", lambda *a, **k: pytest.fail("no debía pedir nada"))
    sm._correr(MODELO, URL)
    d = sm.estado_de_descarga(MODELO)
    assert d["estado"] == "error" and "Ollama no está abierto" in d["mensaje"]


# --- Empezar --------------------------------------------------------------------------------------------------------------


class HiloSincrono:
    def __init__(self, target, args=(), **k):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_empezar_marca_que_se_descarga_y_corre_en_un_hilo(monkeypatch):
    monkeypatch.setattr(sm, "instalado", lambda m, u: False)
    corridas = []
    monkeypatch.setattr(sm, "_correr", lambda m, u: corridas.append((m, u)))
    monkeypatch.setattr(sm.threading, "Thread", HiloSincrono)
    d = sm.iniciar_descarga(MODELO, URL)
    assert d == {"estado": "descargando", "porcentaje": 0.0, "mensaje": "Preparando la descarga…"} and corridas == [(MODELO, URL)]


def test_si_ya_esta_instalado_o_ya_se_descarga_se_rechaza_con_409(monkeypatch):
    monkeypatch.setattr(sm, "instalado", lambda m, u: True)
    with pytest.raises(sm.ErrorModelo, match="ya está instalado") as e:
        sm.iniciar_descarga(MODELO, URL)
    assert e.value.estado == 409

    monkeypatch.setattr(sm, "instalado", lambda m, u: False)
    sm._poner(MODELO, estado="descargando", porcentaje=10.0, mensaje="")
    with pytest.raises(sm.ErrorModelo, match="Ya se está descargando"):
        sm.iniciar_descarga(MODELO, URL)


def test_tras_un_error_se_puede_volver_a_intentar(monkeypatch):
    monkeypatch.setattr(sm, "instalado", lambda m, u: False)
    sm._poner(MODELO, estado="error", porcentaje=40.0, mensaje="sin internet")
    monkeypatch.setattr(sm, "_correr", lambda m, u: None)
    monkeypatch.setattr(sm.threading, "Thread", HiloSincrono)
    assert sm.iniciar_descarga(MODELO, URL)["estado"] == "descargando"
    assert sm.estado_de_descarga(MODELO)["porcentaje"] == 0.0  # empieza de cero la cuenta


def test_preguntar_si_esta_instalado_conecta_con_espera_corta(monkeypatch):
    """Con Ollama cerrado, en Windows cada intento de conexión tarda ~2 s (medido): la pantalla de Ajustes no puede esperar más."""
    pedidos = []
    monkeypatch.setattr(sm.requests, "get", lambda url, timeout: pedidos.append(timeout) or Respuesta(json_={"models": []}))
    sm.instalado(MODELO, URL)
    assert pedidos == [(1, 3)]


def test_si_el_llamador_ya_pregunto_no_se_le_vuelve_a_preguntar_a_ollama(monkeypatch):
    monkeypatch.setattr(sm, "instalado", lambda m, u: pytest.fail("no debía volver a preguntar"))
    monkeypatch.setattr(sm, "_correr", lambda m, u: None)
    monkeypatch.setattr(sm.threading, "Thread", HiloSincrono)
    assert sm.iniciar_descarga(MODELO, URL, ya_esta=False)["estado"] == "descargando"
    sm._descargas.clear()
    with pytest.raises(sm.ErrorModelo, match="ya está instalado"):
        sm.iniciar_descarga(MODELO, URL, ya_esta=True)
