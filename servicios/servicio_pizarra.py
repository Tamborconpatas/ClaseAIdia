"""Fotos de la pizarra: el profesor las saca con el celular durante la clase y un modelo de visión las lee para sumar su
texto al material de estudio.

Reglas que vienen del resto del proyecto: la imagen es temporal (puede salir un alumno, y el proyecto solo guarda texto):
se borra apenas se lee, también si la lectura falla; la lectura corre después de la clase en el proceso aparte del
procesamiento (un modelo a la vez, con la memoria cuidada) y **nunca bloquea la clase**: si una foto no se puede leer
queda marcada con su motivo y el material se genera igual. Medido (QA.md, 2026-10-02): el texto y las listas salen bien;
las cifras de matemática escrita a mano, no, así que el texto se entrega al modelo como apoyo, no como verdad.
"""
import base64
import io
import os
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy.orm import Session, sessionmaker

from infraestructura import cliente_ollama
from nucleo.memoria import esperar_memoria
from infraestructura.modelos_orm import EstadoGrabacion as E
from infraestructura.modelos_orm import FotoPizarra, Grabacion
from servicios.servicio_grabacion import ErrorGrabacion

CARPETA_FOTOS = Path(os.environ.get("FOTOS_TEMP_DIR", "fotos_temp"))
MODELO_VISION = os.environ.get("MODELO_VISION", "qwen2.5vl:3b")
MAX_FOTOS = 30
MAX_BYTES = 15 * 1024 * 1024
# 1024 y no más: es con lo que se midió (QA.md). Con 1280 px el modelo entró en un bucle de repetición con una pizarra de cálculo
# densa y Ollama abortó la respuesta (probado de punta a punta); a 1024 la leyó.
LADO_MAXIMO = 1024
LADO_REINTENTO = 768  # si aun así falla, una segunda lectura con la foto más chica (otra cantidad de piezas de imagen)
MAX_CARACTERES_AL_MATERIAL = 4000
MEMORIA_MINIMA_GB = 4.5  # el modelo de visión usa 3,4 GB (medido) más lo que ya tiene el proceso
ESPERA_MEMORIA_S = 300
ESTADOS_QUE_ACEPTAN_FOTOS = (E.ESPERANDO, E.GRABANDO, E.PAUSADA, E.TERMINANDO)
Image.MAX_IMAGE_PIXELS = 60_000_000  # las fotos de celular llegan a ~50 MP; algo mayor (una bomba de descompresión) se rechaza

# En inglés a propósito: con el mismo pedido en español el modelo inventó filas de una tabla y rechazó una foto del cuaderno
# (medido; ver QA.md). «No inventes» es lo que más pesa.
_PROMPT = (
    "Read all the text in the image. Transcribe it exactly as written, line by line, keeping math notation. "
    "Do not invent or complete anything that is not visible. If there is a diagram, add one short line saying what it connects."
)
_ENCABEZADO_AL_MATERIAL = (
    "Texto leído automáticamente de fotos de la pizarra de esta clase. Puede tener errores, sobre todo en cifras y fórmulas "
    "escritas a mano: úsalo solo como apoyo a lo que explicó el profesor, menciona una cifra solo si coincide con la clase, "
    "y no inventes lo que no aparezca."
)


def _carpeta(grabacion_id: int) -> Path:
    return CARPETA_FOTOS / str(grabacion_id)


def _ruta(foto: FotoPizarra) -> Path:
    return _carpeta(foto.grabacion_id) / f"{foto.id}.jpg"


def borrar_fotos(grabacion_id: int) -> None:
    shutil.rmtree(_carpeta(grabacion_id), ignore_errors=True)


def _normalizar(datos: bytes) -> bytes:
    """Gira según la orientación del celular, reduce y vuelve a codificar: así también se pierden los metadatos (GPS...)."""
    try:
        with Image.open(io.BytesIO(datos)) as im:
            if im.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(im.format)
            im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        raise ErrorGrabacion("El archivo no es una foto válida (JPEG, PNG o WebP)", 415) from None
    im.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    salida = io.BytesIO()
    im.save(salida, "JPEG", quality=85)
    return salida.getvalue()


def guardar_foto(db: Session, g: Grabacion, datos: bytes, segundo: int = 0) -> FotoPizarra:
    if g.estado not in ESTADOS_QUE_ACEPTAN_FOTOS:
        raise ErrorGrabacion(f"No se pueden agregar fotos con la grabación {g.estado.value}")
    if not datos or len(datos) > MAX_BYTES:
        raise ErrorGrabacion("La foto está vacía o es demasiado grande", 413)
    if len(g.fotos) >= MAX_FOTOS:
        raise ErrorGrabacion(f"Máximo {MAX_FOTOS} fotos por clase", 409)
    jpeg = _normalizar(datos)
    foto = FotoPizarra(grabacion_id=g.id, segundo=max(0, min(int(segundo), 24 * 3600)))
    db.add(foto)
    db.flush()  # para tener el id: el nombre del archivo lo pone el servidor, nunca el cliente
    ruta = _ruta(foto)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(jpeg)
    db.commit()
    return foto


def limpiar_repeticiones(texto: str) -> str:
    """Un modelo de visión pequeño a veces repite el mismo bloque una y otra vez hasta llenar el tope de palabras (pasó con una
    tabla densa). Una línea larga que sale tres veces o más se deja solo la primera; el resto, y una última línea cortada, no."""
    lineas = texto.split("\n")
    veces = Counter(linea.strip() for linea in lineas if len(linea.strip()) >= 12)
    vistas: set[str] = set()
    salida = []
    for linea in lineas:
        clave = linea.strip()
        if veces[clave] >= 3 and len(clave) >= 12:
            if clave in vistas:
                continue
            vistas.add(clave)
        salida.append(linea)
    return "\n".join(salida).strip()


def _leer(ruta: Path, ollama_url: str, reducida: bool = False) -> str:
    """`reducida`: segunda oportunidad, con la foto más chica y una penalización mayor a repetir."""
    if reducida:
        with Image.open(ruta) as im:
            im.thumbnail((LADO_REINTENTO, LADO_REINTENTO))
            salida = io.BytesIO()
            im.convert("RGB").save(salida, "JPEG", quality=85)
        imagen = base64.b64encode(salida.getvalue()).decode()
    else:
        imagen = base64.b64encode(ruta.read_bytes()).decode()
    texto = cliente_ollama.generate(
        _PROMPT, MODELO_VISION, 700, ollama_url, ventana=4096, imagenes=[imagen],
        opciones={"temperature": 0.1, "repeat_penalty": 1.3 if reducida else 1.1},
    )
    return limpiar_repeticiones(texto.strip())


def _leer_con_reintento(ruta: Path, ollama_url: str) -> str:
    """Si Ollama aborta (la respuesta entró en un bucle: «token repeat limit»), el modelo cargado queda mal y las fotos
    siguientes también fallarían (medido): se descarga de la memoria para que se recargue limpio y se prueba una vez más con
    la foto más chica. Si el modelo ni siquiera está instalado, reintentar no sirve."""
    try:
        return _leer(ruta, ollama_url)
    except Exception as e:
        if "not found" in str(e).lower():
            raise
        cliente_ollama.descargar_modelo(MODELO_VISION, ollama_url)
        return _leer(ruta, ollama_url, reducida=True)


def leer_pendientes(grabacion_id: int, fabrica: sessionmaker, ollama_url: str | None = None) -> None:
    """Lee las fotos que faltan, una a una. Nunca lanza: una foto que falla queda en `error` con el motivo."""
    ollama_url = ollama_url or os.environ.get("OLLAMA_URL") or "http://localhost:11434"
    with fabrica() as db:
        ids = [f.id for f in db.query(FotoPizarra).filter_by(grabacion_id=grabacion_id, estado="pendiente").order_by(FotoPizarra.segundo, FotoPizarra.id)]
    if ids and not esperar_memoria(MEMORIA_MINIMA_GB, ESPERA_MEMORIA_S):
        with fabrica() as db:  # la clase es más importante que sus fotos: se sigue sin ellas
            for foto in db.query(FotoPizarra).filter(FotoPizarra.id.in_(ids)):
                foto.estado, foto.error = "error", "El equipo no tenía memoria suficiente para leer la foto"
            db.commit()
        ids = []
    for foto_id in ids:
        with fabrica() as db:
            foto = db.get(FotoPizarra, foto_id)
            ruta = _ruta(foto)
            try:
                if not ruta.is_file():
                    raise RuntimeError("la imagen ya no estaba en el servidor")
                foto.texto, foto.estado, foto.error = _leer_con_reintento(ruta, ollama_url), "leida", None
            except Exception as e:  # una foto no puede romper la clase
                foto.estado, foto.error = "error", _motivo(e)
                cliente_ollama.descargar_modelo(MODELO_VISION, ollama_url)  # que la foto que falló no deje mal a las que siguen
            finally:
                ruta.unlink(missing_ok=True)  # leída o no, la imagen no se queda
            db.commit()
    if ids:
        cliente_ollama.descargar_modelo(MODELO_VISION, ollama_url)  # el modelo de texto va a necesitar esa memoria
    shutil.rmtree(_carpeta(grabacion_id), ignore_errors=True)


def descartar_pendientes(db: Session, grabacion_id: int) -> None:
    """La clase no se va a procesar más: sus fotos sin leer se borran y quedan marcadas."""
    for foto in db.query(FotoPizarra).filter_by(grabacion_id=grabacion_id, estado="pendiente"):
        foto.estado, foto.error = "error", "La clase no se pudo procesar"
    db.commit()
    borrar_fotos(grabacion_id)


def _motivo(e: Exception) -> str:
    texto = str(e)
    if "not found" in texto.lower() or "pull" in texto.lower():
        return f"Falta el modelo de lectura de imágenes: ejecuta «ollama pull {MODELO_VISION}»"
    return f"No se pudo leer la foto: {texto[:200]}"


def texto_para_el_material(db: Session, grabacion_id: int) -> str:
    """Lo leído de todas las fotos, en orden, para sumarlo al material; vacío si no hay."""
    partes = []
    for f in db.query(FotoPizarra).filter_by(grabacion_id=grabacion_id, estado="leida").order_by(FotoPizarra.segundo, FotoPizarra.id):
        if (f.texto or "").strip():
            partes.append(f"[Foto a los {f.segundo // 60} min]\n{f.texto.strip()}")
    if not partes:
        return ""
    return f"{_ENCABEZADO_AL_MATERIAL}\n\n" + "\n\n".join(partes)[:MAX_CARACTERES_AL_MATERIAL]


def limpiar_huerfanas(db: Session) -> None:
    """Al arrancar: borra las imágenes que ya no hacen falta (cualquiera que no esté pendiente o cuya sesión ya no exista)."""
    if not CARPETA_FOTOS.exists():
        return
    pendientes = {f.id for f in db.query(FotoPizarra).filter_by(estado="pendiente")}
    for carpeta in CARPETA_FOTOS.iterdir():
        if not carpeta.is_dir():
            continue
        for archivo in carpeta.glob("*.jpg"):
            if not archivo.stem.isdigit() or int(archivo.stem) not in pendientes:
                archivo.unlink(missing_ok=True)
        if not any(carpeta.iterdir()):
            carpeta.rmdir()
