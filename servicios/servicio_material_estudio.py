import os
import re

from nucleo import configuracion as app_config
from nucleo import limpieza_texto
from infraestructura import cliente_ollama as ollama_client
from infraestructura import hardware

# Modelos livianos de la familia llama3.2 — mucho más chicos que llama3 (8B),
# que en CPU se demora tanto generando que puede superar el timeout del
# cliente. Se eligen automáticamente cuando "ollama_model" está en "auto".
_OLLAMA_MODEL_CPU = "llama3.2:1b"
_OLLAMA_MODEL_GPU = "llama3.2:3b"


def _resolve_ollama_model(configured: str) -> str:
    if configured != "auto":
        return configured
    return _OLLAMA_MODEL_GPU if hardware.detect_gpu_vendor() != "none" else _OLLAMA_MODEL_CPU

# Regex tolerante en vez de string exacto: modelos locales pequeños no
# siempre reproducen los marcadores al pie de la letra.
_SUMMARY_MARKER = "##RESUMEN##"
_KEYPOINTS_MARKER = "##PUNTOS_CLAVE##"
_REVIEW_SHEET_MARKER = "##HOJA_DE_REPASO##"
_FLASHCARDS_MARKER = "##TARJETAS_ESTUDIO##"

_SECTION_PATTERNS = [
    ("resumen", re.compile(r'[#*]{0,3}\s*RESUMEN\s*[#*]{0,3}\s*:?\s*[#*]{0,3}\s*\n?', re.IGNORECASE)),
    ("puntos_clave", re.compile(r'[#*]{0,3}\s*PUNTOS[\s_]+CLAVE\s*[#*]{0,3}\s*:?\s*[#*]{0,3}\s*\n?', re.IGNORECASE)),
    ("hoja_repaso", re.compile(r'[#*]{0,3}\s*HOJA[\s_]+DE[\s_]+REPASO\s*[#*]{0,3}\s*:?\s*[#*]{0,3}\s*\n?', re.IGNORECASE)),
    ("tarjetas", re.compile(r'[#*]{0,3}\s*TARJETAS[\s_]+(DE[\s_]+)?ESTUDIO\s*[#*]{0,3}\s*:?\s*[#*]{0,3}\s*\n?', re.IGNORECASE)),
]

# Tolera numeración que modelos chicos agregan pese a la instrucción de no
# numerar (ej. "P1:", "P2:" en vez de "P:").
_FLASHCARD_LINE_RE = re.compile(
    r'P\s*\d*\s*:\s*(.+?)\s*\n\s*R\s*\d*\s*:\s*(.+?)(?=\n\s*(?:\d+[.)]\s*)?P\s*\d*\s*:|\Z)',
    re.IGNORECASE | re.DOTALL,
)

# Tokens de salida solo para el resumen intermedio de cada bloque, no para
# la pasada final (esa usa "ollama_max_tokens").
_CHUNK_SUMMARY_MAX_TOKENS = 512


def _split_into_chunks(text: str, max_chars: int) -> list:
    """Parte una transcripción larga en bloques de a lo sumo `max_chars`,
    cortando en el límite de una oración cuando es posible para no partir
    una idea a la mitad. Si el texto ya cabe en un solo bloque, lo devuelve
    tal cual (sin bloques de más)."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            boundary = max(
                text.rfind('. ', start, end),
                text.rfind('? ', start, end),
                text.rfind('! ', start, end),
            )
            if boundary > start:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end

    return chunks


def _condense_transcript(chunks: list, model_name: str, ollama_url: str) -> str:
    """Reduce cada bloque a un resumen fiel y extenso, uno a la vez
    (secuencial, nunca en paralelo) antes de la pasada final — evita
    mandarle la transcripción completa de una clase larga a Ollama de una
    sola vez, lo que en hardware modesto puede exceder la ventana de
    contexto del modelo o saturar la memoria del sistema."""
    total = len(chunks)
    partial_summaries = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"[study_material] Condensando bloque {i}/{total}...")
        prompt = (
            f"Este es el bloque {i} de {total} de la transcripción de una clase (se procesa "
            "por separado del resto para no saturar la memoria del sistema). Resume de forma "
            "extensa y fiel los conceptos, definiciones, ejemplos y datos importantes "
            "mencionados en este bloque, sin agregar información que no esté en el texto ni "
            "repetir instrucciones o encabezados — responde solo con el resumen.\n\n"
            f"Bloque:\n{chunk}"
        )
        summary = ollama_client.generate(
            prompt, model=model_name, max_tokens=_CHUNK_SUMMARY_MAX_TOKENS, ollama_url=ollama_url
        )
        partial_summaries.append(f"[Parte {i}/{total}]\n{summary.strip()}")

    return "\n\n".join(partial_summaries)


# Lo más largo que puede ser el texto condensado que entra a la pasada final (unos 8.000 tokens): con las
# instrucciones y la respuesta caben en la ventana de contexto que se le pide a Ollama (ver cliente_ollama).
_MAX_CARACTERES_FINAL = 24_000
_MAX_NIVELES = 3  # una clase de varias horas necesita 2; con 3 caben cientos de miles de caracteres


def _condense_until_fits(chunks: list, model_name: str, ollama_url: str, chunk_chars: int) -> str:
    """Condensa los bloques y, si el resultado sigue siendo demasiado largo para la pasada final (una clase de
    más de una hora), lo vuelve a condensar por bloques, hasta que quepa. Así la pasada final nunca recibe más
    de lo que entra en la ventana de contexto, que es lo que antes la dejaba sin sus instrucciones."""
    nivel = 1
    while True:
        condensado = _condense_transcript(chunks, model_name, ollama_url)
        if len(condensado) <= _MAX_CARACTERES_FINAL or nivel == _MAX_NIVELES:
            return condensado
        nivel += 1
        print(f"[study_material] El resumen por partes mide {len(condensado)} caracteres: se condensa de nuevo (nivel {nivel}).")
        chunks = _split_into_chunks(condensado, max_chars=chunk_chars)


def _split_study_material(raw: str) -> dict:
    """Parsea la respuesta del LLM en sus 4 secciones buscando los
    encabezados de forma tolerante (el orden en el texto puede variar
    levemente entre modelos, así que se ordenan por dónde aparecen). Si el
    modelo no incluyó ningún encabezado reconocible, cae a devolver todo el
    texto como resumen — igual que el comportamiento anterior."""
    matches = []
    for name, pattern in _SECTION_PATTERNS:
        m = pattern.search(raw)
        if m:
            matches.append((m.start(), m.end(), name))

    if not matches:
        return {"resumen": raw.strip(), "puntos_clave": "", "hoja_repaso": "", "tarjetas": ""}

    matches.sort(key=lambda x: x[0])

    result = {"resumen": "", "puntos_clave": "", "hoja_repaso": "", "tarjetas": ""}
    for i, (start, end, name) in enumerate(matches):
        section_end = matches[i + 1][0] if i + 1 < len(matches) else len(raw)
        result[name] = raw[end:section_end].strip()

    return result


def _parse_flashcards(raw_tarjetas: str) -> list:
    """Convierte el bloque de texto de tarjetas (líneas 'P: ...' / 'R: ...')
    en una lista de dicts {'pregunta', 'respuesta'} — datos estructurados,
    listos para que una futura función de repetición espaciada los use en
    vez de solo texto plano."""
    if not raw_tarjetas:
        return []
    cards = []
    for m in _FLASHCARD_LINE_RE.finditer(raw_tarjetas):
        pregunta, respuesta = m.group(1).strip(), m.group(2).strip()
        if pregunta and respuesta:
            cards.append({"pregunta": pregunta, "respuesta": respuesta})
    return cards


def generate_study_material(text: str):
    """Genera resumen, puntos clave, hoja de repaso y tarjetas de estudio,
    incorporando recuperación activa/elaboración/interleaving en el diseño
    del prompt (la repetición espaciada real necesita que la app resurfacee
    las tarjetas en el tiempo, algo que aún no existe en el modelo de
    datos). Si la transcripción es larga, la condensa en bloques primero
    (ver `_condense_transcript`).

    Devuelve (resumen, puntos_clave, hoja_repaso, tarjetas), donde tarjetas
    es una lista de dicts {'pregunta', 'respuesta'}."""
    if not text or len(text.strip()) == 0:
        return "No hay transcripción para generar material de estudio.", "", "", []

    text = limpieza_texto.limpiar_transcripcion(text)

    model_name = _resolve_ollama_model(app_config.get_param("ollama_model"))
    max_tokens = int(app_config.get_param("ollama_max_tokens"))
    ollama_url = os.environ.get("OLLAMA_URL") or app_config.get_param("ollama_url")
    chunk_chars = int(app_config.get_param("ollama_chunk_chars"))

    chunks = _split_into_chunks(text, max_chars=chunk_chars)

    try:
        if len(chunks) > 1:
            print(f"[study_material] Transcripción larga: procesando en {len(chunks)} bloques...")
            source_text = _condense_until_fits(chunks, model_name, ollama_url, chunk_chars)
        else:
            source_text = text
    except RuntimeError as e:
        return str(e), "", "", []

    prompt = (
        "Eres un asistente académico que ayuda a estudiantes que faltaron a clase o les cuesta "
        "concentrarse. A partir del contenido de una clase (puede venir como transcripción "
        "completa, o ya condensado en partes si la clase era muy larga), genera EXACTAMENTE "
        "cuatro secciones, en este orden, con estos encabezados literales y nada más antes del "
        "primer encabezado:\n\n"
        f"{_SUMMARY_MARKER}\n"
        "Un resumen claro y completo de la clase, en prosa, que le permita a alguien que no "
        "asistió entender todo el contenido explicado por el profesor.\n\n"
        f"{_KEYPOINTS_MARKER}\n"
        "Una lista con viñetas ('- ') de los conceptos, definiciones, fórmulas o datos más "
        "importantes que el alumno debería memorizar antes de una evaluación (recuperación "
        "activa: formula cada punto de forma que el alumno tenga que recordar el detalle, no "
        "solo reconocerlo).\n\n"
        f"{_REVIEW_SHEET_MARKER}\n"
        "Una hoja de repaso con los conceptos clave, pero para cada uno explica también POR QUÉ "
        "importa o CÓMO se conecta con otro concepto visto en la misma clase (elaboración: no "
        "listes definiciones sueltas, tejan relaciones entre ideas).\n\n"
        f"{_FLASHCARDS_MARKER}\n"
        "Entre 6 y 10 tarjetas de estudio en formato estricto 'P: <pregunta>' seguido de "
        "'R: <respuesta>' en la línea siguiente, una tarjeta tras otra sin numerarlas ni agregar "
        "texto extra. Mezcla preguntas de distintos sub-temas de la clase en vez de agruparlas "
        "por tema (interleaving), y redáctalas pensando en que el alumno las repasará varias "
        "veces en distintos días, no solo una vez (repetición espaciada).\n\n"
        f"No excedas los {max_tokens} tokens en total.\n\n"
        f"Contenido de la clase:\n{source_text}"
    )

    try:
        raw = ollama_client.generate(prompt, model=model_name, max_tokens=max_tokens, ollama_url=ollama_url)
    except RuntimeError as e:
        return str(e), "", "", []

    sections = _split_study_material(raw)
    flashcards = _parse_flashcards(sections["tarjetas"])
    return sections["resumen"], sections["puntos_clave"], sections["hoja_repaso"], flashcards
