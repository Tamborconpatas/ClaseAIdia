# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import secrets
import string

_ALFABETO = string.ascii_uppercase + string.digits


def generar_codigo_invitacion(largo: int = 6) -> str:
    """Código corto para que un alumno se una a un curso vía código/QR."""
    return "".join(secrets.choice(_ALFABETO) for _ in range(largo))
