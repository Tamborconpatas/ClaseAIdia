import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, selectinload, sessionmaker

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Bloque, Clase, Grabacion, RolNombre, TipoBloque, Usuario
from interfaz.api.dependencias_auth import requiere_rol
from interfaz.api.esquemas import (
    BloqueDeHoyOut,
    GrabacionComando,
    GrabacionCrear,
    GrabacionOut,
    GrabadorFinalizar,
    GrabadorLatido,
    GrabadorRegistrar,
)
from interfaz.api.red_local import solo_red_local
from servicios import servicio_grabacion as sg

# Todo lo de /grabaciones es de la red local y del profesor de ese bloque (ni el UTP ni otro profesor).
router = APIRouter(prefix="/grabaciones", tags=["grabaciones"], dependencies=[Depends(solo_red_local)])
profesor_actual = requiere_rol(RolNombre.PROFESOR)


def _salida(g: Grabacion) -> dict:
    b = g.clase.bloque
    return {
        "id": g.id, "clase_id": g.clase_id, "bloque_id": b.id, "asignatura": b.asignatura, "curso_nombre": b.curso.nombre,
        "sala": b.sala, "fecha": g.clase.fecha, "hora_inicio": b.hora_inicio, "hora_fin": b.hora_fin,
        "estado": g.estado.value, "silenciada": g.silenciada, "prioritaria": g.clase.prioritaria, "corte_en": g.corte_en,
        "segundos_grabados": g.segundos_grabados, "nivel": g.nivel, "trozos": g.trozos, "grabador_id": g.grabador_id,
        "grabador_conectado": sg.grabador_conectado(g), "error": g.error,
        "reintento_en": g.reintento_en.replace(tzinfo=datetime.timezone.utc) if g.reintento_en else None,
    }


def _propia(db: Session, grabacion_id: int, profesor: Usuario) -> Grabacion:
    g = db.get(Grabacion, grabacion_id)
    if g is None or g.clase.bloque.profesor_id != profesor.id:
        raise HTTPException(status_code=404, detail="Grabación no encontrada")
    return g


def _fabrica(db: Session) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())


@router.get("/hoy", response_model=list[BloqueDeHoyOut])
def bloques_de_hoy(db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """Los bloques de clase de hoy del profesor, con su sesión de grabación si ya existe."""
    ahora = sg.ahora_local()
    bloques = (
        db.query(Bloque)
        .options(selectinload(Bloque.curso), selectinload(Bloque.clases).selectinload(Clase.grabacion))
        .filter(Bloque.profesor_id == profesor.id, Bloque.tipo == TipoBloque.CLASE, Bloque.dia_semana == ahora.weekday())
        .order_by(Bloque.hora_inicio)
        .all()
    )
    salida = []
    for b in bloques:
        clase = next((c for c in b.clases if c.fecha == ahora.date()), None)
        puede, motivo = sg.estado_de_hoy(b, ahora)
        if clase is not None and clase.contenido is not None:
            puede, motivo = False, "Esta clase ya tiene su material"
        g = clase.grabacion if clase is not None else None
        if g is not None and g.estado in sg.ACTIVAS:
            puede, motivo = True, None  # una sesión en curso siempre se puede retomar
        salida.append({
            "bloque_id": b.id, "asignatura": b.asignatura, "curso_nombre": b.curso.nombre, "sala": b.sala,
            "hora_inicio": b.hora_inicio, "hora_fin": b.hora_fin, "puede_grabar": puede, "motivo": motivo,
            "grabacion": _salida(g) if g is not None else None,
        })
    return salida


@router.post("", response_model=GrabacionOut, status_code=201)
def crear_grabacion(datos: GrabacionCrear, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """Crea la sesión de grabación de un bloque de hoy, o retoma la que ya existe (así se puede cambiar de equipo)."""
    return _salida(sg.crear_o_reanudar(db, profesor, datos.bloque_id))


@router.get("/{grabacion_id}", response_model=GrabacionOut)
def ver_grabacion(grabacion_id: int, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    return _salida(_propia(db, grabacion_id, profesor))


@router.post("/{grabacion_id}/comando", response_model=GrabacionOut | None)
def comando(grabacion_id: int, datos: GrabacionComando, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    g = sg.aplicar_comando(db, _propia(db, grabacion_id, profesor), datos.accion)
    return _salida(g) if g is not None else None


@router.post("/{grabacion_id}/grabador", response_model=GrabacionOut)
def registrar_grabador(grabacion_id: int, datos: GrabadorRegistrar, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """Este equipo pasa a ser el que graba (el PC de la sala o el celular del profesor)."""
    return _salida(sg.registrar_grabador(db, _propia(db, grabacion_id, profesor), datos.dispositivo, datos.forzar))


@router.post("/{grabacion_id}/latido", response_model=GrabacionOut)
def latido(grabacion_id: int, datos: GrabadorLatido, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """Lo manda el equipo grabador cada par de segundos: avisa que sigue vivo y devuelve el estado que debe obedecer."""
    return _salida(sg.latido(db, _propia(db, grabacion_id, profesor), datos.dispositivo, datos.segundos, datos.nivel))


@router.put("/{grabacion_id}/trozos/{n}", response_model=GrabacionOut)
async def subir_trozo(
    grabacion_id: int, n: int, dispositivo: str, request: Request,
    db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual),
):
    """Un trozo de audio (cuerpo crudo, tipo audio/*). Se corta la lectura apenas supera el máximo."""
    g = _propia(db, grabacion_id, profesor)
    if len(dispositivo) < 8 or len(dispositivo) > 64:
        raise HTTPException(status_code=422, detail="dispositivo inválido")
    datos = bytearray()
    async for parte in request.stream():
        datos += parte
        if len(datos) > sg.MAX_TROZO_BYTES:
            raise HTTPException(status_code=413, detail="Trozo de audio demasiado grande")
    return _salida(sg.guardar_trozo(db, g, dispositivo, n, bytes(datos), request.headers.get("content-type", "")))


@router.post("/{grabacion_id}/finalizar", response_model=GrabacionOut)
def finalizar(grabacion_id: int, datos: GrabadorFinalizar, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    return _salida(sg.finalizar(db, _propia(db, grabacion_id, profesor), datos.dispositivo, _fabrica(db)))


@router.post("/{grabacion_id}/regenerar", response_model=GrabacionOut)
def regenerar(grabacion_id: int, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """Vuelve a generar el material desde la transcripción guardada, cuando falló solo la generación."""
    return _salida(sg.regenerar(db, _propia(db, grabacion_id, profesor), _fabrica(db)))


@router.post("/{grabacion_id}/reintentar-ahora", response_model=GrabacionOut)
def reintentar_ahora(grabacion_id: int, db: Session = Depends(obtener_db), profesor: Usuario = Depends(profesor_actual)):
    """No esperar al reintento automático programado: se lanza en unos segundos."""
    return _salida(sg.reintentar_ahora(db, _propia(db, grabacion_id, profesor)))
