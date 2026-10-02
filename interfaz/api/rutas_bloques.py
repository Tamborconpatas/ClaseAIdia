from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Bloque, Curso, RolNombre, Usuario
from interfaz.api.dependencias_auth import requiere_rol
from interfaz.api.esquemas import BloqueCrear, BloqueOut

router = APIRouter(prefix="/bloques", tags=["bloques"])


def verificar_bloque(db: Session, utp: Usuario, curso: Curso, datos: BloqueCrear, excluir_id: int | None = None) -> None:
    """Reglas del horario, comunes a crear y editar: el profesor debe ser del colegio, y el bloque no puede
    cruzarse con otro del mismo curso ni poner al mismo profesor en dos lugares a la vez."""
    if datos.profesor_id is not None:
        profesor = db.get(Usuario, datos.profesor_id)
        if (
            profesor is None
            or profesor.colegio_id != utp.colegio_id
            or RolNombre.PROFESOR not in {r.rol for r in profesor.roles}
        ):
            raise HTTPException(status_code=409, detail="profesor_id inexistente")
        # Un profesor desactivado no recibe bloques nuevos (a un bloque que ya era suyo se le puede seguir editando la hora).
        actual = db.get(Bloque, excluir_id) if excluir_id is not None else None
        if not profesor.activo and (actual is None or actual.profesor_id != profesor.id):
            raise HTTPException(status_code=409, detail="Ese profesor está desactivado")

    cruzan = db.query(Bloque).filter(
        Bloque.dia_semana == datos.dia_semana,
        Bloque.hora_inicio < datos.hora_fin,
        Bloque.hora_fin > datos.hora_inicio,
    )
    if excluir_id is not None:
        cruzan = cruzan.filter(Bloque.id != excluir_id)
    if cruzan.filter(Bloque.curso_id == curso.id).first() is not None:
        raise HTTPException(status_code=409, detail="Ese horario se cruza con otro bloque del curso")
    if datos.profesor_id is not None:
        otro = cruzan.filter(Bloque.profesor_id == datos.profesor_id).first()
        if otro is not None:
            raise HTTPException(
                status_code=409, detail=f"El profesor ya tiene un bloque a esa hora en el curso {otro.curso.nombre}"
            )


def _bloque_del_colegio(db: Session, utp: Usuario, bloque_id: int) -> Bloque:
    bloque = (
        db.query(Bloque)
        .join(Curso, Bloque.curso_id == Curso.id)
        .filter(Bloque.id == bloque_id, Curso.colegio_id == utp.colegio_id)
        .first()
    )
    if bloque is None:  # inexistente o de otro colegio: misma respuesta
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    return bloque


@router.put("/{bloque_id}", response_model=BloqueOut)
def editar_bloque(
    bloque_id: int,
    datos: BloqueCrear,
    db: Session = Depends(obtener_db),
    utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    """Reemplaza los datos del bloque (el curso no cambia)."""
    bloque = _bloque_del_colegio(db, utp, bloque_id)
    verificar_bloque(db, utp, bloque.curso, datos, excluir_id=bloque.id)
    for campo, valor in datos.model_dump().items():
        setattr(bloque, campo, valor)
    db.commit()
    db.refresh(bloque)
    return bloque


@router.delete("/{bloque_id}", status_code=204)
def borrar_bloque(
    bloque_id: int, db: Session = Depends(obtener_db), utp: Usuario = Depends(requiere_rol(RolNombre.UTP))
):
    bloque = _bloque_del_colegio(db, utp, bloque_id)
    # El borrado en cascada se llevaría las clases del bloque con su material de estudio.
    if bloque.clases:
        raise HTTPException(status_code=409, detail="Este bloque ya tiene clases registradas; no se puede borrar")
    db.delete(bloque)
    db.commit()
