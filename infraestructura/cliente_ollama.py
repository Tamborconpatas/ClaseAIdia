import requests

# Generar texto en CPU (hardware objetivo del proyecto, sin GPU) puede tardar
# varios minutos para un modelo de 7-9B con num_predict alto — 180s se queda
# corto en ese escenario real, así que el timeout queda generoso a propósito.
_REQUEST_TIMEOUT_SECONDS = 600


# Ollama usa por defecto una ventana de contexto de 4096 tokens (aunque el modelo soporte mucho más) y, si el
# prompt no cabe, recorta el principio: justo donde están las instrucciones. Con una clase larga el modelo dejaba
# de producir la hoja de repaso y las tarjetas sin avisar. Por eso la ventana se fija según el tamaño del prompt.
_CARACTERES_POR_TOKEN = 3  # el español ronda 3,5; se redondea hacia abajo para no quedar corto
_MARGEN_TOKENS = 256
_VENTANA_MINIMA = 4096
_VENTANA_MAXIMA = 16384  # más allá, el caché de contexto no cabe en una GPU de 4 GB junto al modelo


def ventana_necesaria(prompt: str, max_tokens: int) -> int:
    """Tokens de contexto que hacen falta para el prompt y la respuesta, en múltiplos de 1024."""
    tokens = len(prompt) // _CARACTERES_POR_TOKEN + max_tokens + _MARGEN_TOKENS
    return min(_VENTANA_MAXIMA, max(_VENTANA_MINIMA, -(-tokens // 1024) * 1024))


# Más bajo que el valor por defecto de Ollama (0,8): resumir fielmente no pide creatividad, y con 0,8 el mismo
# texto daba resúmenes de 373 y de 1.383 caracteres en dos corridas seguidas.
_TEMPERATURA = 0.3


def generate(
    prompt: str, model: str, max_tokens: int, ollama_url: str = "http://localhost:11434", ventana: int | None = None
) -> str:
    """Transporte puro hacia la API de Ollama: envía un prompt y devuelve el
    texto crudo de la respuesta. No sabe nada de prompts de dominio ni de
    cómo parsear el resultado — eso vive en la capa de servicios."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            # `ventana` fija la misma para varias llamadas seguidas: cambiarla obliga a Ollama a recargar el modelo.
            "num_ctx": ventana or ventana_necesaria(prompt, max_tokens),
            "temperature": _TEMPERATURA,
        }
    }

    try:
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"No se pudo conectar a Ollama. Asegúrate de tener Ollama corriendo localmente "
            f"('ollama serve') y el modelo '{model}' instalado ('ollama run {model}')."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Ollama tardó más de {_REQUEST_TIMEOUT_SECONDS}s en responder — en CPU, modelos "
            f"grandes o transcripciones largas pueden tardar bastante. Intenta con un modelo "
            f"más chico (ej. 'llama3:8b' cuantizado) o reduce el tamaño de bloque en Configuración."
        )
    except Exception as e:
        raise RuntimeError(f"Excepción al contactar a Ollama: {str(e)}")

    if response.status_code != 200:
        raise RuntimeError(f"Error de Ollama: {response.text}")

    raw = response.json().get("response", "").strip()
    if not raw:
        raise RuntimeError("Respuesta vacía del LLM.")

    return raw
