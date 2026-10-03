"""Panel de estado del servidor: solo el UTP, y solo lo de su colegio."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import RolNombre, Usuario
from interfaz.api.dependencias_auth import requiere_rol
from interfaz.api.esquemas import EstadoServidorOut
from servicios import servicio_estado

router = APIRouter(prefix="/estado", tags=["estado"])
utp_actual = requiere_rol(RolNombre.UTP)


@router.get("", response_model=EstadoServidorOut)
def ver_estado(request: Request, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    return servicio_estado.estado_del_servidor(db, utp.colegio_id, vigilando=request.app.state.vigilando)
