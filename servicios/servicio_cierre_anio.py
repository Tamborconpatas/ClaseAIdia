# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Cierre del año escolar, en dos tiempos, porque los alumnos cambian de curso en febrero, antes de que empiecen las clases, y no en diciembre:

1. **Cerrar el año** (al terminar las clases): se borra todo el material de clases del año (el «8.°A» de la generación siguiente no debe ver las clases de la
   anterior), las grabaciones quedan en pausa y el año queda marcado como cerrado. **Los alumnos siguen donde están**: no se les pregunta nada todavía.
2. **Preparar el año nuevo** (cuando las grabaciones están por activarse de nuevo): ahí el UTP decide qué pasa con los alumnos. Cada curso pasa a otro (que ya
   existe o se crea) o egresa; cada alumno **pasa**, **repite** (se queda donde está) o **se fue** del colegio. Se borran las cuentas de quienes egresan o
   se fueron (privacidad: no se guarda el dato de un menor que ya no es del colegio), todos los cursos reciben un código de invitación nuevo y las
   grabaciones se reactivan. Con el año cerrado no se pueden reactivar de otra forma.

El horario (cursos y bloques) se conserva siempre: el UTP lo ajusta con la grilla de siempre. Antes de cada paso que borra se hace un respaldo aparte de la base,
que no se borra solo. Nada se hace a medias: primero se valida todo (`calcular`) y solo si no hay problemas se aplica.
"""
import datetime
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from infraestructura.modelos_orm import AlumnoCurso, Bloque, Clase, Colegio, Curso, EstadoGrabacion as E, Grabacion, RolNombre, Usuario
from nucleo.codigos import generar_codigo_invitacion
from servicios import servicio_ajustes, servicio_grabacion as sg, servicio_respaldo

LOTE = 200  # clases por tanda al borrar: la memoria no crece con el año (cada clase trae su transcripción)
CUPO_CURSO_NUEVO = 45
_EN_CURSO = (E.ESPERANDO, E.GRABANDO, E.PAUSADA, E.TERMINANDO, E.PROCESANDO)


class ErrorCierre(Exception):
    """El paso no se puede hacer (o el plan está mal): se explica en palabras de persona (se responde 409)."""

    def __init__(self, problemas: list[str]):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


def _clases_del_colegio(db: Session, colegio_id: int):
    return db.query(Clase).join(Bloque, Clase.bloque_id == Bloque.id).join(Curso, Bloque.curso_id == Curso.id).filter(Curso.colegio_id == colegio_id)


def _en_marcha(db: Session, colegio_id: int) -> int:
    return (
        db.query(Grabacion).join(Clase).join(Bloque, Clase.bloque_id == Bloque.id).join(Curso, Bloque.curso_id == Curso.id)
        .filter(Curso.colegio_id == colegio_id, Grabacion.estado.in_(_EN_CURSO)).count()
    )


def _es_alumno(u: Usuario) -> bool:
    return {r.rol for r in u.roles} == {RolNombre.ALUMNO}


def _codigo_libre(db: Session) -> str:
    codigo = generar_codigo_invitacion()
    while db.query(Curso).filter_by(codigo_invitacion=codigo).first() is not None:
        codigo = generar_codigo_invitacion()
    return codigo


# --- 1. Cerrar el año -------------------------------------------------------------------------------------------------


def estado(db: Session, colegio: Colegio) -> dict:
    """Lo que el UTP ve antes de cerrar el año: cuántas clases se borrarían y si algo lo impide."""
    problemas = []
    if colegio.anio_cerrado:
        problemas.append("El año ya está cerrado: lo que falta es preparar el año nuevo.")
    en_marcha = _en_marcha(db, colegio.id)
    if en_marcha:
        problemas.append(f"Hay {en_marcha} {'clase grabándose o procesándose' if en_marcha == 1 else 'clases grabándose o procesándose'}: espera a que terminen para cerrar el año.")
    return {"anio_cerrado": colegio.anio_cerrado, "clases_a_borrar": _clases_del_colegio(db, colegio.id).count(), "problemas": problemas}


def _borrar_clases(db: Session, colegio_id: int) -> int:
    """Todo el material del año, en tandas (cada una se confirma sola: no se arma en memoria un año entero de transcripciones)."""
    total = 0
    while lote := _clases_del_colegio(db, colegio_id).limit(LOTE).all():
        for c in lote:
            if c.grabacion is not None:
                sg.olvidar_archivos(c.grabacion.id)  # un reintento pendiente guarda audio en disco: no debe sobrevivir a la clase
            db.delete(c)
        db.commit()
        total += len(lote)
    return total


def cerrar_anio(db: Session, colegio: Colegio, origen_base: Path | None, carpeta_respaldos: Path, ahora: datetime.datetime | None = None) -> dict:
    """Respaldo aparte, borra todo el material de clases, deja las grabaciones en pausa y marca el año como cerrado. Los alumnos no se tocan."""
    ahora = ahora or datetime.datetime.now()
    e = estado(db, colegio)
    if e["problemas"]:
        raise ErrorCierre(e["problemas"])
    respaldo = servicio_respaldo.respaldar_antes_del_cierre(origen_base, carpeta_respaldos, ahora) if origen_base is not None else None
    borradas = _borrar_clases(db, colegio.id)
    colegio.anio_cerrado = True
    servicio_ajustes.cambiar_grabaciones(db, colegio, False)  # confirma el marcado de cierre y la pausa juntos
    return {"clases_borradas": borradas, "respaldo": respaldo.name if respaldo else None}


# --- 2. Preparar el año nuevo -----------------------------------------------------------------------------------------


def calcular(db: Session, colegio: Colegio, plan: dict) -> dict:
    """Valida el plan y dice qué pasaría, sin cambiar nada. `plan`: {cursos: [{curso_id, destino_id | destino_nuevo | egresa}], repiten: [usuario_id], se_van: [usuario_id]}.
    Devuelve {problemas, resumen, cursos}; con problemas no se puede aplicar."""
    problemas: list[str] = []
    if not colegio.anio_cerrado:
        problemas.append("Primero hay que cerrar el año (al terminar las clases): ahí se borran las clases del año y las grabaciones quedan en pausa.")
    cursos = {c.id: c for c in db.query(Curso).filter_by(colegio_id=colegio.id).all()}
    inscripciones = db.query(AlumnoCurso).filter(AlumnoCurso.curso_id.in_(cursos)).all() if cursos else []
    por_curso: dict[int, list[AlumnoCurso]] = {}
    for i in inscripciones:
        por_curso.setdefault(i.curso_id, []).append(i)

    # --- el plan de cada curso
    decisiones: dict[int, dict] = {}
    for p in plan.get("cursos", []):
        cid = p["curso_id"]
        if cid not in cursos:
            problemas.append("Hay un curso en el plan que no es de este colegio.")
            continue
        if cid in decisiones:
            problemas.append(f"El curso {cursos[cid].nombre} aparece dos veces en el plan.")
            continue
        elegidas = [k for k in ("destino_id", "destino_nuevo", "egresa") if p.get(k) not in (None, False, "")]
        if len(elegidas) != 1:
            problemas.append(f"Elige un solo destino para el curso {cursos[cid].nombre}.")
            continue
        if p.get("destino_id") is not None and p["destino_id"] not in cursos:
            problemas.append(f"El curso de destino de {cursos[cid].nombre} no es de este colegio.")
            continue
        if p.get("destino_id") == cid:
            problemas.append(f"El curso {cursos[cid].nombre} no puede pasar a sí mismo: marca a sus alumnos como «repite».")
            continue
        decisiones[cid] = p
    for cid, lista in por_curso.items():
        if cid not in decisiones and lista:
            problemas.append(f"Falta decidir a dónde pasa el curso {cursos[cid].nombre} ({len(lista)} alumnos).")

    # --- los cursos nuevos (por nombre, sin repetir ni chocar con uno existente)
    existentes = {c.nombre.strip().casefold() for c in cursos.values()}
    nuevos: dict[str, str] = {}  # nombre normalizado -> nombre tal como lo escribió el UTP
    for d in decisiones.values():
        if not d.get("destino_nuevo"):
            continue
        nombre = d["destino_nuevo"].strip()
        if not nombre or len(nombre) > 40:
            problemas.append("El nombre de un curso nuevo debe tener de 1 a 40 caracteres.")
        elif nombre.casefold() in existentes:
            problemas.append(f"Ya existe un curso llamado {nombre}: elígelo de la lista en vez de crearlo.")
        else:
            nuevos.setdefault(nombre.casefold(), nombre)

    # --- los alumnos que repiten o se fueron
    repiten, se_van = set(plan.get("repiten", [])), set(plan.get("se_van", []))
    if repiten & se_van:
        problemas.append("Un alumno no puede repetir y a la vez haberse ido del colegio.")
    por_usuario = {i.usuario_id: i for i in inscripciones}
    for uid in repiten | se_van:
        if uid not in por_usuario:
            problemas.append("Hay un alumno marcado que no está en ningún curso de este colegio.")
            break
    for uid in se_van:
        i = por_usuario.get(uid)
        if i is not None and not _es_alumno(i.usuario):
            problemas.append(f"{i.usuario.nombre} no es alumno: solo se borran cuentas de alumnos.")

    # --- dónde queda cada alumno
    final: dict[int, tuple[str, object]] = {}  # inscripción.id -> ("borrar"|"queda"|"curso"|"nuevo", dato)
    for i in inscripciones:
        d = decisiones.get(i.curso_id)
        if i.usuario_id in se_van:
            final[i.id] = ("borrar", "se fue")
        elif i.usuario_id in repiten:
            final[i.id] = ("queda", i.curso_id)
        elif d is None:
            continue
        elif d.get("egresa"):
            final[i.id] = ("borrar", "egresa")
        elif d.get("destino_id") is not None:
            final[i.id] = ("curso", d["destino_id"])
        else:
            final[i.id] = ("nuevo", d["destino_nuevo"].strip().casefold())

    # --- cupos: cuántos quedarían en cada curso
    ocupacion: Counter = Counter()
    for k, dato in final.values():
        if k in ("queda", "curso"):
            ocupacion[dato] += 1
        elif k == "nuevo":
            ocupacion[("nuevo", dato)] += 1
    for cid, n in ocupacion.items():
        if isinstance(cid, int) and n > cursos[cid].cupo:
            problemas.append(f"El curso {cursos[cid].nombre} quedaría con {n} alumnos y su máximo es {cursos[cid].cupo}: sube el máximo en «Alumnos» del curso o reparte a algunos.")
        elif isinstance(cid, tuple) and n > CUPO_CURSO_NUEVO:
            problemas.append(f"El curso nuevo {nuevos.get(cid[1], cid[1])} quedaría con {n} alumnos y el máximo de un curso es {CUPO_CURSO_NUEVO}.")

    resumen = {
        "pasan": sum(1 for k, _ in final.values() if k in ("curso", "nuevo")),
        "repiten": sum(1 for k, _ in final.values() if k == "queda"),
        "se_van": sum(1 for k, m in final.values() if k == "borrar" and m == "se fue"),
        "egresan": sum(1 for k, m in final.values() if k == "borrar" and m == "egresa"),
        "cuentas_a_borrar": sum(1 for k, _ in final.values() if k == "borrar"),
        "cursos_nuevos": sorted(nuevos.values()),
        "codigos_nuevos": len(cursos) + len(nuevos),
    }
    detalle = []
    for cid, c in sorted(cursos.items(), key=lambda kv: kv[1].nombre):
        d = decisiones.get(cid, {})
        destino = "Egresan" if d.get("egresa") else (cursos[d["destino_id"]].nombre if d.get("destino_id") in cursos else (d.get("destino_nuevo") or "").strip() or None)
        detalle.append({"curso_id": cid, "curso": c.nombre, "alumnos": len(por_curso.get(cid, [])), "destino": destino})
    return {"problemas": problemas, "resumen": resumen, "cursos": detalle, "_final": final, "_nuevos": nuevos, "_inscripciones": {i.id: i for i in inscripciones}}


def empezar_anio(db: Session, colegio: Colegio, plan: dict, origen_base: Path | None, carpeta_respaldos: Path, ahora: datetime.datetime | None = None) -> dict:
    """Aplica el plan del año nuevo (todo junto, en una sola transacción) y reactiva las grabaciones. Lanza ErrorCierre si tiene problemas; hace un respaldo aparte
    antes de tocar nada."""
    ahora = ahora or datetime.datetime.now()
    r = calcular(db, colegio, plan)
    if r["problemas"]:
        raise ErrorCierre(r["problemas"])
    respaldo = servicio_respaldo.respaldar_antes_del_cierre(origen_base, carpeta_respaldos, ahora) if origen_base is not None else None

    cursos = {c.id: c for c in db.query(Curso).filter_by(colegio_id=colegio.id).all()}
    for clave, nombre in r["_nuevos"].items():
        c = Curso(nombre=nombre, colegio_id=colegio.id, codigo_invitacion=_codigo_libre(db), cupo=CUPO_CURSO_NUEVO)
        db.add(c)
        db.flush()
        cursos[c.id] = c
        r["_nuevos"][clave] = c.id  # de aquí en adelante: id del curso creado
    for iid, (k, dato) in r["_final"].items():
        i = r["_inscripciones"][iid]
        if k == "borrar":
            db.delete(i.usuario)  # en cascada: su inscripción y sus roles
        elif k == "curso":
            i.curso_id = dato
        elif k == "nuevo":
            i.curso_id = r["_nuevos"][dato]
    for c in cursos.values():
        c.codigo_invitacion = _codigo_libre(db)  # el código viejo ya no sirve: quien se fue no puede volver a entrar con él
    colegio.anio_cerrado = False
    servicio_ajustes.cambiar_grabaciones(db, colegio, True)  # confirma todo junto: ya se puede volver a grabar
    codigos = [{"curso": c.nombre, "codigo": c.codigo_invitacion} for c in sorted(cursos.values(), key=lambda c: c.nombre)]
    return {"resumen": r["resumen"], "respaldo": respaldo.name if respaldo else None, "codigos": codigos}
