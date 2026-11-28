# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Cierre del año escolar (solo el UTP), en dos tiempos: cerrar el año al terminar las clases y preparar el año nuevo (qué pasa con los alumnos) cuando las
grabaciones están por activarse de nuevo, porque los alumnos cambian de curso en febrero."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Colegio, RolNombre, Usuario
from interfaz.api.dependencias_auth import requiere_rol
from interfaz.api.esquemas import (
    CierreAnioNuevoConfirmarIn, CierreAnioNuevoOut, CierreConfirmarIn, CierreEstadoOut, CierreHechoOut, CierrePlanIn, CierreVistaPreviaOut,
)
from servicios import servicio_ajustes, servicio_cierre_anio as sc, servicio_respaldo

router = APIRouter(prefix="/cierre-anio", tags=["cierre del año"])
utp_actual = requiere_rol(RolNombre.UTP)


def _base() -> Path | None:
    """El archivo de la base, para el respaldo previo (None si no es un archivo SQLite)."""
    from infraestructura.basedatos import engine

    return Path(engine.url.database) if engine.url.get_backend_name() == "sqlite" and engine.url.database else None


@router.get("/estado", response_model=CierreEstadoOut)
def ver_estado(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Si el año está cerrado y, si no, cuántas clases se borrarían al cerrarlo (y qué lo impide)."""
    return sc.estado(db, db.get(Colegio, utp.colegio_id))


@router.post("/cerrar", response_model=CierreHechoOut)
def cerrar_anio(datos: CierreConfirmarIn, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Cierra el año al terminar las clases: respaldo aparte, borra todo el material de clases, deja las grabaciones en pausa. Los alumnos siguen donde están."""
    if not datos.confirmo:
        raise HTTPException(status_code=422, detail="Falta confirmar el cierre del año.")
    try:
        r = sc.cerrar_anio(db, db.get(Colegio, utp.colegio_id), _base(), servicio_ajustes.carpeta_de_respaldos(db))
    except sc.ErrorCierre as e:
        raise HTTPException(status_code=409, detail=" ".join(e.problemas)) from e
    servicio_respaldo.compactar(_base())
    return r


@router.post("/anio-nuevo/vista-previa", response_model=CierreVistaPreviaOut)
def vista_previa(plan: CierrePlanIn, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Dice qué pasaría con ese plan para el año nuevo (y qué lo impide) sin cambiar nada."""
    r = sc.calcular(db, db.get(Colegio, utp.colegio_id), plan.model_dump())
    return {k: r[k] for k in ("problemas", "resumen", "cursos")}


@router.post("/anio-nuevo", response_model=CierreAnioNuevoOut)
def preparar_anio_nuevo(datos: CierreAnioNuevoConfirmarIn, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Prepara el año nuevo: pasa a los alumnos de curso, borra las cuentas de quienes egresan o se fueron, cambia los códigos de invitación y reactiva las
    grabaciones. Antes hace un respaldo aparte. No se puede deshacer desde la aplicación."""
    if not datos.confirmo:
        raise HTTPException(status_code=422, detail="Falta confirmar.")
    try:
        r = sc.empezar_anio(db, db.get(Colegio, utp.colegio_id), datos.model_dump(exclude={"confirmo"}), _base(), servicio_ajustes.carpeta_de_respaldos(db))
    except sc.ErrorCierre as e:
        raise HTTPException(status_code=409, detail=" ".join(e.problemas)) from e
    return r
