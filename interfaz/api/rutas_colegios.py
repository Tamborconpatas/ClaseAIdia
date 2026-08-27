from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Colegio
from interfaz.api.esquemas import ColegioCrear, ColegioOut

router = APIRouter(prefix="/colegios", tags=["colegios"])


@router.post("", response_model=ColegioOut, status_code=201)
def crear_colegio(datos: ColegioCrear, db: Session = Depends(obtener_db)):
    colegio = Colegio(nombre=datos.nombre)
    db.add(colegio)
    db.commit()
    db.refresh(colegio)
    return colegio


@router.get("", response_model=list[ColegioOut])
def listar_colegios(db: Session = Depends(obtener_db)):
    return db.query(Colegio).all()


@router.get("/{colegio_id}", response_model=ColegioOut)
def obtener_colegio(colegio_id: int, db: Session = Depends(obtener_db)):
    colegio = db.get(Colegio, colegio_id)
    if colegio is None:
        raise HTTPException(status_code=404, detail="Colegio no encontrado")
    return colegio
