import datetime
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session, selectinload

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import AlumnoCurso, Bloque, Clase, ContenidoClase, Curso, RolNombre, Usuario
from infraestructura.seguridad import ahora_utc
from interfaz.api.dependencias_auth import requiere_rol, rol_principal, usuario_actual
from interfaz.api.esquemas import ClaseDetalleOut, ClaseOut, ContenidoEditar, ContenidoOut, TarjetaOut

router = APIRouter(prefix="/clases", tags=["clases"])

# Horas que tiene el profesor, desde que el material queda listo, para aprobarlo o retirarlo. Pasado
# ese plazo sin hacer nada, el material se publica como "provisorio" (los alumnos ven una advertencia):
# un olvido del profesor no deja a los alumnos sin material. Configurable con HORAS_REVISION_PROFESOR.
HORAS_REVISION = int(os.environ.get("HORAS_REVISION_PROFESOR", "24"))


def _plazo() -> datetime.timedelta:
    return datetime.timedelta(hours=HORAS_REVISION)


def _utc(dt: datetime.datetime) -> datetime.datetime:
    """La base guarda UTC sin zona; al responder se marca como UTC para que el navegador lo convierta bien."""
    return dt.replace(tzinfo=datetime.timezone.utc)


def _estado(k: ContenidoClase | None, ahora: datetime.datetime) -> str:
    if k is None:
        return "procesando"
    if k.aprobado:
        return "publicada"
    if k.retirado:
        return "retirada"
    return "provisoria" if ahora >= (k.generado_en or ahora) + _plazo() else "por_aprobar"


def _clases_visibles(db: Session, usuario: Usuario) -> Query:
    """Una sola regla de visibilidad para el listado, el detalle y las acciones del profesor.
    UTP: todas las del colegio. Profesor: las de sus bloques, en cualquier estado.
    Alumno: las de su curso con material aprobado, o provisorio (sin aprobar, no retirado y con el
    plazo de revisión vencido)."""
    consulta = (
        db.query(Clase)
        .join(Bloque, Clase.bloque_id == Bloque.id)
        .join(Curso, Bloque.curso_id == Curso.id)
        .filter(Curso.colegio_id == usuario.colegio_id)
        .options(selectinload(Clase.bloque).selectinload(Bloque.curso), selectinload(Clase.contenido))
    )
    rol = rol_principal(usuario)
    if rol == RolNombre.PROFESOR:
        consulta = consulta.filter(Bloque.profesor_id == usuario.id)
    elif rol == RolNombre.ALUMNO:
        provisorio = and_(ContenidoClase.retirado.is_(False), ContenidoClase.generado_en <= ahora_utc() - _plazo())
        consulta = (
            consulta.join(AlumnoCurso, AlumnoCurso.curso_id == Curso.id)
            .filter(AlumnoCurso.usuario_id == usuario.id)
            .join(ContenidoClase, ContenidoClase.clase_id == Clase.id)
            .filter(or_(ContenidoClase.aprobado.is_(True), provisorio))
        )
    return consulta


def _resumen(c: Clase) -> dict:
    ahora = ahora_utc()
    estado = _estado(c.contenido, ahora)
    b = c.bloque
    return {
        "id": c.id,
        "bloque_id": c.bloque_id,
        "fecha": c.fecha,
        "curso_id": b.curso_id,
        "curso_nombre": b.curso.nombre,
        "asignatura": b.asignatura,
        "sala": b.sala,
        "hora_inicio": b.hora_inicio,
        "hora_fin": b.hora_fin,
        "profesor_id": b.profesor_id,
        "estado": estado,
        # Cuándo se publicará como provisorio si el profesor no la revisa (solo mientras espera revisión).
        "revision_vence": _utc((c.contenido.generado_en or ahora) + _plazo()) if estado == "por_aprobar" else None,
        "prioritaria": c.prioritaria,
    }


def _detalle(clase: Clase) -> dict:
    contenido = None
    if clase.contenido is not None:
        k = clase.contenido
        contenido = ContenidoOut(
            resumen=k.resumen,
            puntos_clave=k.puntos_clave,
            hoja_repaso=k.hoja_repaso,
            tarjetas=[TarjetaOut(**t) for t in (k.tarjetas or [])],
            transcripcion_texto=k.transcripcion_texto,
        )
    return {**_resumen(clase), "contenido": contenido}


@router.get("", response_model=list[ClaseOut])
def listar_clases(
    curso_id: int | None = None, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)
):
    consulta = _clases_visibles(db, actual)
    if curso_id is not None:
        consulta = consulta.filter(Curso.id == curso_id)
    # ponytail: tope fijo; paginar cuando un semestre de un profesor supere esto.
    clases = consulta.order_by(Clase.fecha.desc(), Bloque.hora_inicio.desc()).limit(300).all()
    return [_resumen(c) for c in clases]


@router.get("/{clase_id}", response_model=ClaseDetalleOut)
def obtener_clase(clase_id: int, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    clase = _clases_visibles(db, actual).filter(Clase.id == clase_id).first()
    if clase is None:  # inexistente o no visible: misma respuesta
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    return _detalle(clase)


def _revisar(clase_id: int, aprobar: bool, db: Session, staff: Usuario) -> dict:
    clase = _clases_visibles(db, staff).filter(Clase.id == clase_id).first()
    if clase is None:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    if clase.contenido is None:
        raise HTTPException(status_code=409, detail="Esta clase todavía no tiene material para revisar")
    clase.contenido.aprobado = aprobar
    clase.contenido.retirado = not aprobar
    db.commit()
    db.refresh(clase)
    return _detalle(clase)


@router.put("/{clase_id}/contenido", response_model=ClaseDetalleOut)
def editar_contenido(
    clase_id: int,
    datos: ContenidoEditar,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """El profesor corrige el material generado (resumen, puntos clave, hoja de repaso y tarjetas).
    No cambia su estado: si ya estaba publicada, los alumnos ven la versión corregida."""
    clase = _clases_visibles(db, staff).filter(Clase.id == clase_id).first()
    if clase is None:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    if clase.contenido is None:
        raise HTTPException(status_code=409, detail="Esta clase todavía no tiene material para editar")
    k = clase.contenido
    k.resumen, k.puntos_clave, k.hoja_repaso = datos.resumen, datos.puntos_clave, datos.hoja_repaso
    k.tarjetas = [t.model_dump() for t in datos.tarjetas]
    db.commit()
    db.refresh(clase)
    return _detalle(clase)


# Solo el profesor de esa clase (o el UTP). Se puede cambiar de opinión: una clase retirada se puede aprobar.
@router.post("/{clase_id}/aprobar", response_model=ClaseDetalleOut)
def aprobar_clase(
    clase_id: int,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Aprueba el material: los alumnos lo ven sin advertencia."""
    return _revisar(clase_id, True, db, staff)


@router.post("/{clase_id}/retirar", response_model=ClaseDetalleOut)
def retirar_clase(
    clase_id: int,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Oculta el material a los alumnos y evita que se publique solo como provisorio."""
    return _revisar(clase_id, False, db, staff)
