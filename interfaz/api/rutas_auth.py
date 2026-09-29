from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import RolNombre, Usuario, UsuarioRol
from infraestructura.seguridad import (
    LIMITE_INTENTOS,
    ahora_utc,
    calcular_bloqueo,
    hashear_secreto,
    verificar_secreto,
)
from interfaz.api.dependencias_auth import emitir_token
from interfaz.api.esquemas import BootstrapUtpIn, LoginAlumnoIn, LoginStaffIn, RestablecerPinIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


def verificar_bloqueo(usuario: Usuario):
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora_utc():
        raise HTTPException(
            status_code=429,
            detail=f"Cuenta bloqueada temporalmente. Reintenta después de {usuario.bloqueado_hasta.isoformat()}.",
        )


def registrar_resultado_intento(usuario: Usuario, exitoso: bool, db: Session):
    if exitoso:
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
    else:
        usuario.intentos_fallidos += 1
        if usuario.intentos_fallidos >= LIMITE_INTENTOS:
            usuario.bloqueado_hasta = ahora_utc() + calcular_bloqueo(usuario.intentos_fallidos)
    db.commit()


@router.post("/bootstrap-utp", response_model=TokenOut, status_code=201)
def bootstrap_utp(datos: BootstrapUtpIn, db: Session = Depends(obtener_db)):
    ya_tiene_utp = (
        db.query(Usuario)
        .join(UsuarioRol)
        .filter(Usuario.colegio_id == datos.colegio_id, UsuarioRol.rol == RolNombre.UTP)
        .first()
    )
    if ya_tiene_utp is not None:
        raise HTTPException(status_code=409, detail="Este colegio ya tiene un UTP registrado")

    usuario = Usuario(
        rut=datos.rut,
        nombre=datos.nombre,
        colegio_id=datos.colegio_id,
        password_hash=hashear_secreto(datos.password),
    )
    usuario.roles = [UsuarioRol(rol=RolNombre.UTP)]
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="RUT ya registrado o colegio inexistente") from e
    db.refresh(usuario)
    return emitir_token(usuario)


@router.post("/login/staff", response_model=TokenOut)
def login_staff(datos: LoginStaffIn, db: Session = Depends(obtener_db)):
    usuario = db.query(Usuario).filter_by(rut=datos.rut).first()
    if usuario is None or usuario.password_hash is None:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    verificar_bloqueo(usuario)

    if not verificar_secreto(datos.password, usuario.password_hash):
        registrar_resultado_intento(usuario, exitoso=False, db=db)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    registrar_resultado_intento(usuario, exitoso=True, db=db)
    return emitir_token(usuario)


@router.post("/login/alumno", response_model=TokenOut)
def login_alumno(datos: LoginAlumnoIn, db: Session = Depends(obtener_db)):
    usuario = db.query(Usuario).filter_by(rut=datos.rut).first()
    if usuario is None or usuario.pin_hash is None:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    verificar_bloqueo(usuario)

    if not verificar_secreto(datos.pin, usuario.pin_hash):
        registrar_resultado_intento(usuario, exitoso=False, db=db)
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    registrar_resultado_intento(usuario, exitoso=True, db=db)
    return emitir_token(usuario)


@router.post("/restablecer-pin", response_model=TokenOut)
def restablecer_pin(datos: RestablecerPinIn, db: Session = Depends(obtener_db)):
    """El alumno fija su PIN nuevo con el código de un solo uso que le dio el staff
    (POST /usuarios/{id}/reset-pin). Cuenta intentos igual que el login."""
    usuario = db.query(Usuario).filter_by(rut=datos.rut).first()
    if usuario is None or usuario.codigo_reset_hash is None:
        raise HTTPException(status_code=401, detail="Código inválido o vencido")

    verificar_bloqueo(usuario)

    if usuario.codigo_reset_vence < ahora_utc() or not verificar_secreto(datos.codigo, usuario.codigo_reset_hash):
        registrar_resultado_intento(usuario, exitoso=False, db=db)
        raise HTTPException(status_code=401, detail="Código inválido o vencido")

    usuario.pin_hash = hashear_secreto(datos.pin)
    usuario.codigo_reset_hash = None
    usuario.codigo_reset_vence = None
    registrar_resultado_intento(usuario, exitoso=True, db=db)
    return emitir_token(usuario)
