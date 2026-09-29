import datetime
import os
import secrets

import jwt
from passlib.context import CryptContext

_contexto_hash = CryptContext(schemes=["argon2"], deprecated="auto")

ALGORITMO = "HS256"
EXPIRACION_HORAS = 12
LIMITE_INTENTOS = 5
VIGENCIA_CODIGO_RESET_MINUTOS = 15

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    JWT_SECRET_KEY = secrets.token_hex(32)
    print(
        "⚠️  JWT_SECRET_KEY no definido — usando una clave temporal generada en memoria. "
        "Los tokens emitidos no sobrevivirán un reinicio. Definir JWT_SECRET_KEY en producción."
    )


def hashear_secreto(secreto: str) -> str:
    return _contexto_hash.hash(secreto)


def verificar_secreto(secreto: str, hash_guardado: str) -> bool:
    return _contexto_hash.verify(secreto, hash_guardado)


def crear_token(payload: dict) -> str:
    datos = payload.copy()
    datos["exp"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=EXPIRACION_HORAS)
    return jwt.encode(datos, JWT_SECRET_KEY, algorithm=ALGORITMO)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITMO])


def calcular_bloqueo(intentos_fallidos: int) -> datetime.timedelta:
    """Backoff creciente: 1, 2, 4, 8... minutos, tope 60. Se aplica desde
    el intento número LIMITE_INTENTOS en adelante."""
    minutos = 2 ** (intentos_fallidos - LIMITE_INTENTOS)
    return datetime.timedelta(minutes=min(minutos, 60))


def ahora_utc() -> datetime.datetime:
    """Naive UTC — SQLite no guarda zona horaria, así que todo lo que se
    compara contra columnas DateTime (bloqueado_hasta) usa este mismo tipo."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
