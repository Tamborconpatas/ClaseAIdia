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
from interfaz.api.esquemas import (
    AjusteClasesEditar, AjusteClasesOut, AjusteConservacionEditar, AjusteConservacionOut, AjusteFotosEditar, AjusteFotosOut, AjusteGrabacionesEditar, AjusteGrabacionesOut, AjusteModeloDescargar, AjusteModeloEditar, AjusteModeloTextoOut,
    AjusteRespaldosEditar, AjusteRespaldosOut,
)
from nucleo import modelos_ia
from nucleo.memoria import memoria_total_gb
from servicios import servicio_ajustes as sa, servicio_conservacion, servicio_modelos, servicio_pizarra, servicio_respaldo

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


def _receso(colegio: Colegio) -> dict:
    return {"activas": sa.grabaciones_activas(colegio), "hasta": colegio.grabaciones_hasta, "anio_cerrado": colegio.anio_cerrado}


def _conservacion(db: Session, colegio: Colegio, consultado: int | None = None) -> dict:
    dias = sa.dias_de_conservacion(colegio) if consultado is None else consultado
    if consultado is not None and not sa.RANGO_DIAS_CONSERVACION[0] <= consultado <= sa.RANGO_DIAS_CONSERVACION[1]:
        raise sa.ErrorAjuste(f"Plazo de conservación: escribe un número entero de {sa.RANGO_DIAS_CONSERVACION[0]} a {sa.RANGO_DIAS_CONSERVACION[1]} días.")
    return {
        "dias": sa.dias_de_conservacion(colegio), "dias_por_defecto": sa.DIAS_CONSERVACION_POR_DEFECTO, "rango_dias": list(sa.RANGO_DIAS_CONSERVACION),
        "se_borrarian": servicio_conservacion.contar_vencidas(db, colegio, dias),
    }


@router.get("/grabaciones", response_model=AjusteGrabacionesOut)
def ver_grabaciones(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    return _receso(db.get(Colegio, utp.colegio_id))


@router.put("/grabaciones", response_model=AjusteGrabacionesOut)
def cambiar_grabaciones(datos: AjusteGrabacionesEditar, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Receso del colegio (fin de clases o vacaciones): apaga o enciende el empezar a grabar. Lo ya grabado se procesa igual."""
    colegio = db.get(Colegio, utp.colegio_id)
    sa.cambiar_grabaciones(db, colegio, datos.activas, datos.hasta)
    return _receso(colegio)


@router.get("/conservacion", response_model=AjusteConservacionOut)
def ver_conservacion(dias: int | None = None, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """El plazo de este colegio. Con `dias`, dice cuántas clases se borrarían con ese plazo (vista previa antes de guardarlo)."""
    return _conservacion(db, db.get(Colegio, utp.colegio_id), dias)


@router.put("/conservacion", response_model=AjusteConservacionOut)
def cambiar_conservacion(datos: AjusteConservacionEditar, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Cuántos días se guarda el material de cada clase de este colegio (`null` = un año). Un plazo más corto borra al instante, y sin vuelta
    atrás, lo que ya lo pasó (la respuesta dice cuántas clases se borraron)."""
    colegio = db.get(Colegio, utp.colegio_id)
    sa.cambiar_conservacion(db, colegio, datos.dias)
    borradas = servicio_conservacion.borrar_vencidas(db, solo=colegio)
    return {**_conservacion(db, colegio), "borradas": borradas}


@router.post("/fotos-pizarra/modelo", response_model=AjusteFotosOut)
def descargar_modelo(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Baja el modelo de lectura de imágenes (necesita internet una vez). Se consulta el avance con el GET."""
    url, modelo = servicio_pizarra.url_ollama(), servicio_pizarra.MODELO_VISION
    esta = servicio_modelos.instalado(modelo, url)  # una sola pregunta a Ollama por pedido
    servicio_modelos.iniciar_descarga(modelo, url, ya_esta=bool(esta))
    return _estado_fotos(db, utp, esta=bool(esta) if esta is not None else None)


def _estado_texto(db: Session, nombres: set[str] | None) -> dict:
    """`nombres`: los modelos que tiene Ollama (None si no responde). Una sola pregunta a Ollama alcanza para todas las filas."""
    modelo = modelos_ia.modelo_a_instalar(sa.modelo_de_resumen(db))
    esta = lambda m: None if nombres is None else servicio_modelos.esta_en(m, nombres)  # noqa: E731
    total = memoria_total_gb()
    return {
        "modelo": modelo,
        "ollama_responde": nombres is not None,
        "modelo_instalado": bool(esta(modelo)),
        "memoria_total_gb": round(total, 1) if total else None,
        "memoria_minima_gb": modelos_ia.MEMORIA_MINIMA_GB,
        "tamano_gb": modelos_ia.TAMANO_GB.get(modelo),
        "descarga": servicio_modelos.estado_de_descarga(modelo),
        "eleccion": sa.modelo_elegido(db) or "auto",
        "opciones": [
            {"modelo": m, "etiqueta": etiqueta, "nota": nota, "tamano_gb": modelos_ia.TAMANO_GB.get(m), "instalado": esta(m), "descarga": servicio_modelos.estado_de_descarga(m)}
            for m, etiqueta, nota in modelos_ia.ELEGIBLES
        ],
    }


@router.get("/modelo-texto", response_model=AjusteModeloTextoOut)
def ver_modelo_texto(db: Session = Depends(obtener_db), _: Usuario = Depends(utp_actual)):
    return _estado_texto(db, servicio_modelos.modelos_instalados(servicio_pizarra.url_ollama()))


@router.put("/modelo-texto", response_model=AjusteModeloTextoOut)
def elegir_modelo_texto(datos: AjusteModeloEditar, db: Session = Depends(obtener_db), _: Usuario = Depends(utp_actual)):
    """Qué modelo escribe los resúmenes: uno de los que la aplicación ofrece, o `auto` para que decida sola. Solo se puede elegir uno que ya esté
    descargado. Vale desde la próxima clase que se procese (la que está en marcha termina con el que empezó)."""
    nombres = servicio_modelos.modelos_instalados(servicio_pizarra.url_ollama())
    instalado = None if nombres is None else servicio_modelos.esta_en(datos.modelo, nombres)
    sa.cambiar_modelo_de_resumen(db, datos.modelo, instalado)
    return _estado_texto(db, nombres)


@router.post("/modelo-texto/descargar", response_model=AjusteModeloTextoOut)
def descargar_modelo_texto(datos: AjusteModeloDescargar | None = None, db: Session = Depends(obtener_db), _: Usuario = Depends(utp_actual)):
    """Baja un modelo (necesita internet una vez): el que se pide, que debe ser de los que la aplicación ofrece, o el que se está usando. Se consulta
    el avance con el GET."""
    url = servicio_pizarra.url_ollama()
    modelo = datos.modelo if datos and datos.modelo else modelos_ia.modelo_a_instalar(sa.modelo_de_resumen(db))
    if modelo not in {m for m, _e, _n in modelos_ia.ELEGIBLES} | {modelos_ia.modelo_a_instalar(sa.modelo_de_resumen(db))}:
        raise sa.ErrorAjuste("Ese modelo no está entre los que la aplicación ofrece.")
    nombres = servicio_modelos.modelos_instalados(url)  # una sola pregunta a Ollama por pedido
    servicio_modelos.iniciar_descarga(modelo, url, ya_esta=bool(nombres is not None and servicio_modelos.esta_en(modelo, nombres)))
    return _estado_texto(db, nombres)


# --- Cómo se tratan las clases (por colegio) y el respaldo diario (de todo el servidor) ---


def _clases(colegio: Colegio) -> dict:
    return {
        "horas_revision": sa.horas_de_revision(colegio), "minutos_corte": sa.minutos_de_corte(colegio),
        "horas_revision_por_defecto": sa.HORAS_REVISION_POR_DEFECTO, "minutos_corte_por_defecto": sa.MINUTOS_CORTE_POR_DEFECTO,
        "rango_horas_revision": list(sa.RANGO_HORAS_REVISION), "rango_minutos_corte": list(sa.RANGO_MINUTOS_CORTE),
    }


@router.get("/clases", response_model=AjusteClasesOut)
def ver_clases(db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    return _clases(db.get(Colegio, utp.colegio_id))


@router.put("/clases", response_model=AjusteClasesOut)
def cambiar_clases(datos: AjusteClasesEditar, db: Session = Depends(obtener_db), utp: Usuario = Depends(utp_actual)):
    """Plazo de revisión del profesor y minutos del corte automático, de este colegio. `null` = el valor predeterminado. Vale de inmediato."""
    colegio = db.get(Colegio, utp.colegio_id)
    sa.cambiar_ajustes_del_colegio(db, colegio, datos.horas_revision, datos.minutos_corte)
    return _clases(colegio)


def _respaldos(db: Session) -> dict:
    return {
        "carpeta": str(sa.carpeta_de_respaldos(db).resolve()), "carpeta_por_defecto": str(servicio_respaldo.carpeta_de_respaldos().resolve()),
        "dias": sa.dias_de_respaldo(db), "dias_por_defecto": sa.DIAS_RESPALDO_POR_DEFECTO, "rango_dias": list(sa.RANGO_DIAS_RESPALDO),
    }


@router.get("/respaldos", response_model=AjusteRespaldosOut)
def ver_respaldos(db: Session = Depends(obtener_db), _: Usuario = Depends(utp_actual)):
    return _respaldos(db)


@router.put("/respaldos", response_model=AjusteRespaldosOut)
def cambiar_respaldos(datos: AjusteRespaldosEditar, db: Session = Depends(obtener_db), _: Usuario = Depends(utp_actual)):
    """Carpeta y días del respaldo diario. Vale para todo el servidor (la base es una sola) desde el próximo respaldo. La carpeta se prueba
    escribiendo en ella antes de guardar. `null` = el valor predeterminado."""
    sa.cambiar_ajustes_de_respaldo(db, datos.carpeta, datos.dias)
    return _respaldos(db)
