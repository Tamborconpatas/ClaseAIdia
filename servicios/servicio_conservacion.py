# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Cuánto tiempo se guarda el material de una clase. Pasado el plazo del colegio (un año por defecto, de 90 a 730 días) de la fecha de la clase se borra todo lo que quedó de ella
(transcripción, resumen, puntos clave, hoja de repaso, tarjetas, mapa y texto de la pizarra): el año escolar siguiente empieza de cero y el
colegio no acumula para siempre texto de clases donde puede salir la voz de menores (privacidad: guardar solo lo necesario, solo el tiempo necesario).
El horario (cursos y bloques) no se toca: solo las clases ya dictadas.
"""
import datetime
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from infraestructura.modelos_orm import Bloque, Clase, Colegio, Curso, EstadoGrabacion as E, Grabacion
from infraestructura.seguridad import ahora_utc
from servicios import servicio_ajustes

log = logging.getLogger(__name__)

LOTE = 200  # clases por tanda: cada tanda se confirma sola, así la base nunca queda bloqueada borrando un año entero de golpe
_EN_CURSO = (E.ESPERANDO, E.GRABANDO, E.PAUSADA, E.TERMINANDO, E.PROCESANDO)
ultima_limpieza: datetime.datetime | None = None


def _vencidas(db: Session, colegio_id: int, dias: int, hoy: datetime.date):
    """Las clases de ese colegio con más de `dias` días, menos las que aún se graban o se procesan."""
    limite = hoy - datetime.timedelta(days=dias)
    en_curso = db.query(Grabacion.clase_id).filter(Grabacion.estado.in_(_EN_CURSO))
    return (
        db.query(Clase).join(Bloque, Clase.bloque_id == Bloque.id).join(Curso, Bloque.curso_id == Curso.id)
        .filter(Curso.colegio_id == colegio_id, Clase.fecha < limite, Clase.id.not_in(en_curso))
    )


def contar_vencidas(db: Session, colegio: Colegio, dias: int, hoy: datetime.date | None = None) -> int:
    """Cuántas clases se borrarían con ese plazo (el UTP lo ve antes de guardar un plazo más corto)."""
    consulta = _vencidas(db, colegio.id, dias, hoy or datetime.date.today())
    return consulta.with_entities(func.count(Clase.id)).scalar() or 0


def borrar_vencidas(db: Session, hoy: datetime.date | None = None, solo: Colegio | None = None) -> int:
    """Borra, colegio por colegio y según el plazo de cada uno, las clases vencidas con todo su material (en cascada: contenido, grabación
    y fotos). Una clase que aún se graba o se procesa nunca se borra. `solo`: únicamente ese colegio (cuando su UTP acorta el plazo). Devuelve cuántas."""
    from servicios import servicio_grabacion  # import tardío: ese módulo importa este

    hoy = hoy or datetime.date.today()  # la fecha de las clases es la del reloj local del servidor
    total = 0
    for colegio in [solo] if solo is not None else db.query(Colegio).all():
        dias = servicio_ajustes.dias_de_conservacion(colegio)
        while lote := _vencidas(db, colegio.id, dias, hoy).limit(LOTE).all():
            for clase in lote:
                if clase.grabacion is not None:
                    servicio_grabacion.olvidar_archivos(clase.grabacion.id)
                db.delete(clase)
            db.commit()
            total += len(lote)
    if total:
        log.info("Se borraron %d clases que pasaron su plazo de conservación", total)
    return total


def limpiar_si_toca(db: Session, ahora: datetime.datetime | None = None) -> None:
    """La vigilancia lo llama en cada pasada; el borrado real corre como mucho una vez al día."""
    global ultima_limpieza
    ahora = ahora or ahora_utc()
    if ultima_limpieza is None or (ahora - ultima_limpieza).total_seconds() >= 86400:
        borrar_vencidas(db)
        ultima_limpieza = ahora
