# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Frenos a la adivinación de claves, además del bloqueo de cada cuenta.

- Por dirección: demasiados intentos fallidos desde una misma IP (contra cualquier cuenta) la dejan fuera un rato. Cubre
  lo que el bloqueo por cuenta no ve: probar una clave común contra muchas cuentas.
- Cuentas que no existen: se bloquean igual que las reales, para que la respuesta no delate quién está registrado.
"""
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from infraestructura.seguridad import LIMITE_INTENTOS, calcular_bloqueo
from interfaz.api.ip_cliente import ip_del_cliente
from nucleo.limitador import FallosDeCuentasInexistentes, LimitadorDeFallos

# Rutas donde un fallo es un intento de adivinar algo (clave, PIN, código de reseteo o código de curso).
RUTAS_VIGILADAS = {
    ("POST", "/auth/login/staff"),
    ("POST", "/auth/login/alumno"),
    ("POST", "/auth/restablecer-pin"),
    ("POST", "/auth/restablecer-password"),
    ("POST", "/cursos/unirse"),
}
ESTADOS_DE_FALLO = {401, 404, 409}


def _entero(nombre: str, defecto: int) -> int:
    try:
        return max(1, int(os.environ.get(nombre, defecto)))
    except ValueError:
        return defecto


# 30 fallos en 10 minutos por dirección: un curso entero que se equivoca una vez no alcanza, un script sí.
por_ip = LimitadorDeFallos(_entero("INTENTOS_LOGIN_POR_IP", 30), _entero("VENTANA_LOGIN_MINUTOS", 10) * 60)
sin_cuenta = FallosDeCuentasInexistentes(LIMITE_INTENTOS, calcular_bloqueo)


def reiniciar() -> None:
    por_ip.reiniciar()
    sin_cuenta.reiniciar()


def _clave(request: Request) -> str:
    ip = ip_del_cliente(request)
    return str(ip) if ip else "desconocida"


async def limitar_por_ip(request: Request, call_next):
    if (request.method, request.url.path) not in RUTAS_VIGILADAS:
        return await call_next(request)
    clave = _clave(request)
    espera = por_ip.segundos_de_espera(clave)
    if espera:
        return JSONResponse(
            status_code=429,
            content={"detail": "Demasiados intentos fallidos desde esta conexión. Espera unos minutos."},
            headers={"Retry-After": str(espera)},
        )
    respuesta = await call_next(request)
    if respuesta.status_code in ESTADOS_DE_FALLO:
        por_ip.registrar(clave)
    return respuesta
