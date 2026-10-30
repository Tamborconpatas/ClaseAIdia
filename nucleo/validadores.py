# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import re


def normalizar_rut(rut: str) -> str:
    """Forma canónica para guardar y buscar: sin puntos ni espacios, DV en mayúscula."""
    return re.sub(r"[.\s]", "", rut or "").upper()


def validar_rut(rut: str) -> bool:
    """Valida el dígito verificador de un RUT chileno (ej. '12345678-5' o '12.345.678-5')."""
    rut_limpio = normalizar_rut(rut)
    if not re.fullmatch(r"\d{7,8}-[0-9K]", rut_limpio):
        return False

    numero, dv_informado = rut_limpio.split("-")

    suma = 0
    multiplicador = 2
    for digito in reversed(numero):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < 7 else 2

    resto = 11 - (suma % 11)
    dv_esperado = {11: "0", 10: "K"}.get(resto, str(resto))

    return dv_informado == dv_esperado
