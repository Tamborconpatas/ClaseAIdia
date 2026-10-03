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


def carpeta_de_respaldos() -> Path:
    return Path(os.environ.get("CARPETA_RESPALDOS", "respaldos"))


def estado(carpeta: Path) -> dict:
    """Lo que se ve de los respaldos que hay: la fecha del último (por el nombre del archivo), cuántos y cuánto ocupan."""
    copias = sorted(carpeta.glob("escuela-*.db")) if carpeta.is_dir() else []
    ultimo = None
    if copias:
        try:
            ultimo = datetime.date.fromisoformat(copias[-1].stem.removeprefix("escuela-"))
        except ValueError:
            ultimo = None
    return {"ultimo": ultimo, "cantidad": len(copias), "mb": round(sum(c.stat().st_size for c in copias) / 1e6, 1)}


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


class ErrorRespaldo(Exception):
    """Un respaldo que no se puede usar (falta, está dañado o no es de ClaseAIdia): se explica en palabras de persona."""


def _abrir_solo_lectura(ruta: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)


def verificar(copia: Path) -> None:
    """Comprueba, sin tocar nada, que `copia` sea una base de ClaseAIdia íntegra. Un respaldo que nunca se probó es solo una esperanza."""
    if not copia.is_file():
        raise ErrorRespaldo(f"No existe el respaldo {copia}.")
    try:
        con = _abrir_solo_lectura(copia)
        try:
            integridad = con.execute("PRAGMA integrity_check").fetchall()
            tablas = {fila[0] for fila in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise ErrorRespaldo(f"{copia.name} no se puede leer como base de datos ({e}).") from e
    if integridad != [("ok",)]:
        raise ErrorRespaldo(f"{copia.name} está dañado: la revisión de integridad falló.")
    if not {"colegios", "usuarios"} <= tablas:
        raise ErrorRespaldo(f"{copia.name} es una base de datos, pero no parece ser de ClaseAIdia.")


def ultima_copia(carpeta: Path) -> Path | None:
    copias = sorted(carpeta.glob("escuela-*.db")) if carpeta.is_dir() else []
    return copias[-1] if copias else None


def restaurar(copia: Path, destino: Path, ahora: datetime.datetime) -> Path | None:
    """Deja `copia` como la base `destino`. Antes la verifica; si no sirve, no se toca nada. La base que había no se borra: queda al
    lado con la fecha. Devuelve dónde quedó (None si no había). El servidor tiene que estar apagado."""
    verificar(copia)
    nueva = destino.with_name(destino.name + ".restaurando")
    nueva.unlink(missing_ok=True)
    src, dst = _abrir_solo_lectura(copia), sqlite3.connect(nueva)
    try:
        src.backup(dst)
    finally:
        dst.close(), src.close()
    anterior = None
    if destino.exists():
        anterior = destino.with_name(f"{destino.stem}-antes-de-restaurar-{ahora:%Y%m%d-%H%M%S}{destino.suffix}")
        os.replace(destino, anterior)
    for resto in ("-wal", "-shm", "-journal"):  # de la base anterior: con la nueva no corresponden
        Path(str(destino) + resto).unlink(missing_ok=True)
    os.replace(nueva, destino)
    return anterior
