from nucleo.configuracion import cargar_env

# Antes de importar la app: infraestructura/seguridad.py lee JWT_SECRET_KEY al importarse.
cargar_env()

from interfaz.api.aplicacion import crear_app

app = crear_app(vigilar=True)
