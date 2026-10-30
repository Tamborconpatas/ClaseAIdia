# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

def format_timestamp(seconds: float):
    """Formatea segundos en formato de timestamp SRT estándar."""
    if seconds is None:
        return "00:00:00,000"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_srt(segments):
    """Toma un arreglo de segmentos con start/end/text y genera bloque SRT."""
    srt_content = []
    for i, seg in enumerate(segments, start=1):
        start_fmt = format_timestamp(seg['start'])
        end_fmt = format_timestamp(seg['end'])
        srt_content.append(f"{i}\n{start_fmt} --> {end_fmt}\n{seg['text'].strip()}\n")
    return "\n".join(srt_content)
