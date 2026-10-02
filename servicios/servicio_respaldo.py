"""Respaldo diario de la base de datos (horario, usuarios y texto de las clases; nunca audio).

Usa la copia en caliente de SQLite, así que es segura aunque el servidor esté atendiendo a alguien. Se conservan los
últimos días (`DIAS_DE_RESPALDO`, 14 por defecto). Una carpeta de respaldos en el mismo disco no protege de que el disco
falle: conviene apuntar `CARPETA_RESPALDOS` a otro disco o a una unidad externa.
"""
import datetime
import os
import sqlite3
from pathlib import Path

DIAS_POR_DEFECTO = 14


def respaldar_si_toca(origen: Path, carpeta: Path, ahora: datetime.datetime, conservar: int = DIAS_POR_DEFECTO) -> Path | None:
    """Copia `origen` a `carpeta/escuela-AAAA-MM-DD.db` si hoy aún no hay copia, y borra las más antiguas."""
    if not origen.is_file():
        return None
    destino = carpeta / f"escuela-{ahora:%Y-%m-%d}.db"
    if destino.exists():
        return None
    carpeta.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".parcial")  # una copia a medias (corte de luz) nunca se confunde con un respaldo
    src, dst = sqlite3.connect(origen), sqlite3.connect(parcial)
    try:
        src.backup(dst)
    except Exception:
        parcial.unlink(missing_ok=True)
        raise
    finally:
        dst.close(), src.close()
    os.replace(parcial, destino)
    for vieja in sorted(carpeta.glob("escuela-*.db"))[:-max(conservar, 1)]:
        vieja.unlink(missing_ok=True)
    return destino
