# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Restaura la base de datos desde un respaldo (para quien administra el servidor; el colegio no corre comandos).

    python -m scripts.restaurar_respaldo                      # muestra lo que haría con el último respaldo
    python -m scripts.restaurar_respaldo --si                 # lo hace
    python -m scripts.restaurar_respaldo respaldos/escuela-2026-10-01.db --si

El servidor tiene que estar apagado. La base que había se conserva al lado, con la fecha, y al terminar se aplican las
migraciones (un respaldo de una versión anterior queda al día).
"""
import datetime
import os
import ssl
import sys
import urllib.request
from pathlib import Path

from nucleo.consola import salida_segura

salida_segura()

from nucleo.configuracion import cargar_env  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DIRECCIONES = ("http://127.0.0.1:8000/salud", "https://127.0.0.1:8443/salud")


def _servidor_en_marcha() -> bool:
    """Restaurar con el servidor andando le cambiaría la base bajo los pies."""
    contexto = ssl.create_default_context()
    contexto.check_hostname, contexto.verify_mode = False, ssl.CERT_NONE  # el certificado propio no es de confianza, y no importa para esto
    for url in DIRECCIONES:
        try:
            with urllib.request.urlopen(url, timeout=2, context=contexto):
                return True  # urlopen lanza error con un 4xx o 5xx: si contesta bien, hay un servidor
        except OSError:
            continue
    return False


def _base_actual() -> Path | None:
    from sqlalchemy.engine import make_url

    url = make_url(os.environ.get("DATABASE_URL", "sqlite:///./escuela.db"))
    return Path(url.database) if url.get_backend_name() == "sqlite" and url.database else None


def _migrar(destino: Path) -> bool:
    """Pone la base al día con las migraciones. False si no se puede: una base creada sin ellas no registra en qué versión está."""
    import sqlite3

    from alembic import command
    from alembic.config import Config

    con = sqlite3.connect(destino)
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'").fetchone() is None:
            return False
    finally:
        con.close()
    os.environ["DATABASE_URL"] = f"sqlite:///{destino.resolve().as_posix()}"  # alembic/env.py lo lee de aquí
    configuracion = Config(str(RAIZ / "alembic.ini"))
    configuracion.set_main_option("script_location", str(RAIZ / "alembic"))
    command.upgrade(configuracion, "head")
    return True


def main(argv: list[str], ahora: datetime.datetime | None = None) -> int:
    from servicios import servicio_respaldo as sr

    cargar_env()
    confirmado = "--si" in argv
    pedidos = [a for a in argv if a != "--si"]
    destino = _base_actual()
    if destino is None:
        print("Solo se pueden restaurar bases SQLite (la de este servidor no lo es).")
        return 1
    copia = Path(pedidos[0]) if pedidos else sr.ultima_copia(sr.carpeta_de_respaldos())
    if copia is None:
        print(f"No hay respaldos en {sr.carpeta_de_respaldos().resolve()}.")
        return 1
    if _servidor_en_marcha():
        print("El servidor está encendido. Apágalo antes de restaurar (scripts\\windows\\quitar_servidor.bat) y vuelve a correr esto.")
        return 2
    try:
        sr.verificar(copia)
    except sr.ErrorRespaldo as e:
        print(f"No se restaura nada: {e}")
        return 1
    print(f"Respaldo: {copia.resolve()}\nBase que se reemplaza: {destino.resolve()} (se conserva al lado, con la fecha)")
    if not confirmado:
        print("No se hizo nada todavía. Para restaurar de verdad, agrega --si.")
        return 0
    anterior = sr.restaurar(copia, destino, ahora or datetime.datetime.now())
    al_dia = _migrar(destino)
    if anterior is not None:
        print(f"La base anterior quedó en {anterior.resolve()}.")
    if not al_dia:
        print("Aviso: esta base no registra su versión (se creó sin las migraciones), así que no se pudo ponerla al día. Si el servidor da errores, hay que actualizarla a mano.")
    print("Listo: la base se restauró. Vuelve a iniciar el servidor (scripts\\windows\\instalar_servidor.bat).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
