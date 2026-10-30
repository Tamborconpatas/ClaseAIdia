# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

from nucleo.autoria import anunciar_autoria
from nucleo.consola import salida_segura

salida_segura()  # antes que cualquier otra cosa: con la salida redirigida un print con ✓ o emoji tumbaba el arranque
anunciar_autoria()

from nucleo.configuracion import cargar_env  # noqa: E402

# Antes de importar la app: infraestructura/seguridad.py lee JWT_SECRET_KEY al importarse.
cargar_env()

from interfaz.api.aplicacion import crear_app

app = crear_app(vigilar=True)
