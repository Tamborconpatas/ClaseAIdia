import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import RolNombre, Usuario
from infraestructura.seguridad import crear_token, decodificar_token
from interfaz.api.esquemas import TokenOut

_bearer = HTTPBearer()


def emitir_token(usuario: Usuario) -> TokenOut:
    roles = [r.rol for r in usuario.roles]
    token = crear_token({"sub": str(usuario.id), "rut": usuario.rut, "roles": [r.value for r in roles], "v": usuario.version_sesion})
    return TokenOut(access_token=token, roles=roles, colegio_id=usuario.colegio_id)


def usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(obtener_db),
) -> Usuario:
    try:
        payload = decodificar_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    try:
        usuario_id = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido")
    if not 0 < usuario_id < 2**63:  # fuera del rango de la base: tampoco puede ser un usuario
        raise HTTPException(status_code=401, detail="Token inválido")
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if not usuario.activo:  # también corta las sesiones que ya estaban abiertas
        raise HTTPException(status_code=401, detail="Cuenta desactivada")
    if payload.get("v", 0) != usuario.version_sesion:  # cambió una credencial o se cerraron todas las sesiones
        raise HTTPException(status_code=401, detail="Sesión cerrada: vuelve a ingresar")
    return usuario


def rol_principal(usuario: Usuario) -> RolNombre:
    """Rol con el que se filtra lo que ve un usuario con varios: UTP > PROFESOR > ALUMNO.
    Es el mismo orden que usa el frontend para elegir la vista."""
    roles = {r.rol for r in usuario.roles}
    for rol in (RolNombre.UTP, RolNombre.PROFESOR):
        if rol in roles:
            return rol
    return RolNombre.ALUMNO


def requiere_rol(*roles_permitidos: RolNombre):
    def _verificar(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        roles_usuario = {r.rol for r in usuario.roles}
        if not roles_usuario & set(roles_permitidos):
            raise HTTPException(status_code=403, detail="No tienes permiso para esta acción")
        return usuario

    return _verificar
