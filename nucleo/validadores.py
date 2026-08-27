import re


def validar_rut(rut: str) -> bool:
    """Valida el dígito verificador de un RUT chileno (ej. '12345678-5' o '12.345.678-5')."""
    rut_limpio = re.sub(r"[.\s]", "", rut or "").upper()
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
