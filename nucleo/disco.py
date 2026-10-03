"""Espacio en el disco donde el servidor guarda lo que escribe (audio temporal, base de datos, respaldos)."""
import shutil
from pathlib import Path


def ancestro_existente(ruta: Path) -> Path | None:
    """La ruta, o la carpeta más cercana que exista por encima de ella (una carpeta de audio todavía no creada vive en el mismo disco que su padre)."""
    p = Path(ruta).resolve()
    while not p.exists():
        if p.parent == p:
            return None
        p = p.parent
    return p


def espacio_en_disco(ruta: Path) -> tuple[float, float]:
    """(libre, total) en GB del disco donde está `ruta`. Si no se puede saber, `(inf, inf)`: ante la duda no se bloquea nada."""
    base = ancestro_existente(ruta)
    if base is None:
        return float("inf"), float("inf")
    try:
        uso = shutil.disk_usage(base)
    except OSError:
        return float("inf"), float("inf")
    return uso.free / 1e9, uso.total / 1e9
