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


# Alumnos de 7° básico a 4° medio: nacidos desde ~1999, con RUT de más de 10 millones. Más abajo, o con
# todos los dígitos iguales o en secuencia (12.345.678-5 tiene dígito verificador válido y es el RUT falso clásico),
# no es de un alumno real. No se puede saber si el RUT existe sin consultar al Registro Civil.
RUT_MINIMO_ALUMNO = 10_000_000


def rut_de_alumno_plausible(rut: str) -> bool:
    cuerpo = normalizar_rut(rut).split("-")[0]
    return (
        validar_rut(rut)
        and int(cuerpo) >= RUT_MINIMO_ALUMNO
        and len(set(cuerpo)) > 1
        and cuerpo not in ("12345678", "87654321")
    )
