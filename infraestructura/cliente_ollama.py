# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from nucleo.recursos import hilos_de_procesamiento

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


def ollama_solo_cpu() -> bool:
    """Con `OLLAMA_DISPOSITIVO=cpu` Ollama genera solo con la CPU aunque el equipo tenga GPU: así la GPU queda para
    Whisper (la parte lenta de una clase) y los resúmenes corren en paralelo sin pelear por la misma memoria de video.
    Cualquier otro valor (por defecto `auto`) deja que Ollama decida."""
    return os.environ.get("OLLAMA_DISPOSITIVO", "auto").strip().lower() == "cpu"


def ventana_necesaria(prompt: str, max_tokens: int) -> int:
    """Tokens de contexto que hacen falta para el prompt y la respuesta, en múltiplos de 1024."""
    tokens = len(prompt) // _CARACTERES_POR_TOKEN + max_tokens + _MARGEN_TOKENS
    return min(_VENTANA_MAXIMA, max(_VENTANA_MINIMA, -(-tokens // 1024) * 1024))


# Más bajo que el valor por defecto de Ollama (0,8): resumir fielmente no pide creatividad, y con 0,8 el mismo
# texto daba resúmenes de 373 y de 1.383 caracteres en dos corridas seguidas.
_TEMPERATURA = 0.3

# Ollama mantiene el modelo en memoria 5 minutos después de la última respuesta (1,6 a 4,8 GB que un equipo modesto con
# servidor 24/7 no puede regalar). Aquí se suelta al minuto: las llamadas de una clase van seguidas, así que no se recarga.
_MANTENER_CARGADO = "60s"


def _ejecutable_de_ollama() -> str | None:
    en_path = shutil.which("ollama")
    if en_path:
        return en_path
    local = os.environ.get("LOCALAPPDATA")  # instalación por defecto en Windows (no siempre queda en el PATH)
    candidato = Path(local) / "Programs" / "Ollama" / "ollama.exe" if local else None
    return str(candidato) if candidato and candidato.is_file() else None


def asegurar_ollama(ollama_url: str, esperar_s: float = 30) -> bool:
    """Ollama es un programa aparte y, en un servidor sin nadie al teclado, nadie lo vuelve a abrir si se cae o si el equipo
    se reinició: si no responde y es el de este mismo equipo, se arranca. Devuelve si quedó respondiendo."""
    def responde() -> bool:
        try:
            return requests.get(f"{ollama_url}/api/tags", timeout=3).status_code == 200
        except requests.exceptions.RequestException:
            return False

    if responde():
        return True
    if urlparse(ollama_url).hostname not in ("localhost", "127.0.0.1", "::1"):
        return False  # uno remoto no se puede arrancar desde aquí
    ejecutable = _ejecutable_de_ollama()
    if not ejecutable:
        return False
    extra = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {"start_new_session": True}
    try:
        subprocess.Popen([ejecutable, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
    except OSError:
        return False
    limite = time.monotonic() + esperar_s
    while time.monotonic() < limite:
        if responde():
            return True
        time.sleep(1)
    return False


def generate(
    prompt: str, model: str, max_tokens: int, ollama_url: str = "http://localhost:11434", ventana: int | None = None,
    imagenes: list[str] | None = None, opciones: dict | None = None, formato: dict | None = None,
) -> str:
    """Transporte puro hacia la API de Ollama: envía un prompt y devuelve el
    texto crudo de la respuesta. No sabe nada de prompts de dominio ni de
    cómo parsear el resultado — eso vive en la capa de servicios."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": _MANTENER_CARGADO,
        "options": {
            "num_predict": max_tokens,
            # `ventana` fija la misma para varias llamadas seguidas: cambiarla obliga a Ollama a recargar el modelo.
            "num_ctx": ventana or ventana_necesaria(prompt, max_tokens),
            "temperature": _TEMPERATURA,
            "num_thread": hilos_de_procesamiento(),  # un núcleo libre para que el servidor siga atendiendo
            **({"num_gpu": 0} if ollama_solo_cpu() else {}),  # 0 capas en la GPU
            **(opciones or {}),
        }
    }
    if imagenes:  # en base64, para un modelo con visión
        payload["images"] = imagenes
    if formato:  # esquema JSON: Ollama obliga al modelo a responder con esa forma (sin texto de más ni sintaxis rota)
        payload["format"] = formato

    try:
        try:
            response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=_REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.ConnectionError:
            if not asegurar_ollama(ollama_url):
                raise
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


def descargar_modelo(model: str, ollama_url: str = "http://localhost:11434") -> None:
    """Saca el modelo de la memoria ya (Ollama lo hace solo al minuto; entre dos modelos grandes no hay que esperar)."""
    try:
        requests.post(f"{ollama_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=15)
    except requests.exceptions.RequestException:
        pass  # si no se pudo, se descarga solo por su tiempo de espera
