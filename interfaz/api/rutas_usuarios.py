from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import RolNombre, Usuario, UsuarioRol
from infraestructura.seguridad import hashear_secreto
from interfaz.api.dependencias_auth import requiere_rol, usuario_actual
from interfaz.api.esquemas import UsuarioCrear, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioOut, status_code=201)
def crear_usuario(
    datos: UsuarioCrear, db: Session = Depends(obtener_db), _utp: Usuario = Depends(requiere_rol(RolNombre.UTP))
):
    if datos.colegio_id != _utp.colegio_id:
        raise HTTPException(status_code=403, detail="Solo puedes crear usuarios en tu propio colegio")

    usuario = Usuario(
        rut=datos.rut,
        nombre=datos.nombre,
        colegio_id=datos.colegio_id,
        password_hash=hashear_secreto(datos.password),
    )
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
def listar_usuarios(db: Session = Depends(obtener_db), _utp: Usuario = Depends(requiere_rol(RolNombre.UTP))):
    return db.query(Usuario).filter_by(colegio_id=_utp.colegio_id).all()


@router.get("/{usuario_id}", response_model=UsuarioOut)
def obtener_usuario(usuario_id: int, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    usuario = db.get(Usuario, usuario_id)
    es_staff = {r.rol for r in actual.roles} & {RolNombre.PROFESOR, RolNombre.UTP}
    visible = usuario is not None and (
        usuario.id == actual.id or (es_staff and usuario.colegio_id == actual.colegio_id)
    )
    # 404 también cuando no es visible: no revela si el id existe.
    if not visible:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario
