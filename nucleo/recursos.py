# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Cuánto del equipo puede usar el procesamiento de una clase.

El servidor del colegio es un equipo modesto que corre 24/7 y, mientras transcribe o genera el material de una
clase, tiene que seguir atendiendo a alumnos y profesores. Si Whisper u Ollama se llevaran todos los núcleos, la
página se pondría lenta justo cuando más gente la usa; por eso siempre se deja uno libre.
"""
import os

MAX_HILOS = 8  # más hilos que esto casi no acelera Whisper ni el LLM y solo gasta memoria


def hilos_de_procesamiento() -> int:
    """Núcleos para transcribir y generar: todos menos uno (mínimo 1, máximo MAX_HILOS)."""
    return min(MAX_HILOS, max(1, (os.cpu_count() or 2) - 1))
