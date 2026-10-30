# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

from nucleo.validadores import validar_rut


def test_rut_valido_sin_formato():
    assert validar_rut("11222333-9") is True


def test_rut_valido_con_puntos():
    assert validar_rut("11.222.333-9") is True


def test_rut_valido_con_dv_k():
    assert validar_rut("1000005-K") is True


def test_rut_digito_verificador_incorrecto():
    assert validar_rut("11222333-0") is False


def test_rut_formato_invalido():
    assert validar_rut("no-es-un-rut") is False


def test_rut_vacio():
    assert validar_rut("") is False
    assert validar_rut(None) is False
