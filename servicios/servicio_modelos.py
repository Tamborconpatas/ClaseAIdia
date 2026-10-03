"""Instalar un modelo de IA desde la propia aplicación.

La app se reparte portable y la usa gente de un colegio: nadie abre una consola para escribir `ollama pull`. El UTP pulsa
«Descargar» en Ajustes y esto le pide a Ollama (que tiene que estar instalado en el equipo) que baje el modelo, mostrando el
avance. Necesita internet, una sola vez. La descarga corre en un hilo aparte y se consulta por su estado; reiniciar el
servidor la corta (Ollama retoma lo ya descargado al volver a pedirla).
"""
import json
import threading

import requests

from infraestructura.cliente_ollama import asegurar_ollama

_candado = threading.Lock()
_descargas: dict[str, dict] = {}  # por modelo: {estado: descargando|lista|error, porcentaje, mensaje}


class ErrorModelo(Exception):
    def __init__(self, detalle: str, estado: int = 409):
        super().__init__(detalle)
        self.detalle, self.estado = detalle, estado


def instalado(modelo: str, url: str) -> bool | None:
    """True/False según Ollama; None si Ollama no responde (no se sabe)."""
    try:
        # Conectar con espera corta: en Windows un puerto cerrado tarda ~2 s en rechazar (medido) y la pantalla de Ajustes pregunta a menudo.
        r = requests.get(f"{url}/api/tags", timeout=(1, 3))
        r.raise_for_status()
        modelos = r.json().get("models", [])
    except (requests.RequestException, ValueError):
        return None
    nombres = {m.get("name") for m in modelos} | {m.get("model") for m in modelos}
    return modelo in nombres or f"{modelo}:latest" in nombres


def estado_de_descarga(modelo: str) -> dict | None:
    with _candado:
        d = _descargas.get(modelo)
        return dict(d) if d else None


def _poner(modelo: str, **cambios) -> None:
    with _candado:
        _descargas.setdefault(modelo, {}).update(cambios)


def _traducir(estado: str) -> str:
    estado = estado.lower()
    if "manifest" in estado:
        return "Preparando la descarga…"
    if "verifying" in estado or "writing" in estado:
        return "Verificando lo descargado…"
    if estado == "success":
        return "Listo"
    return "Descargando…"


def _motivo_de_error(texto: str) -> str:
    t = texto.lower()
    if any(p in t for p in ("no such host", "dial tcp", "lookup", "timeout", "i/o timeout", "connection refused", "network")):
        return "No se pudo descargar el modelo: el equipo no parece tener internet. Revisa la conexión y vuelve a intentarlo."
    return f"No se pudo descargar el modelo: {texto[:150]}"


def _correr(modelo: str, url: str) -> None:
    """El trabajo de la descarga (se llama en un hilo). Deja el resultado en el estado, nunca lanza."""
    try:
        if not asegurar_ollama(url):
            raise ErrorModelo("Ollama no está abierto en este equipo. Ábrelo (o instálalo desde ollama.com) y vuelve a intentarlo.")
        capas: dict[str, tuple[int, int]] = {}
        with requests.post(f"{url}/api/pull", json={"model": modelo, "stream": True}, stream=True, timeout=(10, 300)) as r:
            if r.status_code != 200:
                raise ErrorModelo(_motivo_de_error(r.text), r.status_code)
            for linea in r.iter_lines():
                if not linea:
                    continue
                d = json.loads(linea)
                if "error" in d:
                    raise ErrorModelo(_motivo_de_error(str(d["error"])))
                if d.get("total"):
                    capas[d.get("digest") or d.get("status", "")] = (int(d.get("completed", 0)), int(d["total"]))
                total = sum(t for _, t in capas.values())
                hecho = sum(c for c, _ in capas.values())
                _poner(modelo, porcentaje=round(min(99.0, hecho / total * 100), 1) if total else 0.0, mensaje=_traducir(str(d.get("status", ""))))
        _poner(modelo, estado="lista", porcentaje=100.0, mensaje="Listo")
    except ErrorModelo as e:
        _poner(modelo, estado="error", mensaje=e.detalle)
    except (requests.RequestException, ValueError) as e:
        _poner(modelo, estado="error", mensaje=_motivo_de_error(str(e)) if isinstance(e, requests.RequestException) else "Ollama respondió algo que no se entiende.")


def iniciar_descarga(modelo: str, url: str, ya_esta: bool | None = None) -> dict:
    """Empieza a bajar el modelo (sin esperar). 409 si ya se está bajando o si ya está instalado. `ya_esta`: lo que el llamador
    acaba de averiguar con `instalado` (así no se le pregunta dos veces a Ollama en el mismo pedido)."""
    if (instalado(modelo, url) if ya_esta is None else ya_esta):
        raise ErrorModelo("El modelo ya está instalado")
    with _candado:
        actual = _descargas.get(modelo)
        if actual and actual["estado"] == "descargando":
            raise ErrorModelo("Ya se está descargando")
        _descargas[modelo] = {"estado": "descargando", "porcentaje": 0.0, "mensaje": "Preparando la descarga…"}
    threading.Thread(target=_correr, args=(modelo, url), daemon=True, name=f"descarga-{modelo}").start()
    return estado_de_descarga(modelo)  # type: ignore[return-value]
