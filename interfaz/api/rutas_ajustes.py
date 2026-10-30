# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Ajustes del colegio que decide el UTP desde la aplicación (la app se reparte portable: nadie edita archivos ni corre comandos)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import Colegio, RolNombre, Usuario
from interfaz.api.dependencias_auth import requiere_rol
from interfaz.api.esquemas import AjusteFotosEditar, AjusteFotosOut
from nucleo.memoria import memoria_total_gb
from servicios import servicio_modelos, servicio_pizarra

router = APIRouter(prefix="/ajustes", tags=["ajustes"])
utp_actual = requiere_rol(RolNombre.UTP)


_SIN_DATO = object()


def _estado_fotos(db: Session, utp: Usuario, esta: object = _SIN_DATO) -> dict:
    """`esta`: si ya se le preguntó a Ollama en este pedido (True/False/None = no responde); sin dato, se le pregunta aquí."""
    colegio = db.get(Colegio, utp.colegio_id)
    url, modelo = servicio_pizarra.url_ollama(), servicio_pizarra.MODELO_VISION
    if esta is _SIN_DATO:
        esta = servicio_modelos.instalado(modelo, url)  # None = Ollama no responde
    total = memoria_total_gb()
    return {
        "activada": servicio_pizarra.activadas(colegio),
        "modelo": modelo,
        "ollama_responde": esta is not None,
        "modelo_instalado": bool(esta),
        "memoria_total_gb": round(total, 1) if total else None,
        "memoria_recomendada_gb": servicio_pizarra.MEMORIA_RECOMENDADA_GB,
        "descarga": servicio_modelos.estado_de_descarga(modelo),
    }


@router.get("/fotos-pizarra", response_model=AjusteFotosOut)
def ver_fotos(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    return _estado_fotos(db, utp)


@router.put("/fotos-pizarra", response_model=AjusteFotosOut)
def cambiar_fotos(datos: AjusteFotosEditar, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Activa o desactiva las fotos de la pizarra para todo el colegio. Las ya sacadas se procesan igual; desde ahora no se aceptan más."""
    db.get(Colegio, utp.colegio_id).fotos_pizarra = datos.activada
    db.commit()
    return _estado_fotos(db, utp)


@router.post("/fotos-pizarra/modelo", response_model=AjusteFotosOut)
def descargar_modelo(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Baja el modelo de lectura de imágenes (necesita internet una vez). Se consulta el avance con el GET."""
    url, modelo = servicio_pizarra.url_ollama(), servicio_pizarra.MODELO_VISION
    esta = servicio_modelos.instalado(modelo, url)  # una sola pregunta a Ollama por pedido
    servicio_modelos.iniciar_descarga(modelo, url, ya_esta=bool(esta))
    return _estado_fotos(db, utp, esta=bool(esta) if esta is not None else None)
