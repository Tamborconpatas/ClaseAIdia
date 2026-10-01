"""Restablece la contraseña de un UTP desde la consola del servidor.

Es el último recurso cuando el único UTP olvidó su contraseña (si hay otro UTP, él puede generarle un código
desde la pestaña Profesores). Es seguro sin correo ni preguntas secretas porque exige acceso al PC del
colegio, donde vive la base de datos: quien llegue hasta acá ya manda sobre todos los datos.

    python -m scripts.restablecer_utp 12345678-5

Pide la contraseña nueva dos veces (sin mostrarla). Con la base de demostración:

    DATABASE_URL=sqlite:///./escuela_demo.db python -m scripts.restablecer_utp 11111111-1
"""
import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from infraestructura.basedatos import SessionLocal
from infraestructura.modelos_orm import RolNombre, Usuario
from infraestructura.seguridad import hashear_secreto
from interfaz.api.esquemas import _password_sin_rut, _password_valida
from nucleo.validadores import normalizar_rut, validar_rut


class ErrorRestablecer(Exception):
    """Algo que el administrador puede corregir (RUT, contraseña débil...)."""


def restablecer_clave(db: Session, rut: str, password: str) -> Usuario:
    """Fija una contraseña nueva a un UTP (con la misma política que el resto de la app) y lo desbloquea."""
    rut = normalizar_rut(rut)
    if not validar_rut(rut):
        raise ErrorRestablecer("RUT inválido: revisa el número y el dígito verificador.")
    usuario = db.query(Usuario).filter_by(rut=rut).first()
    if usuario is None or RolNombre.UTP not in {r.rol for r in usuario.roles}:
        raise ErrorRestablecer("No hay un UTP con ese RUT en esta base de datos.")
    try:
        _password_valida(password)
        _password_sin_rut(rut, password)
    except ValueError as e:
        raise ErrorRestablecer(str(e)) from e

    usuario.password_hash = hashear_secreto(password)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.codigo_reset_hash = None
    usuario.codigo_reset_vence = None
    db.commit()
    return usuario


def _leer_password(pregunta: str) -> str:
    """En una consola, sin mostrar lo que se escribe; si la entrada viene de un archivo o una tubería, la lee tal cual."""
    return getpass.getpass(pregunta) if sys.stdin.isatty() else sys.stdin.readline().rstrip("\r\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Restablece la contraseña de un UTP (último recurso).")
    parser.add_argument("rut", help="RUT del UTP, p. ej. 12345678-5")
    rut = parser.parse_args().rut

    password = _leer_password("Contraseña nueva: ")
    if password != _leer_password("Repite la contraseña: "):
        print("Las contraseñas no coinciden. No se cambió nada.", file=sys.stderr)
        return 1
    try:
        with SessionLocal() as db:
            usuario = restablecer_clave(db, rut, password)
            print(f"Listo: {usuario.nombre} ya puede entrar con la contraseña nueva.")
    except ErrorRestablecer as e:
        print(f"No se cambió nada: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
