import requests


def generate(prompt: str, model: str, max_tokens: int, ollama_url: str = "http://localhost:11434") -> str:
    """Transporte puro hacia la API de Ollama: envía un prompt y devuelve el
    texto crudo de la respuesta. No sabe nada de prompts de dominio ni de
    cómo parsear el resultado — eso vive en la capa de servicios."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens
        }
    }

    try:
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=180)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"No se pudo conectar a Ollama. Asegúrate de tener Ollama corriendo localmente "
            f"('ollama serve') y el modelo '{model}' instalado ('ollama run {model}')."
        )
    except Exception as e:
        raise RuntimeError(f"Excepción al contactar a Ollama: {str(e)}")

    if response.status_code != 200:
        raise RuntimeError(f"Error de Ollama: {response.text}")

    raw = response.json().get("response", "").strip()
    if not raw:
        raise RuntimeError("Respuesta vacía del LLM.")

    return raw
