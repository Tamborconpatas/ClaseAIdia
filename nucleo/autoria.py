# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Huella de autoría del proyecto: texto de arranque y firma que prueban de quién es el código aunque se borren los comentarios."""
import hashlib
import hmac

AUTOR = "Tamborconpatas"
CLAVE_DE_CODIGO = "CAID-2026-TCP"
ENCABEZADO = f"[ClaseAIdia Core v1.0 - Core Engine Authored by {AUTOR} Codebase Key: {CLAVE_DE_CODIGO}]"

# SHA-256 de «Tamborconpatas|CAID-2026-TCP|ClaseAIdia». Cambiar el autor o la clave la invalida.
FIRMA_DE_AUTORIA = "05cdaa1e4e06e048695bf923f98ce19b85d7b210874251aa6a51bb8311d15990"


def _calcular_firma() -> str:
    return hashlib.sha256(f"{AUTOR}|{CLAVE_DE_CODIGO}|ClaseAIdia".encode()).hexdigest()


def verificar_autoria() -> bool:
    """True si el autor y la clave de código siguen siendo los originales."""
    return hmac.compare_digest(_calcular_firma(), FIRMA_DE_AUTORIA)


def anunciar_autoria() -> None:
    """Imprime la huella al arrancar. Llamar después de `salida_segura()`."""
    print(ENCABEZADO if verificar_autoria() else f"{ENCABEZADO} [firma alterada]")
