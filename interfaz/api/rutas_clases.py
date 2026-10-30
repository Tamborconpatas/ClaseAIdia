# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import datetime
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session, selectinload

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import (
    AlumnoCurso,
    Bloque,
    Clase,
    ContenidoClase,
    Curso,
    EstadoGrabacion,
    FotoPizarra,
    Grabacion,
    RolNombre,
    Usuario,
)
from infraestructura.seguridad import ahora_utc
from interfaz.api.dependencias_auth import requiere_rol, rol_principal, usuario_actual
from interfaz.api.esquemas import ClaseDetalleOut, ClaseOut, ContenidoEditar, ContenidoOut, MapaEditar, PizarraEditar, PizarraOut, RelacionMapa, TarjetaOut

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


def _estado_sin_material(g: Grabacion | None) -> str:
    """Una clase sin material todavía: se está grabando, se está procesando, o falló."""
    if g is None:
        return "procesando"
    if g.estado == EstadoGrabacion.ERROR:
        return "error"
    if g.estado in (EstadoGrabacion.PROCESANDO, EstadoGrabacion.TERMINADA):
        return "procesando"
    return "grabando"


def _estado(k: ContenidoClase | None, ahora: datetime.datetime, g: Grabacion | None = None) -> str:
    if k is None or (g is not None and g.estado in (EstadoGrabacion.ERROR, EstadoGrabacion.PROCESANDO) and not k.resumen):
        # Sin material todavía; o falló/está regenerándose la generación y solo se conserva la transcripción.
        return _estado_sin_material(g)
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
        .options(selectinload(Clase.bloque).selectinload(Bloque.curso), selectinload(Clase.contenido), selectinload(Clase.grabacion))
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
    estado = _estado(c.contenido, ahora, c.grabacion)
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
            mapa=[RelacionMapa(**r) for r in (k.mapa_conceptual or [])],
            pizarra=[
                PizarraOut(id=f.id, segundo=f.segundo, texto=f.texto)
                for f in (clase.grabacion.fotos if clase.grabacion is not None else [])
                if f.estado == "leida" and (f.texto or "").strip()
            ],
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


@router.put("/{clase_id}/mapa", response_model=ClaseDetalleOut)
def editar_mapa(
    clase_id: int, datos: MapaEditar, db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """El profesor arma o corrige el mapa conceptual de la clase (una lista vacía lo quita)."""
    clase = _clases_visibles(db, staff).filter(Clase.id == clase_id).first()
    if clase is None:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    if clase.contenido is None:
        raise HTTPException(status_code=409, detail="Esta clase todavía no tiene material para editar")
    clase.contenido.mapa_conceptual = [r.model_dump() for r in datos.relaciones] or None
    db.commit()
    db.refresh(clase)
    return _detalle(clase)


def _foto_de(db: Session, staff: Usuario, clase_id: int, foto_id: int) -> tuple[Clase, FotoPizarra]:
    clase = _clases_visibles(db, staff).filter(Clase.id == clase_id).first()
    foto = db.get(FotoPizarra, foto_id) if clase is not None and clase.grabacion is not None else None
    if foto is None or foto.grabacion_id != clase.grabacion.id or foto.estado != "leida":
        raise HTTPException(status_code=404, detail="Foto de la pizarra no encontrada")
    return clase, foto


@router.put("/{clase_id}/pizarra/{foto_id}", response_model=ClaseDetalleOut)
def editar_pizarra(
    clase_id: int, foto_id: int, datos: PizarraEditar, db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """El profesor corrige lo que la IA leyó de la pizarra (las cifras a mano son lo que más falla) antes de que lo vean los alumnos."""
    clase, foto = _foto_de(db, staff, clase_id, foto_id)
    foto.texto = datos.texto
    db.commit()
    db.refresh(clase)
    return _detalle(clase)


@router.delete("/{clase_id}/pizarra/{foto_id}", response_model=ClaseDetalleOut)
def quitar_pizarra(
    clase_id: int, foto_id: int, db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Quita lo leído de una foto (mal leído, o no corresponde a la clase)."""
    clase, foto = _foto_de(db, staff, clase_id, foto_id)
    db.delete(foto)
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
