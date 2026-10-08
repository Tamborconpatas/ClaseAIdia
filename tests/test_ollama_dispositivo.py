"""OLLAMA_DISPOSITIVO=cpu: el resumen se genera en la CPU (con el modelo liviano) y la GPU queda libre para Whisper."""
import pytest

from infraestructura import cliente_ollama as co
from servicios import servicio_material_estudio as m


class Resp:
    status_code = 200
    text = ""

    def json(self):
        return {"response": "ok"}


@pytest.fixture()
def envios(monkeypatch):
    """Guarda lo que `generate` le manda a Ollama."""
    guardados = []

    def post(url, json, timeout):
        guardados.append(json)
        return Resp()

    monkeypatch.setattr(co.requests, "post", post)
    return guardados


@pytest.mark.parametrize("valor", ["cpu", "CPU", " cpu "])
def test_con_cpu_ollama_no_pone_capas_en_la_gpu(monkeypatch, envios, valor):
    monkeypatch.setenv("OLLAMA_DISPOSITIVO", valor)
    co.generate("hola", "llama3.2:1b", 100)
    assert envios[0]["options"]["num_gpu"] == 0


@pytest.mark.parametrize("valor", [None, "auto", "", "gpu", "cualquier cosa"])
def test_sin_cpu_no_se_toca_la_gpu(monkeypatch, envios, valor):
    if valor is None:
        monkeypatch.delenv("OLLAMA_DISPOSITIVO", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_DISPOSITIVO", valor)
    co.generate("hola", "llama3.2:1b", 100)
    assert "num_gpu" not in envios[0]["options"]


def test_una_opcion_explicita_gana_sobre_el_dispositivo(monkeypatch, envios):
    monkeypatch.setenv("OLLAMA_DISPOSITIVO", "cpu")
    co.generate("hola", "m", 100, opciones={"num_gpu": 5})
    assert envios[0]["options"]["num_gpu"] == 5


def test_con_gpu_el_modelo_auto_es_el_de_3b_salvo_que_ollama_sea_solo_cpu(monkeypatch):
    monkeypatch.setattr(m.hardware, "detect_gpu_vendor", lambda: "nvidia")
    monkeypatch.delenv("OLLAMA_DISPOSITIVO", raising=False)
    assert m._resolve_ollama_model("auto") == "llama3.2:3b"
    monkeypatch.setenv("OLLAMA_DISPOSITIVO", "cpu")
    assert m._resolve_ollama_model("auto") == "llama3.2:1b"


def test_un_modelo_elegido_a_mano_se_respeta_aunque_sea_solo_cpu(monkeypatch):
    monkeypatch.setenv("OLLAMA_DISPOSITIVO", "cpu")
    assert m._resolve_ollama_model("qwen2.5:7b") == "qwen2.5:7b"
