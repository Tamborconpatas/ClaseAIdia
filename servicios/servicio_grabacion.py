"""Control de clase en vivo: una sesión de grabación por clase.

El servidor guarda el estado de la sesión y es quien manda. Quien controla (el celular del profesor, o el
mismo equipo que graba) cambia ese estado con comandos; el equipo grabador (un PC de la sala o el celular)
lo consulta con su latido y obedece, y va subiendo el audio en trozos. Al terminar, el audio se une, se
transcribe, se genera el material y se **borra siempre** (aunque falle algo): el audio nunca sobrevive al
procesamiento.
"""
import datetime
import os
import shutil
import threading
import traceback
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from infraestructura.modelos_orm import (
    Bloque,
    Clase,
    ContenidoClase,
    EstadoGrabacion as E,
    Grabacion,
    TipoBloque,
    Usuario,
)

CARPETA_AUDIO = Path(os.environ.get("AUDIO_TEMP_DIR", "audio_temp"))
MODELO_WHISPER = os.environ.get("MODELO_WHISPER", "small")
# Minutos después del término del bloque en que la grabación se corta sola (por si el profesor olvida terminarla).
GRACIA_CORTE_MIN = int(os.environ.get("MINUTOS_CORTE_GRABACION", "15"))
LATIDO_VIGENTE_S = 15  # un equipo sin latido por más de esto se considera desconectado
ESPERA_FINALIZAR_S = 45  # tras pedir terminar, lo que se espera al equipo grabador antes de procesar lo que llegó
MAX_SIN_GRABADOR_S = 600  # grabando sin ningún equipo conectado por tanto tiempo: se termina con lo recibido
MAX_TROZO_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_TROZOS = 20_000

EXTENSION = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav"}
ACTIVAS = (E.ESPERANDO, E.GRABANDO, E.PAUSADA, E.TERMINANDO)


class ErrorGrabacion(Exception):
    def __init__(self, detalle: str, estado: int = 409):
        super().__init__(detalle)
        self.detalle, self.estado = detalle, estado


class ErrorProceso(Exception):
    """Falla esperable al procesar (sin voz, Ollama apagado...): se muestra al profesor tal cual."""


def ahora_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def ahora_local() -> datetime.datetime:
    """La hora del horario del colegio: la del reloj del servidor (que está en el colegio)."""
    return datetime.datetime.now()


def grabador_conectado(g: Grabacion, ahora: datetime.datetime | None = None) -> bool:
    ahora = ahora or ahora_utc()
    return g.latido_en is not None and (ahora - g.latido_en).total_seconds() <= LATIDO_VIGENTE_S


def _carpeta(grabacion_id: int) -> Path:
    return CARPETA_AUDIO / str(grabacion_id)


def borrar_audio(grabacion_id: int) -> None:
    shutil.rmtree(_carpeta(grabacion_id), ignore_errors=True)


# --- Crear y controlar la sesión ------------------------------------------------------------------


def _corte_de(bloque: Bloque, hoy: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(hoy, bloque.hora_fin) + datetime.timedelta(minutes=GRACIA_CORTE_MIN)


def estado_de_hoy(bloque: Bloque, ahora: datetime.datetime) -> tuple[bool, str | None]:
    """(se puede grabar ahora, motivo si no). El horario no se restringe por hora de inicio: solo que sea hoy
    y que no haya pasado el corte."""
    if bloque.tipo != TipoBloque.CLASE:
        return False, "Solo se graba un bloque de clase"
    if bloque.dia_semana != ahora.weekday():
        return False, "Este bloque no es de hoy"
    if ahora > _corte_de(bloque, ahora.date()):
        return False, f"El bloque terminó hace más de {GRACIA_CORTE_MIN} minutos"
    return True, None


def crear_o_reanudar(db: Session, profesor: Usuario, bloque_id: int) -> Grabacion:
    bloque = db.get(Bloque, bloque_id)
    # 404 también si el bloque es de otro profesor: no revela que existe.
    if bloque is None or bloque.profesor_id != profesor.id:
        raise ErrorGrabacion("Bloque no encontrado", 404)
    ahora = ahora_local()
    clase = db.query(Clase).filter_by(bloque_id=bloque.id, fecha=ahora.date()).first()
    if clase is not None and clase.contenido is not None:
        raise ErrorGrabacion("Esta clase ya tiene su material")
    if clase is not None and clase.grabacion is not None:
        g = clase.grabacion
        if g.estado == E.ERROR:  # reintento: la sesión vuelve a empezar de cero
            borrar_audio(g.id)
            g.estado, g.error, g.silenciada = E.ESPERANDO, None, False
            g.trozos = g.bytes_recibidos = g.segundos_grabados = 0
            g.mime = g.grabador_id = g.latido_en = g.terminando_desde = None
            g.corte_en = _corte_de(bloque, ahora.date())
            db.commit()
        elif g.estado in (E.PROCESANDO, E.TERMINADA):
            raise ErrorGrabacion("Esa grabación ya terminó")
        return g
    puede, motivo = estado_de_hoy(bloque, ahora)
    if not puede:
        raise ErrorGrabacion(motivo)
    if clase is None:
        clase = Clase(bloque_id=bloque.id, fecha=ahora.date())
        db.add(clase)
    g = Grabacion(clase=clase, estado=E.ESPERANDO, corte_en=_corte_de(bloque, ahora.date()))
    db.add(g)
    db.commit()
    return g


def _ilegal(accion: str, g: Grabacion):
    return ErrorGrabacion(f"No se puede «{accion}» con la grabación {g.estado.value}")


def aplicar_comando(db: Session, g: Grabacion, accion: str) -> Grabacion | None:
    """None cuando la sesión se canceló (ya no existe)."""
    ahora = ahora_utc()
    if accion == "iniciar":
        if g.estado != E.ESPERANDO:
            raise _ilegal(accion, g)
        if not grabador_conectado(g, ahora):
            raise ErrorGrabacion("Todavía no hay un equipo grabando: abre «Grabar» en el PC de la sala o en este celular")
        g.estado = E.GRABANDO
    elif accion == "pausar":
        if g.estado != E.GRABANDO:
            raise _ilegal(accion, g)
        g.estado = E.PAUSADA
    elif accion == "reanudar":
        if g.estado != E.PAUSADA:
            raise _ilegal(accion, g)
        g.estado = E.GRABANDO
    elif accion in ("silenciar", "activar_audio"):
        if g.estado not in (E.ESPERANDO, E.GRABANDO, E.PAUSADA):
            raise _ilegal(accion, g)
        g.silenciada = accion == "silenciar"
    elif accion == "terminar":
        if g.estado not in (E.GRABANDO, E.PAUSADA):
            raise _ilegal(accion, g)
        g.estado, g.terminando_desde = E.TERMINANDO, ahora
    elif accion == "cancelar":
        if g.estado != E.ESPERANDO:
            raise _ilegal(accion, g)
        _eliminar(db, g)
        return None
    elif accion in ("marcar_prioritaria", "quitar_prioritaria"):
        if g.estado == E.TERMINADA:
            raise _ilegal(accion, g)
        g.clase.prioritaria = accion == "marcar_prioritaria"
    else:  # el esquema ya limita las acciones; defensa por si se llama desde otro lado
        raise ErrorGrabacion("Acción desconocida", 422)
    db.commit()
    return g


def _eliminar(db: Session, g: Grabacion) -> None:
    clase = g.clase
    borrar_audio(g.id)
    db.delete(g)
    if clase.contenido is None:
        db.delete(clase)
    db.commit()


# --- El equipo grabador ----------------------------------------------------------------------------


def _del_grabador(g: Grabacion, dispositivo: str) -> None:
    if g.grabador_id != dispositivo:
        raise ErrorGrabacion("Otro equipo tomó el control de la grabación")


def registrar_grabador(db: Session, g: Grabacion, dispositivo: str, forzar: bool) -> Grabacion:
    if g.estado not in (E.ESPERANDO, E.GRABANDO, E.PAUSADA):
        raise _ilegal("grabar", g)
    ahora = ahora_utc()
    if g.grabador_id and g.grabador_id != dispositivo and grabador_conectado(g, ahora) and not forzar:
        raise ErrorGrabacion("Otro equipo ya está grabando esta clase")
    g.grabador_id, g.latido_en = dispositivo, ahora
    db.commit()
    return g


def latido(db: Session, g: Grabacion, dispositivo: str, segundos: int, nivel: float) -> Grabacion:
    _del_grabador(g, dispositivo)
    g.latido_en, g.nivel = ahora_utc(), max(0.0, min(1.0, nivel))
    if g.estado in (E.GRABANDO, E.PAUSADA, E.TERMINANDO):
        g.segundos_grabados = max(g.segundos_grabados, segundos)  # nunca retrocede si llega un latido viejo
    db.commit()
    return g


def _con_firma(inicio: bytes, mime: str) -> bool:
    """Revisa que el primer trozo sea de verdad audio del tipo declarado (no un archivo cualquiera)."""
    if mime == "audio/webm":
        return inicio[:4] == b"\x1a\x45\xdf\xa3"
    if mime == "audio/ogg":
        return inicio[:4] == b"OggS"
    if mime == "audio/mp4":
        return inicio[4:8] == b"ftyp"
    if mime == "audio/mpeg":
        return inicio[:3] == b"ID3" or inicio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    return inicio[:4] == b"RIFF"  # wav


def guardar_trozo(db: Session, g: Grabacion, dispositivo: str, n: int, datos: bytes, content_type: str) -> Grabacion:
    """El nombre del archivo lo pone el servidor (el número de trozo): nunca algo que mande el cliente."""
    _del_grabador(g, dispositivo)
    if g.estado not in (E.GRABANDO, E.PAUSADA, E.TERMINANDO):
        raise _ilegal("subir audio", g)
    mime = content_type.split(";")[0].strip().lower()
    if mime not in EXTENSION:
        raise ErrorGrabacion("Tipo de audio no permitido", 415)
    if g.mime and g.mime != mime:
        raise ErrorGrabacion("El audio cambió de formato en mitad de la grabación", 415)
    if not (0 <= n < MAX_TROZOS):
        raise ErrorGrabacion("Número de trozo inválido", 422)
    if not datos or len(datos) > MAX_TROZO_BYTES:
        raise ErrorGrabacion("Trozo de audio vacío o demasiado grande", 413)
    if n == 0 and not _con_firma(datos[:16], mime):
        raise ErrorGrabacion("El archivo no es audio del tipo indicado", 415)

    carpeta = _carpeta(g.id)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{n:06d}.parte"
    previo = destino.stat().st_size if destino.exists() else 0
    if g.bytes_recibidos - previo + len(datos) > MAX_TOTAL_BYTES:
        raise ErrorGrabacion("La grabación superó el tamaño máximo", 413)
    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(datos)
    os.replace(tmp, destino)  # un reintento del mismo trozo lo reemplaza, no lo duplica
    g.mime = mime
    g.trozos = sum(1 for _ in carpeta.glob("*.parte"))
    g.bytes_recibidos = sum(f.stat().st_size for f in carpeta.glob("*.parte"))
    db.commit()
    return g


def finalizar(db: Session, g: Grabacion, dispositivo: str, fabrica: sessionmaker) -> Grabacion:
    """El equipo grabador avisa que ya subió el último trozo."""
    _del_grabador(g, dispositivo)
    if g.estado != E.TERMINANDO:
        raise _ilegal("finalizar", g)
    _iniciar_procesamiento(db, g, fabrica)
    return g


# --- Procesar ---------------------------------------------------------------------------------------


def _lanzar(funcion, *args) -> None:
    threading.Thread(target=funcion, args=args, daemon=True).start()


def _iniciar_procesamiento(db: Session, g: Grabacion, fabrica: sessionmaker) -> None:
    if g.trozos == 0:
        g.estado, g.error = E.ERROR, "No llegó nada de audio: revisa el micrófono y vuelve a intentarlo"
        borrar_audio(g.id)
        db.commit()
        return
    g.estado, g.error = E.PROCESANDO, None
    db.commit()
    _lanzar(procesar, g.id, fabrica)


_servicio = None
_cerrojo_modelo = threading.Lock()  # un solo procesamiento a la vez (la cola con prioridad es la Fase 5)


def transcribir(ruta: str) -> tuple[str, str]:
    global _servicio
    from servicios.servicio_transcripcion import TranscriptionService

    if _servicio is None:
        _servicio = TranscriptionService()
    if _servicio.engine.current_model is None:
        _servicio.load_model(MODELO_WHISPER)
    final = None
    for final in _servicio.transcribe_file(ruta):
        pass
    if final is None or str(final.get("status", "")).startswith("❌"):
        raise ErrorProceso((final or {}).get("text") or "No se pudo transcribir el audio")
    return final["text"], final.get("srt", "")


def generar_material(texto: str) -> tuple[str, str, str, list]:
    from servicios.servicio_material_estudio import generate_study_material

    resumen, puntos, hoja, tarjetas = generate_study_material(texto)
    if not (puntos or hoja or tarjetas):  # el generador devuelve el error como "resumen"
        raise ErrorProceso(resumen or "No se pudo generar el material de estudio")
    return resumen, puntos, hoja, tarjetas


def _unir_trozos(carpeta: Path, mime: str) -> Path:
    destino = carpeta / f"clase.{EXTENSION[mime]}"
    with destino.open("wb") as salida:
        for parte in sorted(carpeta.glob("*.parte")):
            with parte.open("rb") as f:
                shutil.copyfileobj(f, salida)
    return destino


def procesar(grabacion_id: int, fabrica: sessionmaker) -> None:
    with _cerrojo_modelo:
        db = fabrica()
        try:
            g = db.get(Grabacion, grabacion_id)
            if g is None:
                return
            texto = srt = ""
            try:
                archivo = _unir_trozos(_carpeta(g.id), g.mime or "audio/webm")
                texto, srt = transcribir(str(archivo))
                if not texto.strip():
                    raise ErrorProceso("No se detectó voz en el audio")
                resumen, puntos, hoja, tarjetas = generar_material(texto)
                g.clase.contenido = ContenidoClase(
                    transcripcion_texto=texto, transcripcion_srt=srt, resumen=resumen,
                    puntos_clave=puntos, hoja_repaso=hoja, tarjetas=tarjetas,
                )
                g.estado, g.error = E.TERMINADA, None
            except ErrorProceso as e:
                g.estado, g.error = E.ERROR, str(e)
                if texto.strip():  # falló la generación pero la transcripción se conserva (oculta a los alumnos)
                    g.clase.contenido = ContenidoClase(transcripcion_texto=texto, transcripcion_srt=srt, retirado=True)
            except Exception:
                traceback.print_exc()
                g.estado, g.error = E.ERROR, "Falló el procesamiento de la clase"
            db.commit()
        finally:
            borrar_audio(grabacion_id)  # pase lo que pase, el audio no sobrevive
            db.close()


# --- Vigilancia: corte automático y limpieza -------------------------------------------------------


def vigilar(db: Session, fabrica: sessionmaker, utc: datetime.datetime | None = None, local: datetime.datetime | None = None) -> None:
    utc, local = utc or ahora_utc(), local or ahora_local()
    for g in db.query(Grabacion).filter(Grabacion.estado.in_(ACTIVAS)).all():
        if g.estado == E.ESPERANDO and local > g.corte_en:
            _eliminar(db, g)  # nunca se inició y ya pasó el bloque
        elif g.estado in (E.GRABANDO, E.PAUSADA):
            sin_grabador = g.latido_en is None or (utc - g.latido_en).total_seconds() > MAX_SIN_GRABADOR_S
            if local > g.corte_en or sin_grabador:
                g.estado, g.terminando_desde = E.TERMINANDO, utc
                db.commit()
        elif g.estado == E.TERMINANDO and (utc - (g.terminando_desde or utc)).total_seconds() > ESPERA_FINALIZAR_S:
            _iniciar_procesamiento(db, g, fabrica)  # el equipo no finalizó: se procesa lo que llegó


def recuperar_al_iniciar(db: Session) -> None:
    """Tras un reinicio del servidor: lo que estaba procesándose se pierde (y su audio se borra: no se
    conserva nada fuera de un procesamiento), y cualquier carpeta de audio huérfana se elimina."""
    for g in db.query(Grabacion).filter(Grabacion.estado == E.PROCESANDO).all():
        g.estado, g.error = E.ERROR, "El servidor se reinició mientras se procesaba la clase"
    db.commit()
    vivas = {str(g.id) for g in db.query(Grabacion).filter(Grabacion.estado.in_(ACTIVAS)).all()}
    if CARPETA_AUDIO.exists():
        for d in CARPETA_AUDIO.iterdir():
            if d.is_dir() and d.name not in vivas:
                shutil.rmtree(d, ignore_errors=True)
