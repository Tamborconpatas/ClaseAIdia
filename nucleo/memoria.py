"""Cuánta memoria hay y cuánta usa el proceso, sin librerías extra (Windows y Linux).

El servidor del colegio es un equipo modesto que corre 24/7: procesar una clase no puede agotar la memoria ni tumbar
el sistema. Estas funciones dejan que el resto del código mire cuánta hay antes de empezar algo pesado, espere si
falta, y vigile a su propio proceso. Si no se puede saber (otro sistema), devuelven `None` y quien las usa no bloquea.
"""
import ctypes
import os
import sys
import time

GB = 1024 ** 3


class _EstadoMemoria(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _leer_meminfo(texto: str) -> tuple[float, float] | None:
    """(total, disponible) en GB desde el contenido de /proc/meminfo."""
    valores = {}
    for linea in texto.splitlines():
        partes = linea.replace(":", " ").split()
        if len(partes) >= 2 and partes[1].isdigit():
            valores[partes[0]] = int(partes[1]) * 1024
    if "MemTotal" in valores and "MemAvailable" in valores:
        return valores["MemTotal"] / GB, valores["MemAvailable"] / GB
    return None


def _total_y_libre() -> tuple[float, float] | None:
    if sys.platform == "win32":
        estado = _EstadoMemoria()
        estado.dwLength = ctypes.sizeof(_EstadoMemoria)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return estado.ullTotalPhys / GB, estado.ullAvailPhys / GB
        return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            return _leer_meminfo(f.read())
    except OSError:
        return None


def memoria_total_gb() -> float | None:
    datos = _total_y_libre()
    return datos[0] if datos else None


def memoria_libre_gb() -> float | None:
    """Memoria que se puede usar sin que el sistema empiece a ahogarse (la «disponible», no solo la «libre»)."""
    datos = _total_y_libre()
    return datos[1] if datos else None


def memoria_del_proceso_gb() -> float | None:
    """Memoria física que usa este proceso ahora."""
    try:
        if sys.platform == "win32":
            from ctypes import wintypes

            class _Contadores(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Contadores), wintypes.DWORD]
            c = _Contadores()
            c.cb = ctypes.sizeof(_Contadores)
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return c.WorkingSetSize / GB
            return None
        with open("/proc/self/statm", encoding="utf-8") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / GB
    except (OSError, ValueError, AttributeError):
        return None


def esperar_memoria(minimo_gb: float, espera_max_s: float, intervalo_s: float = 15, libre=memoria_libre_gb, dormir=time.sleep) -> bool:
    """Espera (hasta `espera_max_s`) a que haya al menos `minimo_gb` disponibles. True si hay; False si se acabó la
    espera sin que alcanzara. Si no se puede medir la memoria no se bloquea a nadie: devuelve True."""
    esperado = 0.0
    while True:
        disponible = libre()
        if disponible is None or disponible >= minimo_gb:
            return True
        if esperado >= espera_max_s:
            return False
        dormir(intervalo_s)
        esperado += intervalo_s
