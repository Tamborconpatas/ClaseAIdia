# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Ollama se vuelve a levantar solo cuando el servidor lo necesita y no responde."""
import pytest
import requests

from infraestructura import cliente_ollama as co

URL = "http://localhost:11434"


class Resp:
    def __init__(self, codigo=200, cuerpo=None):
        self.status_code, self._c, self.text = codigo, cuerpo or {}, ""

    def json(self):
        return self._c


@pytest.fixture()
def sin_esperas(monkeypatch):
    monkeypatch.setattr(co.time, "sleep", lambda s: None)


def _caido_hasta_que_se_lance(monkeypatch, lanzados, ejecutable="C:/x/ollama.exe"):
    """Ollama no responde hasta que alguien lo arranca."""
    def get(url, timeout):
        if not lanzados:
            raise requests.exceptions.ConnectionError()
        return Resp()

    monkeypatch.setattr(co.requests, "get", get)
    monkeypatch.setattr(co, "_ejecutable_de_ollama", lambda: ejecutable)
    monkeypatch.setattr(co.subprocess, "Popen", lambda cmd, **k: lanzados.append(cmd))


def test_si_ya_responde_no_se_lanza_nada(monkeypatch):
    monkeypatch.setattr(co.requests, "get", lambda url, timeout: Resp())
    monkeypatch.setattr(co.subprocess, "Popen", lambda *a, **k: pytest.fail("no debía lanzarse"))
    assert co.asegurar_ollama(URL)


def test_si_esta_caido_se_arranca_y_se_espera_a_que_responda(monkeypatch, sin_esperas):
    lanzados = []
    _caido_hasta_que_se_lance(monkeypatch, lanzados)
    assert co.asegurar_ollama(URL) and lanzados == [["C:/x/ollama.exe", "serve"]]


def test_un_ollama_remoto_no_se_intenta_arrancar(monkeypatch):
    monkeypatch.setattr(co.requests, "get", lambda url, timeout: (_ for _ in ()).throw(requests.exceptions.ConnectionError()))
    monkeypatch.setattr(co.subprocess, "Popen", lambda *a, **k: pytest.fail("no debía lanzarse"))
    assert not co.asegurar_ollama("http://servidor-ia.colegio:11434")


def test_sin_ollama_instalado_o_que_no_arranca_devuelve_falso_sin_colgarse(monkeypatch, sin_esperas):
    monkeypatch.setattr(co.requests, "get", lambda url, timeout: (_ for _ in ()).throw(requests.exceptions.ConnectionError()))
    monkeypatch.setattr(co, "_ejecutable_de_ollama", lambda: None)
    assert not co.asegurar_ollama(URL)
    monkeypatch.setattr(co, "_ejecutable_de_ollama", lambda: "C:/x/ollama.exe")
    monkeypatch.setattr(co.subprocess, "Popen", lambda *a, **k: None)
    assert not co.asegurar_ollama(URL, esperar_s=0)


def test_generate_levanta_ollama_y_reintenta_una_vez(monkeypatch, sin_esperas):
    lanzados, envios = [], []
    _caido_hasta_que_se_lance(monkeypatch, lanzados)

    def post(url, json, timeout):
        envios.append(1)
        if not lanzados:
            raise requests.exceptions.ConnectionError()
        return Resp(cuerpo={"response": "hola"})

    monkeypatch.setattr(co.requests, "post", post)
    assert co.generate("p", "m", 10) == "hola" and len(envios) == 2


def test_generate_sigue_fallando_con_el_mensaje_de_siempre_si_no_se_puede_levantar(monkeypatch):
    monkeypatch.setattr(co.requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError()))
    monkeypatch.setattr(co, "asegurar_ollama", lambda url, esperar_s=30: False)
    with pytest.raises(RuntimeError, match="No se pudo conectar a Ollama"):
        co.generate("p", "m", 10)
