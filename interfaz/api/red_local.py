"""La grabación de clases solo se controla desde la red del colegio (frontera de privacidad del proyecto).

Es una restricción real, del servidor: no depende de que el frontend oculte un botón. Una conexión es local
si viene de una dirección privada o de este mismo equipo Y no pasó por un proxy o túnel (que ponen sus
propias cabeceras): un túnel de Cloudflare se conecta desde localhost, y sin esta segunda regla parecería local.
"""
import ipaddress

from fastapi import HTTPException, Request

from interfaz.api.ip_cliente import cabecera_configurada, ip_del_cliente

# Solo lo que de verdad es de la red del colegio o de este equipo. (No `ip.is_private`: incluye rangos de
# documentación como 203.0.113.0/24, que no son una red local.)
REDES_LOCALES = [
    ipaddress.ip_network(r)
    for r in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10")
]
CABECERAS_DE_PROXY = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip", "true-client-ip")


def es_red_local(request: Request) -> bool:
    propia = cabecera_configurada()  # la que escribe nuestro proxy con la dirección real: no cuenta como «pasó por un túnel»
    if any(h in request.headers for h in CABECERAS_DE_PROXY if h != propia):
        return False
    ip = ip_del_cliente(request)
    if ip is None:
        return False
    return any(ip in red for red in REDES_LOCALES if red.version == ip.version)


def solo_red_local(request: Request) -> None:
    if not es_red_local(request):
        raise HTTPException(status_code=403, detail="La grabación de clases solo se controla desde la red del colegio")
