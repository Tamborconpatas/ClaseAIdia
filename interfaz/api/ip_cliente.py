"""Dirección real de quien hace la petición.

Con el servidor a la vista (sin proxy delante), es la de la conexión. Detrás del nginx del despliegue con Docker toda
conexión llega desde el contenedor del proxy; ahí `CABECERA_IP_CLIENTE` nombra la cabecera donde el proxy escribe la
dirección real (y la sobrescribe siempre, nunca la copia del cliente). Esa cabecera solo se cree si la conexión viene de
una dirección privada o local, es decir, del proxy: no se configura si el servidor es alcanzable sin pasar por él.
"""
import ipaddress
import os

from fastapi import Request


def cabecera_configurada() -> str:
    return os.environ.get("CABECERA_IP_CLIENTE", "").strip().lower()


def _ip(valor: str | None):
    try:
        ip = ipaddress.ip_address((valor or "").strip())
    except ValueError:
        return None
    return getattr(ip, "ipv4_mapped", None) or ip


def ip_del_cliente(request: Request):
    """La dirección (objeto `ipaddress`) de quien pide, o None si no se puede saber."""
    directa = _ip(request.client.host if request.client else None)
    cabecera = cabecera_configurada()
    if not cabecera:
        return directa
    if directa is None or not (directa.is_private or directa.is_loopback or directa.is_link_local):
        return directa  # no viene del proxy: la cabecera sería inventada por el cliente
    return _ip(request.headers.get(cabecera))
