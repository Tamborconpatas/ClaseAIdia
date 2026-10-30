# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Colegio, Usuario
from interfaz.api.dependencias_auth import usuario_actual
from interfaz.api.esquemas import ColegioOut

router = APIRouter(prefix="/colegios", tags=["colegios"])


# El colegio se crea una sola vez en POST /auth/setup; acá solo se lee el propio.
@router.get("/{colegio_id}", response_model=ColegioOut)
def obtener_colegio(colegio_id: int, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    # 404 también si es de otro colegio: no revela si el id existe.
    if colegio_id != actual.colegio_id:
        raise HTTPException(status_code=404, detail="Colegio no encontrado")
    return db.get(Colegio, colegio_id)
