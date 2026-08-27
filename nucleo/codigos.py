import secrets
import string

_ALFABETO = string.ascii_uppercase + string.digits


def generar_codigo_invitacion(largo: int = 6) -> str:
    """Código corto para que un alumno se una a un curso vía código/QR."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(largo))
