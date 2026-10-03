from nucleo.consola import salida_segura

salida_segura()  # antes que cualquier otra cosa: con la salida redirigida un print con ✓ o emoji tumbaba el arranque

from nucleo.configuracion import cargar_env  # noqa: E402

# Antes de importar la app: infraestructura/seguridad.py lee JWT_SECRET_KEY al importarse.
cargar_env()

from interfaz.api.aplicacion import crear_app

app = crear_app(vigilar=True)
