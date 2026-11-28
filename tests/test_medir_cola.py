# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""`scripts/medir_cola.py` es una herramienta de medición: se prueba lo que decide cuándo empieza el resumen y qué proceso es cuál, no el servidor."""
from scripts import medir_cola as mc


def test_clasifica_los_procesos_que_importan_y_nada_mas():
    assert mc.clasificar("/usr/lib/ollama/llama-server --model x") == "modelo de Ollama"
    assert mc.clasificar("python -m servicios.trabajador clase 1") == "trabajador (Whisper)"
    assert mc.clasificar("python -m uvicorn api:app --port 8000") == "servidor web"
    assert mc.clasificar("/usr/bin/zsh -c ls") is None


def test_el_resumen_empieza_cuando_el_modelo_ocupa_mas_de_un_giga_despues_de_un_instante():
    m = mc.Muestreador()
    m.linea = [(0.0, {}), (5.0, {"modelo de Ollama": 0.4}), (10.0, {"modelo de Ollama": 4.7}), (20.0, {"modelo de Ollama": 4.8})]
    assert m.primer_modelo_cargado_desde(0.0) == 10.0
    assert m.primer_modelo_cargado_desde(12.0) == 20.0  # un modelo que ya estaba cargado antes no cuenta como el comienzo
    assert m.primer_modelo_cargado_desde(25.0) is None
