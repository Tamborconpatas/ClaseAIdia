from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Usuario, UsuarioRol
from interfaz.api.esquemas import UsuarioCrear, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioOut, status_code=201)
def crear_usuario(datos: UsuarioCrear, db: Session = Depends(obtener_db)):
    usuario = Usuario(rut=datos.rut, nombre=datos.nombre, colegio_id=datos.colegio_id)
    usuario.roles = [UsuarioRol(rol=rol) for rol in datos.roles]
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="RUT ya registrado o colegio inexistente") from e
    db.refresh(usuario)
    return usuario


@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(db: Session = Depends(obtener_db)):
    return db.query(Usuario).all()


@router.get("/{usuario_id}", response_model=UsuarioOut)
def obtener_usuario(usuario_id: int, db: Session = Depends(obtener_db)):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario
