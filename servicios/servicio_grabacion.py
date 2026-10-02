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
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from infraestructura.seguridad import ahora_utc as reloj_de_revision
from nucleo.memoria import esperar_memoria
from servicios.trabajador import CODIGO_SIN_MEMORIA

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
# Limpieza de ruido del audio antes de transcribir. Sin DeepFilterNet a propósito: compila una extensión en Rust, no
# trae versión lista para todos los sistemas y no corre bien en un equipo modesto. Medido con una clase real y ruido
# de aula agregado: `light_dsp` casi no toca el audio limpio (94 % igual) y recupera ~13 puntos con ruido parejo
# (ventilador, proyector); `dsp`, `heavy_dsp` y `mmse` limpian algo más pero distorsionan más el audio limpio.
MODOS_DE_LIMPIEZA = ("none", "light_dsp", "dsp", "heavy_dsp", "mmse")
LIMPIEZA_POR_DEFECTO = "light_dsp"
# Minutos después del término del bloque en que la grabación se corta sola (por si el profesor olvida terminarla).
GRACIA_CORTE_MIN = int(os.environ.get("MINUTOS_CORTE_GRABACION", "15"))
# El procesamiento de una clase corre en un proceso aparte (servicios/trabajador.py) para que, si se queda sin memoria,
# caiga solo él y no el servidor que atiende a alumnos y profesores.
RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
COMANDO_TRABAJADOR = [sys.executable, "-m", "servicios.trabajador"]
MEMORIA_MINIMA_GB = float(os.environ.get("MEMORIA_MINIMA_PROCESAMIENTO_GB", "2.5"))  # libre para empezar (Whisper por tramos usa < 2)
ESPERA_MEMORIA_S = 600  # cuánto espera a que haya esa memoria antes de dejar la clase en error
TIEMPO_MAXIMO_S = float(os.environ.get("TIEMPO_MAXIMO_PROCESAMIENTO_HORAS", "4")) * 3600  # un procesamiento atascado no bloquea al servidor
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
        k, g = clase.contenido, clase.grabacion
        if g is not None and g.estado == E.ERROR and not k.resumen:
            return g  # falló solo la generación: la sesión sigue ahí para regenerar el material
        raise ErrorGrabacion("Esta clase ya tiene su material")
    if clase is not None and clase.grabacion is not None:
        g = clase.grabacion
        if reintentos_pendientes(g):
            return g  # se reintenta sola: reiniciarla borraría el audio que el reintento necesita
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
    """Procesa la clase en un proceso aparte (lo normal). `PROCESAMIENTO_EN_HILO=1` lo hace en un hilo del servidor:
    solo para desarrollo, porque sin el proceso aparte una falta de memoria se lleva también al servidor."""
    if os.environ.get("PROCESAMIENTO_EN_HILO") == "1":
        threading.Thread(target=funcion, args=args, daemon=True).start()
        return
    modo = "generacion" if funcion is procesar_generacion else "clase"
    threading.Thread(target=_trabajar_aparte, args=(modo, args[0], args[1]), daemon=True).start()


# Esperas (minutos) antes de cada reintento automático de un procesamiento que falló. Nadie está frente al computador
# cuando algo falla (memoria, un corte, Ollama apagado), así que se reintenta solo; el audio se conserva hasta el último.
REINTENTOS_MIN = (5, 15, 45)


def programar_reintento(g: Grabacion, mensaje: str) -> None:
    """Deja la sesión en error y, si quedan intentos, programa el siguiente. El mensaje queda a la vista del profesor."""
    g.estado = E.ERROR
    if g.intentos < len(REINTENTOS_MIN):
        espera = datetime.timedelta(minutes=REINTENTOS_MIN[g.intentos])
        g.reintento_en = ahora_utc() + espera
        hora = (ahora_local() + espera).strftime("%H:%M")
        g.error = f"{mensaje} Se reintentará sola a las {hora} (intento {g.intentos + 2} de {len(REINTENTOS_MIN) + 1})."
    else:
        g.reintento_en = None
        g.error = f"{mensaje} Ya se reintentó {len(REINTENTOS_MIN)} veces sin éxito."


def reintentos_pendientes(g: Grabacion) -> bool:
    return g.estado == E.ERROR and g.reintento_en is not None


MENSAJE_SIN_MEMORIA = "El equipo no tenía memoria suficiente para procesar la clase: se cortó antes de afectar al resto de la plataforma."


def _fallo(grabacion_id: int, fabrica: sessionmaker, mensaje: str) -> None:
    """Deja la sesión en error con el motivo y programa el reintento, salvo que el trabajador ya la haya cerrado
    (terminada o con su propio error)."""
    with fabrica() as db:
        g = db.get(Grabacion, grabacion_id)
        if g is not None and g.estado == E.PROCESANDO:
            programar_reintento(g, mensaje)
            db.commit()


def _trabajar_aparte(modo: str, grabacion_id: int, fabrica: sessionmaker) -> None:
    with _cerrojo_modelo:  # uno a la vez (la cola con prioridad es la Fase 5)
        try:
            if not esperar_memoria(MEMORIA_MINIMA_GB, ESPERA_MEMORIA_S):
                _fallo(grabacion_id, fabrica, MENSAJE_SIN_MEMORIA)
                return
            proceso = subprocess.Popen([*COMANDO_TRABAJADOR, modo, str(grabacion_id)], cwd=RAIZ_DEL_PROYECTO)
            _anotar_proceso(grabacion_id, proceso.pid)
            try:
                codigo = proceso.wait(timeout=TIEMPO_MAXIMO_S)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.wait()
                _fallo(grabacion_id, fabrica, f"El procesamiento tardó más de {TIEMPO_MAXIMO_S / 3600:g} horas y se canceló.")
                return
            if codigo != 0:
                _fallo(
                    grabacion_id, fabrica,
                    MENSAJE_SIN_MEMORIA if codigo == CODIGO_SIN_MEMORIA
                    else f"El procesamiento se interrumpió inesperadamente (código {codigo}).",
                )
        except Exception:
            traceback.print_exc()
            _fallo(grabacion_id, fabrica, "No se pudo iniciar el procesamiento de la clase")
        finally:
            if modo == "clase":
                _borrar_audio_si_ya_no_hace_falta(grabacion_id, fabrica)


def _borrar_audio_si_ya_no_hace_falta(grabacion_id: int, fabrica: sessionmaker) -> None:
    """El audio no sobrevive al procesamiento: se borra cuando terminó bien o cuando ya no se va a reintentar. Mientras haya
    un reintento programado se conserva (es parte del mismo procesamiento: no se puede reintentar sin él)."""
    with fabrica() as db:
        g = db.get(Grabacion, grabacion_id)
        k = g.clase.contenido if g is not None else None
        transcripcion_guardada = k is not None and bool((k.transcripcion_texto or "").strip())
        # Si ya está la transcripción, el reintento solo regenera el material: el audio no se necesita para nada.
        if g is None or not reintentos_pendientes(g) or transcripcion_guardada:
            borrar_audio(grabacion_id)


def _anotar_proceso(grabacion_id: int, pid: int) -> None:
    """Para saber, tras un reinicio del servidor, si el trabajador sigue vivo."""
    carpeta = _carpeta(grabacion_id)
    if carpeta.exists():
        (carpeta / "trabajador.pid").write_text(str(pid), encoding="utf-8")


def _proceso_vivo(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            salida = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10).stdout
            return str(pid) in salida
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


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


def modo_de_limpieza() -> str:
    """El modo pedido en LIMPIEZA_AUDIO. Si no existe (o es `deepfilter`, que no se ofrece), se usa el de por defecto."""
    pedido = os.environ.get("LIMPIEZA_AUDIO", LIMPIEZA_POR_DEFECTO).strip().lower()
    if pedido in MODOS_DE_LIMPIEZA:
        return pedido
    print(f"AVISO: LIMPIEZA_AUDIO='{pedido}' no es válido (opciones: {', '.join(MODOS_DE_LIMPIEZA)}); se usa {LIMPIEZA_POR_DEFECTO}.")
    return LIMPIEZA_POR_DEFECTO


def config_de_limpieza() -> dict:
    modo = modo_de_limpieza()
    return {"enabled": modo != "none", "denoise_mode": modo, "normalize_input": True, "normalize_output": True, "highpass_hz": 80}


def transcribir(ruta: str) -> tuple[str, str]:
    global _servicio
    from servicios.servicio_transcripcion import TranscriptionService

    if _servicio is None:
        _servicio = TranscriptionService()
    if _servicio.engine.current_model is None:
        _servicio.load_model(MODELO_WHISPER)
    _servicio.set_enhancement_config(config_de_limpieza())
    final = None
    for final in _servicio.transcribe_file(ruta):
        pass
    # Whisper ya no se necesita: se libera su memoria de la GPU para que Ollama la use entera (en una GPU de 4 GB
    # compiten, y lo que no cabe se va a la CPU y la generación se vuelve mucho más lenta). La próxima clase lo recarga.
    liberar = getattr(_servicio.engine, "free_memory", None)
    if liberar:
        liberar()
    if final is None or str(final.get("status", "")).startswith("❌"):
        raise ErrorProceso((final or {}).get("text") or "No se pudo transcribir el audio")
    return final["text"], final.get("srt", "")


def generar_material(texto: str, asignatura: str | None = None) -> tuple[str, str, str, list]:
    from servicios.servicio_material_estudio import generate_study_material

    resumen, puntos, hoja, tarjetas = generate_study_material(texto, asignatura)
    if not (puntos or hoja or tarjetas):  # el generador devuelve el error como "resumen"
        raise ErrorProceso(resumen or "No se pudo generar el material de estudio")
    return resumen, puntos, hoja, tarjetas


def _empieza_un_flujo(inicio: bytes, mime: str) -> bool:
    """¿Este trozo es el comienzo de una grabación del navegador (con su cabecera) y no la continuación de otra?
    Un equipo que vuelve (se recargó la página, el celular se durmió) empieza un flujo nuevo."""
    if mime == "audio/webm":
        return inicio[:4] == b"\x1a\x45\xdf\xa3"
    if mime == "audio/mp4":
        return inicio[4:8] == b"ftyp"
    if mime == "audio/ogg":
        return inicio[:4] == b"OggS" and len(inicio) > 5 and bool(inicio[5] & 0x02)  # página de inicio de flujo
    return False  # wav y mp3 se pueden concatenar tal cual


def _flujos(partes: list[Path], mime: str) -> list[list[Path]]:
    flujos: list[list[Path]] = []
    for parte in partes:
        with parte.open("rb") as f:
            inicio = f.read(16)
        if not flujos or _empieza_un_flujo(inicio, mime):
            flujos.append([])
        flujos[-1].append(parte)
    return flujos


def _concatenar(partes: list[Path], destino: Path) -> None:
    with destino.open("wb") as salida:
        for parte in partes:
            with parte.open("rb") as f:
                shutil.copyfileobj(f, salida)


def _unir_trozos(carpeta: Path, mime: str) -> Path:
    """Une los trozos en un solo archivo. Si hubo varios flujos (el equipo se cortó y volvió), cada uno se
    convierte aparte a wav 16 kHz mono y se juntan: pegar flujos con cabecera propia no es un archivo válido."""
    flujos = _flujos(sorted(carpeta.glob("*.parte")), mime)
    if len(flujos) <= 1:
        destino = carpeta / f"clase.{EXTENSION[mime]}"
        _concatenar(flujos[0] if flujos else [], destino)
        return destino

    import wave

    from infraestructura.herramientas_ffmpeg import optimize_audio_ffmpeg

    destino = carpeta / "clase.wav"
    with wave.open(str(destino), "wb") as salida:
        salida.setnchannels(1)
        salida.setsampwidth(2)
        salida.setframerate(16000)
        for i, partes in enumerate(flujos):
            crudo = carpeta / f"flujo{i}.{EXTENSION[mime]}"
            _concatenar(partes, crudo)
            convertido = optimize_audio_ffmpeg(str(crudo))
            try:
                with wave.open(convertido, "rb") as entrada:
                    salida.writeframes(entrada.readframes(entrada.getnframes()))
            except (wave.Error, EOFError) as e:
                raise ErrorProceso("No se pudo unir el audio de la clase (¿está instalado ffmpeg?)") from e
            finally:
                if convertido != str(crudo) and os.path.exists(convertido):
                    os.remove(convertido)
                crudo.unlink(missing_ok=True)
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
                resumen, puntos, hoja, tarjetas = generar_material(texto, g.clase.bloque.asignatura)
                g.clase.contenido = ContenidoClase(
                    transcripcion_texto=texto, transcripcion_srt=srt, resumen=resumen,
                    puntos_clave=puntos, hoja_repaso=hoja, tarjetas=tarjetas,
                )
                g.estado, g.error = E.TERMINADA, None
            except ErrorProceso as e:
                if texto.strip():  # falló la generación: se conserva la transcripción (oculta) y se reintenta solo la generación
                    g.clase.contenido = ContenidoClase(transcripcion_texto=texto, transcripcion_srt=srt, retirado=True)
                    programar_reintento(g, str(e))
                else:  # sin voz o sin poder transcribir: reintentar no lo arregla
                    g.estado, g.error, g.reintento_en = E.ERROR, str(e), None
            except Exception:
                traceback.print_exc()
                programar_reintento(g, "Falló el procesamiento de la clase.")  # con el audio, que se conserva para el reintento
            db.commit()
        finally:
            db.close()
            _borrar_audio_si_ya_no_hace_falta(grabacion_id, fabrica)


def regenerar(db: Session, g: Grabacion, fabrica: sessionmaker) -> Grabacion:
    """Si falló solo la generación (p. ej. Ollama estaba apagado), la transcripción se conservó: se vuelve a
    generar el material desde ese texto, sin audio y sin volver a grabar."""
    k = g.clase.contenido
    if g.estado != E.ERROR or k is None or not (k.transcripcion_texto or "").strip() or k.resumen:
        raise ErrorGrabacion("Solo se puede regenerar cuando falló la generación del material")
    g.estado, g.error, g.reintento_en = E.PROCESANDO, None, None
    db.commit()
    _lanzar(procesar_generacion, g.id, fabrica)
    return g


def procesar_generacion(grabacion_id: int, fabrica: sessionmaker) -> None:
    with _cerrojo_modelo:
        db = fabrica()
        try:
            g = db.get(Grabacion, grabacion_id)
            if g is None:
                return
            k = g.clase.contenido
            try:
                resumen, puntos, hoja, tarjetas = generar_material(k.transcripcion_texto, g.clase.bloque.asignatura)
                k.resumen, k.puntos_clave, k.hoja_repaso, k.tarjetas = resumen, puntos, hoja, tarjetas
                k.retirado, k.generado_en = False, reloj_de_revision()  # vuelve al flujo normal: por aprobar (el plazo de revisión corre desde ahora)
                g.estado, g.error = E.TERMINADA, None
            except ErrorProceso as e:
                programar_reintento(g, str(e))
            except Exception:
                traceback.print_exc()
                programar_reintento(g, "Falló la generación del material.")
            db.commit()
        finally:
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
    for g in db.query(Grabacion).filter(Grabacion.estado == E.ERROR, Grabacion.reintento_en.is_not(None), Grabacion.reintento_en <= utc).all():
        _reintentar(db, g, fabrica)


def _reintentar(db: Session, g: Grabacion, fabrica: sessionmaker) -> None:
    k = g.clase.contenido
    if k is not None and (k.transcripcion_texto or "").strip() and not k.resumen:
        funcion = procesar_generacion  # la transcripción está: solo falta el material, sin audio
    elif any(_carpeta(g.id).glob("*.parte")):
        funcion = procesar
    else:
        g.reintento_en = None
        g.error = f"{g.error or ''} No queda audio para reintentar: hay que grabar la clase de nuevo.".strip()
        db.commit()
        return
    g.intentos += 1
    g.estado, g.error, g.reintento_en = E.PROCESANDO, None, None
    db.commit()
    _lanzar(funcion, g.id, fabrica)


def reintentar_ahora(db: Session, g: Grabacion) -> Grabacion:
    """El profesor (o el UTP) no quiere esperar: el vigilante lanza el reintento programado en unos segundos."""
    if not reintentos_pendientes(g):
        raise ErrorGrabacion("No hay un reintento automático pendiente")
    g.reintento_en = ahora_utc()
    db.commit()
    return g


def _trabajador_vivo(carpeta: Path) -> bool:
    archivo = carpeta / "trabajador.pid"
    try:
        return archivo.exists() and _proceso_vivo(int(archivo.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return False


def recuperar_al_iniciar(db: Session, fabrica: sessionmaker | None = None) -> None:
    """Tras un reinicio del servidor (por ejemplo un corte de luz), una clase que se estaba procesando no se pierde: su
    audio sigue en disco (solo mientras se procesa) y, con `fabrica`, se vuelve a procesar desde ahí. Si ya no hay audio
    pero sí la transcripción, solo se regenera el material; si no hay nada, queda en error. Si el trabajador sigue
    vivo (se reinició solo el servidor) no se toca: terminará y dejará el resultado. Sin `fabrica` no se reanuda nada.
    Las carpetas de audio que no son de una sesión activa ni en proceso se borran."""
    en_proceso = set()
    for g in db.query(Grabacion).filter(Grabacion.estado == E.PROCESANDO).all():
        carpeta = _carpeta(g.id)
        if _trabajador_vivo(carpeta):
            en_proceso.add(str(g.id))
        elif fabrica is not None and any(carpeta.glob("*.parte")):
            en_proceso.add(str(g.id))
            _lanzar(procesar, g.id, fabrica)
        elif fabrica is not None and g.clase.contenido is not None and (g.clase.contenido.transcripcion_texto or "").strip() and not g.clase.contenido.resumen:
            _lanzar(procesar_generacion, g.id, fabrica)
        else:
            g.estado, g.error = E.ERROR, "El servidor se reinició mientras se procesaba la clase"
    db.commit()
    vivas = {str(g.id) for g in db.query(Grabacion).filter(Grabacion.estado.in_(ACTIVAS)).all()} | en_proceso
    vivas |= {str(g.id) for g in db.query(Grabacion).filter(Grabacion.estado == E.ERROR, Grabacion.reintento_en.is_not(None)).all()}  # su reintento necesita el audio
    if CARPETA_AUDIO.exists():
        for d in CARPETA_AUDIO.iterdir():
            if d.is_dir() and d.name not in vivas:
                shutil.rmtree(d, ignore_errors=True)
