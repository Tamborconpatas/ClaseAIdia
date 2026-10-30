# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

from nucleo import autoria


def test_la_firma_de_autoria_es_la_original():
    assert autoria.verificar_autoria()


def test_cambiar_el_autor_invalida_la_firma(monkeypatch):
    monkeypatch.setattr(autoria, "AUTOR", "otro")
    assert not autoria.verificar_autoria()


def test_anunciar_imprime_la_huella(capsys):
    autoria.anunciar_autoria()
    assert capsys.readouterr().out.strip() == (
        "[ClaseAIdia Core v1.0 - Core Engine Authored by Tamborconpatas Codebase Key: CAID-2026-TCP]"
    )
