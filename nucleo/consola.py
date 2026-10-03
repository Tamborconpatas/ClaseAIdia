"""La salida de texto (print) del servidor y del trabajador nunca debe tumbar el programa."""
import sys


def salida_segura() -> None:
    """Pasa la salida estándar y la de errores a UTF-8 y hace que imprimir no pueda fallar.

    Con la salida redirigida (un archivo de registro, un servicio de Windows, un `.exe` sin consola) Python usa la
    codificación del sistema (cp1252 en Windows) y cualquier `print` con ✓ o un emoji lanzaba `UnicodeEncodeError`: la API
    no arrancaba y el procesamiento de las clases fallaba. En una consola interactiva nunca se notaba."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):  # sin consola (`pythonw`, un `.exe` de ventana) el flujo es None: no hay nada que ajustar
            flujo.reconfigure(encoding="utf-8", errors="replace")
