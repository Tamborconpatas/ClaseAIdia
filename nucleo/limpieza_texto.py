# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import re

# Frases que Whisper suele "alucinar" en silencios o audio ruidoso — vienen
# de su entrenamiento con subtítulos de YouTube, no de nada que el profesor
# haya dicho realmente. Sin filtrarlas, contaminan el resumen generado.
_FRASES_ALUCINADAS_RE = re.compile(
    r"subt[ií]tulos?\s+(realizados?|creados?|hechos?)\s+por.*|"
    r"subt[ií]tulos?\s+por\s+la\s+comunidad\s+de\s+amara\.org|"
    r"gracias\s+por\s+ver\s+(el|este)\s+v[ií]deo|"
    r"suscr[ií]bete\s+al\s+canal|"
    r"dale\s+(like|me\s+gusta)\s+y\s+suscr[ií]bete|"
    r"www\.youtube\.com|"
    r"traducci[oó]n\s+(realizada|hecha)\s+por.*",
    re.IGNORECASE,
)

# Una misma palabra repetida 4+ veces seguidas — típico bucle de alucinación
# de Whisper durante silencios largos (ej. "sí sí sí sí sí sí").
_REPETICION_RE = re.compile(r'\b(\w+)\b(?:\s+\1\b){3,}', re.IGNORECASE)


def limpiar_transcripcion(text: str) -> str:
    """Limpia artefactos típicos de ASR (frases alucinadas, bucles de
    palabras repetidas) antes de mandar el texto a un LLM para resumir.

    No se usa para el SRT ni para la transcripción cruda que ve el
    usuario — esas se dejan intactas, nada de lo transcrito se pierde;
    esta versión limpia solo alimenta la generación de material de estudio,
    para que esos artefactos no confundan al modelo."""
    if not text:
        return text

    cleaned = _FRASES_ALUCINADAS_RE.sub("", text)
    cleaned = _REPETICION_RE.sub(r'\1', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Puntuación huérfana que queda al borrar una frase completa (ej. "núcleo. . para").
    cleaned = re.sub(r'\s*([.,;:!?])(\s*\1)+', r'\1', cleaned)
    cleaned = re.sub(r'\s+([.,;:!?])', r'\1', cleaned)
    return cleaned.strip()
