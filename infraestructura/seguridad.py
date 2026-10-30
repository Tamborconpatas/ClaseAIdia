# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import datetime
import os
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # argon2id; el mismo formato que guardaba passlib, así que los hashes ya guardados siguen sirviendo

ALGORITMO = "HS256"
EXPIRACION_HORAS = 12
LIMITE_INTENTOS = 5
VIGENCIA_CODIGO_RESET_MINUTOS = 15

LARGO_MIN_CLAVE_JWT = 32


def cargar_clave_jwt(valor: str | None) -> str:
    """Sin clave: una temporal en memoria (las sesiones no sobreviven un reinicio).
    Con clave corta: error — una clave adivinable permite falsificar cualquier token."""
    if not valor:
        # Solo ASCII: con la salida redirigida en Windows (cp1252) un emoji haría fallar el arranque.
        print(
            "AVISO: JWT_SECRET_KEY no definido - usando una clave temporal generada en memoria. "
            "Los tokens emitidos no sobreviviran un reinicio. Definir JWT_SECRET_KEY en produccion."
        )
        return secrets.token_hex(32)
    if len(valor) < LARGO_MIN_CLAVE_JWT:
        raise RuntimeError(f"JWT_SECRET_KEY demasiado corta: minimo {LARGO_MIN_CLAVE_JWT} caracteres (ver .env.example)")
    return valor


JWT_SECRET_KEY = cargar_clave_jwt(os.environ.get("JWT_SECRET_KEY"))


def hashear_secreto(secreto: str) -> str:
    return _hasher.hash(secreto)


def verificar_secreto(secreto: str, hash_guardado: str) -> bool:
    try:
        return _hasher.verify(hash_guardado, secreto)
    except (VerificationError, InvalidHashError):
        return False


_HASH_FALSO = hashear_secreto("relleno-para-igualar-tiempos")


def verificar_secreto_falso(secreto: str) -> None:
    """Gasta lo mismo que una verificación real. Se llama cuando el RUT no existe,
    para que el tiempo de respuesta no delate qué RUT están registrados."""
    verificar_secreto(secreto, _HASH_FALSO)


def crear_token(payload: dict) -> str:
    datos = payload.copy()
    datos["exp"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=EXPIRACION_HORAS)
    return jwt.encode(datos, JWT_SECRET_KEY, algorithm=ALGORITMO)


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITMO], options={"require": ["exp", "sub"]})


def calcular_bloqueo(intentos_fallidos: int) -> datetime.timedelta:
    """Backoff creciente: 1, 2, 4, 8... minutos, tope 60. Se aplica desde
    el intento número LIMITE_INTENTOS en adelante."""
    minutos = 2 ** (intentos_fallidos - LIMITE_INTENTOS)
    return datetime.timedelta(minutes=min(minutos, 60))


def ahora_utc() -> datetime.datetime:
    """Naive UTC — SQLite no guarda zona horaria, así que todo lo que se
    compara contra columnas DateTime (bloqueado_hasta) usa este mismo tipo."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
