"""Proceso aparte que procesa una clase (transcribir y generar el material).

    python -m servicios.trabajador clase <id de la grabación>
    python -m servicios.trabajador generacion <id de la grabación>   # solo vuelve a generar el material

Corre separado del servidor web a propósito: el servidor del colegio es un equipo modesto que corre 24/7, y procesar una
clase es lo único que puede agotarle la memoria. Si ese trabajo se pasa, se corta **este** proceso (por su propio
vigilante, o porque el sistema lo cierra) y el servidor sigue atendiendo a alumnos y profesores; el servidor se entera
por el código de salida y deja la clase en error con el motivo, para reintentar.
"""
import os
import sys
import threading
import time

from nucleo.memoria import memoria_del_proceso_gb, memoria_total_gb

CODIGO_SIN_MEMORIA = 75  # código de salida de «me pasé del tope de memoria»; el servidor lo reconoce
FRACCION_DE_LA_MEMORIA = 0.6  # de la RAM del equipo, lo máximo que puede usar este proceso
TOPE_MAXIMO_GB = 8.0
TOPE_SI_NO_SE_SABE_GB = 6.0


def limite_de_memoria_gb() -> float:
    """Tope de memoria del proceso: LIMITE_MEMORIA_PROCESAMIENTO_GB si se define; si no, el 60 % de la RAM del equipo
    (con un máximo de 8 GB). En un equipo de 8 GB son 4,8 GB; Whisper por tramos usa menos de 2."""
    pedido = os.environ.get("LIMITE_MEMORIA_PROCESAMIENTO_GB", "").strip()
    try:
        if pedido and float(pedido) > 0:
            return float(pedido)
    except ValueError:
        pass
    total = memoria_total_gb()
    return min(TOPE_MAXIMO_GB, total * FRACCION_DE_LA_MEMORIA) if total else TOPE_SI_NO_SE_SABE_GB


def vigilar_memoria(limite_gb: float, intervalo_s: float = 1.0, leer=memoria_del_proceso_gb, salir=os._exit) -> threading.Thread:
    """Hilo que mira cuánta memoria usa este proceso y, si pasa del tope, lo cierra con CODIGO_SIN_MEMORIA antes de que
    el sistema operativo tenga que elegir qué cerrar (que puede ser cualquier otro programa del equipo).
    Se puede detener con `hilo.detener.set()` (los tests lo necesitan: un vigilante olvidado seguiría vivo para siempre)."""
    detener = threading.Event()

    def ciclo():
        while not detener.wait(intervalo_s):
            uso = leer()
            if uso is not None and uso > limite_gb:
                print(f"AVISO: el procesamiento usa {uso:.1f} GB, más del tope de {limite_gb:.1f} GB: se corta para no agotar la memoria del equipo.", flush=True)
                salir(CODIGO_SIN_MEMORIA)
                return  # con os._exit nunca se llega aquí; con otro `salir` no se repite el aviso sin fin

    hilo = threading.Thread(target=ciclo, daemon=True, name="vigilante-de-memoria")
    hilo.detener = detener
    hilo.start()
    return hilo


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("clase", "generacion") or not argv[1].isdigit():
        print("uso: python -m servicios.trabajador (clase|generacion) <id de la grabación>", file=sys.stderr)
        return 2
    modo, grabacion_id = argv[0], int(argv[1])
    vigilar_memoria(limite_de_memoria_gb())
    # Los módulos pesados se importan después de armar el vigilante, y solo aquí: el servidor web no los carga.
    from infraestructura.basedatos import SessionLocal
    from servicios import servicio_grabacion as sg

    (sg.procesar if modo == "clase" else sg.procesar_generacion)(grabacion_id, SessionLocal)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
