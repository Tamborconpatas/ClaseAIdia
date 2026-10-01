import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import AlumnoCurso, Bloque, RolNombre, Usuario, UsuarioRol
from infraestructura.seguridad import VIGENCIA_CODIGO_RESET_MINUTOS, ahora_utc, hashear_secreto
from interfaz.api.dependencias_auth import requiere_rol, rol_principal, usuario_actual
from interfaz.api.esquemas import ResetPinOut, UsuarioCrear, UsuarioOut
from nucleo.codigos import generar_codigo_invitacion

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


@router.post("/{usuario_id}/reset-password", response_model=ResetPinOut)
def resetear_password(
    usuario_id: int,
    db: Session = Depends(obtener_db),
    utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    """Un UTP invalida la contraseña de un profesor u otro UTP y le da un código de un solo uso, con vencimiento,
    para que elija una nueva en POST /auth/restablecer-password. Un UTP no resetea la suya: se lo pide a otro UTP
    o, si es el único, a quien administra el servidor (`python -m scripts.restablecer_utp <RUT>`)."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or usuario.colegio_id != utp.colegio_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario.id == utp.id:
        raise HTTPException(status_code=409, detail="No puedes resetear tu propia contraseña: pídeselo a otro UTP o a quien administra el servidor")
    if not {r.rol for r in usuario.roles} & {RolNombre.PROFESOR, RolNombre.UTP}:
        raise HTTPException(status_code=409, detail="Solo se puede resetear la contraseña de personal del colegio")

    codigo = generar_codigo_invitacion()
    vence = ahora_utc() + datetime.timedelta(minutes=VIGENCIA_CODIGO_RESET_MINUTOS)
    usuario.password_hash = None
    usuario.codigo_reset_hash = hashear_secreto(codigo)
    usuario.codigo_reset_vence = vence
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    db.commit()
    return ResetPinOut(codigo=codigo, vence=vence)


@router.post("/{usuario_id}/reset-pin", response_model=ResetPinOut)
def resetear_pin(
    usuario_id: int,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Invalida el PIN del alumno y devuelve un código de un solo uso, con vencimiento.
    El alumno elige su PIN nuevo en POST /auth/restablecer-pin con ese código:
    conocer el RUT (o el código del curso) no alcanza para quedarse con la cuenta."""
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or usuario.colegio_id != staff.colegio_id:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if RolNombre.ALUMNO not in {r.rol for r in usuario.roles}:
        raise HTTPException(status_code=409, detail="Solo se puede resetear el PIN de un alumno")
    if rol_principal(staff) == RolNombre.PROFESOR:
        # Un profesor solo resetea el PIN de alumnos de los cursos donde dicta (el UTP, el de cualquiera).
        dicta_ahi = (
            db.query(AlumnoCurso.id)
            .join(Bloque, Bloque.curso_id == AlumnoCurso.curso_id)
            .filter(AlumnoCurso.usuario_id == usuario.id, Bloque.profesor_id == staff.id)
            .first()
        )
        if dicta_ahi is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

    codigo = generar_codigo_invitacion()
    vence = ahora_utc() + datetime.timedelta(minutes=VIGENCIA_CODIGO_RESET_MINUTOS)
    usuario.pin_hash = None
    usuario.codigo_reset_hash = hashear_secreto(codigo)
    usuario.codigo_reset_vence = vence
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    db.commit()
    return ResetPinOut(codigo=codigo, vence=vence)
