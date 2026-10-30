# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import json
import os
import re

from nucleo import configuracion as app_config
from nucleo import limpieza_texto
from nucleo.memoria import memoria_libre_gb
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
    # El modelo depende de dónde corre Ollama, no de si hay GPU: con OLLAMA_DISPOSITIVO=cpu se usa el liviano.
    if ollama_client.ollama_solo_cpu():
        return _OLLAMA_MODEL_CPU
    return _OLLAMA_MODEL_GPU if hardware.detect_gpu_vendor() != "none" else _OLLAMA_MODEL_CPU


# Memoria que usa Ollama con cada modelo (medido en CPU, con la ventana de contexto grande de una clase larga):
# el de 1B llega a ~1,6 GB y el de 3B a ~4,8 GB. Un modelo que no se conoce se supone grande.
_MEMORIA_DEL_MODELO_GB = {_OLLAMA_MODEL_CPU: 2.0, _OLLAMA_MODEL_GPU: 5.0}
_MEMORIA_DE_UN_MODELO_DESCONOCIDO_GB = 6.0


def _modelo_que_cabe(modelo: str, es_auto: bool) -> str:
    """En un equipo modesto cargar un modelo que no cabe en la memoria libre ahoga a todo el sistema. Si el modelo lo
    eligió la aplicación (`auto`) y no cabe, se usa el liviano; si lo eligió la persona se respeta."""
    libre = memoria_libre_gb()
    necesita = _MEMORIA_DEL_MODELO_GB.get(modelo, _MEMORIA_DE_UN_MODELO_DESCONOCIDO_GB)
    if es_auto and libre is not None and libre < necesita and modelo != _OLLAMA_MODEL_CPU:
        print(f"[study_material] AVISO: {modelo} necesita ~{necesita:.0f} GB y hay {libre:.1f} GB libres: se usa {_OLLAMA_MODEL_CPU}.")
        return _OLLAMA_MODEL_CPU
    return modelo

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
    r'(?<!\w)P\s*\d*\s*:\s*(.+?)\s*(?<!\w)R\s*\d*\s*:\s*(.+?)(?=\s(?:\d+[.)]\s*)?(?<!\w)P\s*\d*\s*:|\Z)',
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


def _contexto(asignatura: str | None) -> str:
    """Lo que el modelo debe saber del texto: de qué materia es, que viene de un reconocimiento de voz que se
    equivoca (sobre todo con nombres y términos en inglés) y que la conversación ajena a la materia sobra. Sin
    esto, el saludo y el desorden del inicio de una clase real entraban al resumen como si fueran contenido."""
    materia = f" de la materia «{asignatura}»" if asignatura else ""
    return (
        f"El texto es parte de una clase{materia}, transcrita automáticamente: puede tener errores en nombres, siglas "
        "y términos técnicos (sobre todo en inglés); corrígelos cuando el contexto lo permita. Ignora los saludos, la "
        "asistencia, las bromas y cualquier conversación que no sea parte del contenido de la materia."
    )


def _con_pizarra(contenido: str, pizarra: str) -> str:
    """Lo leído de las fotos de la pizarra va aparte del contenido hablado, con su advertencia (puede tener cifras mal leídas)."""
    return f"{contenido}\n\n{pizarra}" if pizarra and pizarra.strip() else contenido


def _condense_transcript(chunks: list, model_name: str, ollama_url: str, asignatura: str | None = None) -> str:
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
            f"{_contexto(asignatura)}\n\n"
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


def _condense_until_fits(chunks: list, model_name: str, ollama_url: str, chunk_chars: int, asignatura: str | None = None) -> str:
    """Condensa los bloques y, si el resultado sigue siendo demasiado largo para la pasada final (una clase de
    más de una hora), lo vuelve a condensar por bloques, hasta que quepa. Así la pasada final nunca recibe más
    de lo que entra en la ventana de contexto, que es lo que antes la dejaba sin sus instrucciones."""
    nivel = 1
    while True:
        condensado = _condense_transcript(chunks, model_name, ollama_url, asignatura)
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


# Las cuatro partes del material de una clase larga, cada una con su propia petición: pedirlas todas juntas a un
# modelo de 3B con un tope de 2.048 tokens dejaba un resumen de pocos cientos de caracteres. (nombre, tokens, instrucción)
_SECCIONES = [
    (
        "resumen", 1500,
        "Escribe un resumen claro y completo de la clase, en prosa, de 4 a 7 párrafos, en el orden en que se vio, "
        "que le permita a alguien que no asistió entender todo el contenido explicado por el profesor.",
    ),
    (
        "puntos_clave", 700,
        "Escribe una lista con viñetas ('- ') de entre 8 y 15 conceptos, definiciones, fórmulas o datos que el alumno "
        "debería memorizar antes de una evaluación (recuperación activa: formula cada punto de forma que el alumno "
        "tenga que recordar el detalle, no solo reconocerlo).",
    ),
    (
        "hoja_repaso", 1100,
        "Escribe una hoja de repaso con los conceptos clave; para cada uno explica también POR QUÉ importa o CÓMO se "
        "conecta con otro concepto visto en la misma clase (elaboración: no listes definiciones sueltas, teje "
        "relaciones entre ideas).",
    ),
    (
        "tarjetas", 900,
        "Escribe entre 8 y 12 tarjetas de estudio en formato estricto: una línea 'P: <pregunta>' y la siguiente "
        "'R: <respuesta>', una tarjeta tras otra, sin numerarlas ni agregar texto extra. Mezcla preguntas de distintos "
        "sub-temas en vez de agruparlas por tema (interleaving) y redáctalas pensando en que el alumno las repasará "
        "varias veces en distintos días (repetición espaciada).",
    ),
]


def _sin_cola_incompleta(texto: str) -> str:
    """Si el modelo se quedó sin tokens a mitad de una oración, quita esa oración a medias (el alumno leía el
    resumen terminando en «Se discutió que el desarrollo»). Si cortar dejaría menos de la mitad, no toca nada."""
    t = texto.rstrip()
    if not t or t[-1] in '.!?»")*:;':
        return t
    corte = max(t.rfind(". "), t.rfind(".\n"), t.rfind("? "), t.rfind("! "), t.rfind("\n"))
    return t[: corte + 1].rstrip() if corte >= len(t) * 0.5 else t


def _texto_de_seccion(raw: str, nombre: str) -> str:
    """La respuesta a una sola sección; si el modelo repite el encabezado al inicio, se lo quita."""
    patron = dict(_SECTION_PATTERNS)[nombre]
    primera, _, resto = raw.strip().partition("\n")
    if resto and patron.fullmatch(primera.strip()):  # solo si el encabezado está solo en su línea, no si abre una oración
        raw = resto
    return raw.strip() if nombre == "tarjetas" else _sin_cola_incompleta(raw.strip())


def _generar_por_secciones(material: str, asignatura: str | None, model_name: str, ollama_url: str, max_tokens: int):
    """Las cuatro partes del material, cada una en su propia llamada. El contenido va primero y la instrucción al
    final (con el mismo contenido al principio, Ollama reutiliza lo ya leído entre una llamada y la siguiente), y
    todas piden la misma ventana de contexto: cambiarla entre llamadas hace que Ollama recargue el modelo."""
    base = f"{_contexto(asignatura)}\n\nContenido de la clase (resumen por partes):\n{material}\n\n---\n"
    ventana = ollama_client.ventana_necesaria(base + "x" * 600, max(tokens for _, tokens, _ in _SECCIONES))
    textos = {}
    for nombre, tokens, instruccion in _SECCIONES:
        texto = ""
        for intento in (1, 2):  # un modelo chico a veces no sigue el formato: se pide una vez más antes de dar la sección por perdida
            print(f"[study_material] Generando {nombre}..." + (" (otro intento)" if intento == 2 else ""))
            raw = ollama_client.generate(
                base + f"{instruccion} Responde solo con eso, sin encabezados." + (" Sigue el formato pedido al pie de la letra." if intento == 2 else ""),
                model=model_name, max_tokens=min(tokens, max_tokens), ollama_url=ollama_url, ventana=ventana,
            )
            texto = _texto_de_seccion(raw, nombre)
            if texto and (nombre != "tarjetas" or _parse_flashcards(texto)):
                break
        textos[nombre] = texto
    return textos["resumen"], textos["puntos_clave"], textos["hoja_repaso"], _parse_flashcards(textos["tarjetas"])


def generate_study_material(text: str, asignatura: str | None = None, pizarra: str = ""):
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

    configurado = app_config.get_param("ollama_model")
    model_name = _modelo_que_cabe(_resolve_ollama_model(configurado), es_auto=configurado == "auto")
    max_tokens = int(app_config.get_param("ollama_max_tokens"))
    ollama_url = os.environ.get("OLLAMA_URL") or app_config.get_param("ollama_url")
    chunk_chars = int(app_config.get_param("ollama_chunk_chars"))

    chunks = _split_into_chunks(text, max_chars=chunk_chars)

    try:
        if len(chunks) > 1:
            print(f"[study_material] Transcripción larga: procesando en {len(chunks)} bloques...")
            source_text = _condense_until_fits(chunks, model_name, ollama_url, chunk_chars, asignatura)
            return _generar_por_secciones(_con_pizarra(source_text, pizarra), asignatura, model_name, ollama_url, max_tokens)
        source_text = _con_pizarra(text, pizarra)
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
        f"{_contexto(asignatura)}\n\n"
        f"Contenido de la clase:\n{source_text}"
    )

    try:
        raw = ollama_client.generate(prompt, model=model_name, max_tokens=max_tokens, ollama_url=ollama_url)
    except RuntimeError as e:
        return str(e), "", "", []

    sections = _split_study_material(raw)
    flashcards = _parse_flashcards(sections["tarjetas"])
    return sections["resumen"], sections["puntos_clave"], sections["hoja_repaso"], flashcards


# --- Mapa conceptual ------------------------------------------------------------------------------------------------
# Medido (QA.md, 2026-10-02): pedirle a un modelo pequeño que escriba código Mermaid sale mal (con el de 1B, basura; con el
# de 3B, sintaxis rota casi siempre). Pedirle los datos como JSON con esquema, y armar el diagrama en código, sale siempre
# válido; pero con el de 1B las relaciones no sirven (repite «origen -más-> materia»), así que solo se genera con uno mayor.

_MAX_RELACIONES = 14
_MIN_RELACIONES = 3
_ESQUEMA_MAPA = {
    "type": "object",
    "properties": {
        "relaciones": {
            "type": "array",
            "minItems": 5,
            "maxItems": _MAX_RELACIONES,
            "items": {
                "type": "object",
                "properties": {
                    "de": {"type": "string", "maxLength": 60},
                    "relacion": {"type": "string", "maxLength": 40},
                    "a": {"type": "string", "maxLength": 60},
                },
                "required": ["de", "relacion", "a"],
            },
        }
    },
    "required": ["relaciones"],
}


def _limpiar_relaciones(crudas) -> list[dict]:
    """Normaliza lo que devolvió el modelo: sin vacíos, sin flechas de un concepto a sí mismo, sin repetidas, y un mismo
    concepto con la misma escritura (la primera que apareció), que es lo que une las flechas en un solo nodo."""
    escritura: dict[str, str] = {}
    vistas: set[tuple[str, str]] = set()
    relaciones = []
    for r in crudas if isinstance(crudas, list) else []:
        if not isinstance(r, dict):
            continue
        de, rel, a = (" ".join(str(r.get(k) or "").split()) for k in ("de", "relacion", "a"))
        if not de or not a or de.casefold() == a.casefold():
            continue
        de, a = escritura.setdefault(de.casefold(), de), escritura.setdefault(a.casefold(), a)
        if (de.casefold(), a.casefold()) in vistas:
            continue
        vistas.add((de.casefold(), a.casefold()))
        relaciones.append({"de": de, "relacion": rel, "a": a})
    return relaciones[:_MAX_RELACIONES]


def generar_mapa_conceptual(resumen: str, puntos_clave: str, asignatura: str | None = None) -> list[dict]:
    """Relaciones entre los conceptos de la clase, a partir del material ya generado (más corto que la transcripción).
    Devuelve [] si el modelo es muy pequeño, si falla o si no salen relaciones suficientes: el mapa es un extra."""
    configurado = app_config.get_param("ollama_model")
    modelo = _modelo_que_cabe(_resolve_ollama_model(configurado), es_auto=configurado == "auto")
    if modelo == _OLLAMA_MODEL_CPU:
        return []
    texto = f"{resumen or ''}\n\n{puntos_clave or ''}".strip()[:6000]
    if not texto:
        return []
    materia = f" de la materia «{asignatura}»" if asignatura else ""
    prompt = (
        f"Del resumen de una clase{materia} que aparece abajo, extrae las relaciones entre los conceptos principales para armar un "
        "mapa conceptual. Cada relación es: concepto de origen (1 a 4 palabras), verbo o frase corta que los une, y concepto de "
        "destino (1 a 4 palabras). Usa exactamente el mismo nombre cada vez que aparezca el mismo concepto. Solo ideas que estén "
        f"en el texto; no inventes.\n\nResumen de la clase:\n{texto}"
    )
    ollama_url = os.environ.get("OLLAMA_URL") or app_config.get_param("ollama_url")
    try:
        bruto = ollama_client.generate(prompt, model=modelo, max_tokens=900, ollama_url=ollama_url, formato=_ESQUEMA_MAPA)
        relaciones = _limpiar_relaciones(json.loads(bruto).get("relaciones"))
    except (RuntimeError, ValueError, AttributeError):
        return []
    return relaciones if len(relaciones) >= _MIN_RELACIONES else []
