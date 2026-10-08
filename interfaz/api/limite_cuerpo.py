"""Tope al tamaño de lo que se recibe, para que una petición enorme no llene la memoria del servidor.

Mira la cabecera `Content-Length` y, si el cliente manda el cuerpo por partes (sin largo declarado), cuenta lo que va llegando
y corta al pasarse. Las subidas de audio y de fotos tienen un tope mayor; todo lo demás es JSON corto.
"""
import re

MAX_JSON_BYTES = 1 * 1024 * 1024
MAX_SUBIDA_BYTES = 20 * 1024 * 1024  # igual que client_max_body_size del nginx del despliegue con Docker
RUTAS_DE_SUBIDA = re.compile(r"^/grabaciones/\d+/(trozos/[^/]+|fotos)$")
METODOS_CON_CUERPO = {"POST", "PUT", "PATCH", "DELETE"}


def tope_para(ruta: str) -> int:
    return MAX_SUBIDA_BYTES if RUTAS_DE_SUBIDA.match(ruta) else MAX_JSON_BYTES


async def _responder_413(send):
    cuerpo = b'{"detail":"El contenido enviado es demasiado grande"}'
    await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode()), (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": cuerpo})


class LimiteDeCuerpo:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in METODOS_CON_CUERPO:
            return await self.app(scope, receive, send)
        maximo = tope_para(scope["path"])
        declarado = dict(scope["headers"]).get(b"content-length", b"")
        if declarado.isdigit() and int(declarado) > maximo:
            return await _responder_413(send)

        contados = 0
        excedido = False

        async def receive_con_tope():
            nonlocal contados, excedido
            mensaje = await receive()
            if mensaje["type"] == "http.request" and not excedido:
                contados += len(mensaje.get("body", b""))
                if contados > maximo:
                    # La respuesta sale ya; la app ve una conexión cortada y lo que intente contestar después se descarta
                    # (FastAPI convertiría cualquier error al leer el cuerpo en un 400).
                    excedido = True
                    await _responder_413(send)
            if excedido:
                return {"type": "http.disconnect"}
            return mensaje

        async def send_si_no_se_corto(mensaje):
            if not excedido:
                await send(mensaje)

        try:
            await self.app(scope, receive_con_tope, send_si_no_se_corto)
        except Exception:
            if not excedido:
                raise
