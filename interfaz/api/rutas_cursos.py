# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import AlumnoCurso, Bloque, Curso, RolNombre, Usuario, UsuarioRol
from infraestructura.seguridad import hashear_secreto, verificar_secreto
from interfaz.api.dependencias_auth import emitir_token, requiere_rol, rol_principal, usuario_actual
from interfaz.api.esquemas import (
    AlumnoMoverIn,
    BloqueCrear,
    BloqueOut,
    AlumnoOut,
    CodigoCursoOut,
    CursoConCodigoOut,
    CursoCupoIn,
    CursoCrear,
    CursoOut,
    CursoRenombrar,
    TokenOut,
    UnirseCursoIn,
    pin_es_facil,
)
from interfaz.api.rutas_auth import registrar_resultado_intento, verificar_bloqueo
from interfaz.api.rutas_bloques import verificar_bloque
from nucleo.codigos import generar_codigo_invitacion
from nucleo.nombres import suena_a_broma
from servicios import servicio_conexiones

router = APIRouter(prefix="/cursos", tags=["cursos"])


def _obtener_curso_o_404(curso_id: int, db: Session) -> Curso:
    curso = db.get(Curso, curso_id)
    if curso is None:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return curso


def _curso_visible_o_404(curso_id: int, usuario: Usuario, db: Session) -> Curso:
    """UTP: los cursos de su colegio. Profesor: aquellos donde dicta alguna clase. Alumno: aquellos
    en que está inscrito. 404 en todos los casos: no revela si el id existe."""
    curso = db.get(Curso, curso_id)
    if curso is None or curso.colegio_id != usuario.colegio_id:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    rol = rol_principal(usuario)
    if rol == RolNombre.PROFESOR:
        permitido = db.query(Bloque.id).filter_by(curso_id=curso.id, profesor_id=usuario.id).first()
    elif rol == RolNombre.ALUMNO:
        permitido = db.query(AlumnoCurso.id).filter_by(usuario_id=usuario.id, curso_id=curso.id).first()
    else:
        permitido = True
    if not permitido:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    return curso


@router.post("", response_model=CursoConCodigoOut, status_code=201)
def crear_curso(
    datos: CursoCrear, db: Session = Depends(obtener_db), _utp: Usuario = Depends(requiere_rol(RolNombre.UTP))
):
    if datos.colegio_id != _utp.colegio_id:
        raise HTTPException(status_code=403, detail="Solo puedes crear cursos en tu propio colegio")

    codigo = generar_codigo_invitacion()
    while db.query(Curso).filter_by(codigo_invitacion=codigo).first() is not None:
        codigo = generar_codigo_invitacion()

    curso = Curso(nombre=datos.nombre, colegio_id=datos.colegio_id, codigo_invitacion=codigo)
    db.add(curso)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="colegio_id inexistente") from e
    db.refresh(curso)
    return curso


@router.get("", response_model=list[CursoOut])
def listar_cursos(db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    consulta = db.query(Curso).filter_by(colegio_id=actual.colegio_id)
    rol = rol_principal(actual)
    if rol == RolNombre.PROFESOR:
        consulta = consulta.filter(Curso.id.in_(select(Bloque.curso_id).where(Bloque.profesor_id == actual.id)))
    elif rol == RolNombre.ALUMNO:
        consulta = consulta.join(AlumnoCurso).filter(AlumnoCurso.usuario_id == actual.id)
    return consulta.all()


@router.post("/unirse", response_model=TokenOut)
def unirse_curso(datos: UnirseCursoIn, request: Request, db: Session = Depends(obtener_db)):
    curso = db.query(Curso).filter_by(codigo_invitacion=datos.codigo_invitacion).first()
    if curso is None:
        raise HTTPException(status_code=404, detail="Código de invitación inválido")

    usuario = db.query(Usuario).filter_by(rut=datos.rut).first()
    if usuario is None:
        if pin_es_facil(datos.pin):
            raise HTTPException(status_code=422, detail="PIN demasiado fácil de adivinar (repetido o secuencia)")
        broma = suena_a_broma(datos.nombre)
        if broma and not datos.confirmar_nombre:
            # No se bloquea (alguien puede llamarse así de verdad): se pide confirmar y, si confirma, el profesor lo ve marcado.
            raise HTTPException(status_code=428, detail="El nombre necesita confirmación")
        usuario = Usuario(
            rut=datos.rut,
            nombre=datos.nombre,
            colegio_id=curso.colegio_id,
            pin_hash=hashear_secreto(datos.pin),
            revisar_nombre=broma,
        )
        if broma:  # solo si el nombre quedó para revisar: desde qué equipo se creó la cuenta (se borra al revisarlo)
            equipo = servicio_conexiones.dispositivo_de(db, curso.colegio_id, request)
            usuario.registro_dispositivo_id = equipo.id if equipo else None
        usuario.roles = [UsuarioRol(rol=RolNombre.ALUMNO)]
        db.add(usuario)
        db.flush()
    else:
        # Una cuenta de staff no se convierte en alumno por esta vía: si no, bastaría
        # un código de invitación + el RUT de un UTP para fijarle PIN y entrar como él.
        if RolNombre.ALUMNO not in {r.rol for r in usuario.roles}:
            raise HTTPException(status_code=409, detail="Este RUT pertenece a una cuenta de personal del colegio")

        # Sin PIN = reseteado por staff: se restablece solo con el código de un solo
        # uso (/auth/restablecer-pin), no con el código del curso, que conoce todo el curso.
        if usuario.pin_hash is None:
            raise HTTPException(status_code=409, detail="PIN reseteado: usa el código que te dio tu profesor")

        # Mismo límite de intentos que /auth/login/alumno — si no, esta ruta
        # serviría para adivinar el PIN sin bloqueo.
        verificar_bloqueo(usuario)
        if not verificar_secreto(datos.pin, usuario.pin_hash):
            registrar_resultado_intento(usuario, exitoso=False, db=db)
            raise HTTPException(status_code=401, detail="PIN incorrecto para este RUT")
        registrar_resultado_intento(usuario, exitoso=True, db=db)

    _exigir_sin_otro_curso(db, usuario.id, curso.id)
    ya_inscrito = db.query(AlumnoCurso).filter_by(usuario_id=usuario.id, curso_id=curso.id).first()
    if ya_inscrito is None:
        _exigir_cupo(db, curso)
        db.add(AlumnoCurso(usuario_id=usuario.id, curso_id=curso.id))

    usuario.version_sesion += 1  # una sola sesión por alumno: la del equipo anterior se cierra
    db.commit()
    db.refresh(usuario)
    return emitir_token(usuario)


@router.get("/{curso_id}", response_model=CursoOut)
def obtener_curso(curso_id: int, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    return _curso_visible_o_404(curso_id, actual, db)


@router.put("/{curso_id}", response_model=CursoOut)
def renombrar_curso(
    curso_id: int,
    datos: CursoRenombrar,
    db: Session = Depends(obtener_db),
    utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    curso = _curso_visible_o_404(curso_id, utp, db)
    curso.nombre = datos.nombre
    db.commit()
    db.refresh(curso)
    return curso


@router.put("/{curso_id}/cupo", response_model=CursoOut)
def fijar_cupo(
    curso_id: int,
    datos: CursoCupoIn,
    db: Session = Depends(obtener_db),
    utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    """El UTP fija cuántos alumnos admite el curso. No puede quedar bajo los que ya tiene: primero se mueven."""
    curso = _curso_visible_o_404(curso_id, utp, db)
    inscritos = db.query(AlumnoCurso.id).filter_by(curso_id=curso.id).count()
    if datos.cupo < inscritos:
        raise HTTPException(status_code=409, detail=f"El curso ya tiene {inscritos} alumnos: mueve o saca a algunos antes de bajar el máximo")
    curso.cupo = datos.cupo
    db.commit()
    db.refresh(curso)
    return curso


@router.delete("/{curso_id}", status_code=204)
def borrar_curso(
    curso_id: int, db: Session = Depends(obtener_db), utp: Usuario = Depends(requiere_rol(RolNombre.UTP))
):
    """Solo un curso vacío: el borrado en cascada se llevaría su horario, sus clases y su material."""
    curso = _curso_visible_o_404(curso_id, utp, db)
    if db.query(Bloque.id).filter_by(curso_id=curso.id).first() is not None:
        raise HTTPException(status_code=409, detail="El curso todavía tiene bloques en su horario: elimínalos primero")
    if db.query(AlumnoCurso.id).filter_by(curso_id=curso.id).first() is not None:
        raise HTTPException(status_code=409, detail="El curso todavía tiene alumnos inscritos")
    db.delete(curso)
    db.commit()


@router.get("/{curso_id}/alumnos", response_model=list[AlumnoOut])
def alumnos_del_curso(
    curso_id: int,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Los alumnos inscritos, para que el profesor (de ese curso) o el UTP les resetee el PIN."""
    curso = _curso_visible_o_404(curso_id, staff, db)
    return (
        db.query(Usuario)
        .join(AlumnoCurso, AlumnoCurso.usuario_id == Usuario.id)
        .filter(AlumnoCurso.curso_id == curso.id)
        .order_by(Usuario.nombre)
        .all()
    )


def _exigir_sin_otro_curso(db: Session, usuario_id: int, curso_id: int) -> None:
    """Un RUT está en un solo curso: para cambiarlo de sección el UTP lo mueve."""
    otro = db.query(Curso.nombre).join(AlumnoCurso).filter(AlumnoCurso.usuario_id == usuario_id, Curso.id != curso_id).first()
    if otro is not None:
        raise HTTPException(status_code=409, detail=f"Este RUT ya está en el curso {otro[0]}: pídele al UTP que lo mueva")


def _exigir_cupo(db: Session, curso: Curso) -> None:
    if db.query(AlumnoCurso.id).filter_by(curso_id=curso.id).count() >= curso.cupo:
        raise HTTPException(status_code=409, detail=f"El curso {curso.nombre} está lleno ({curso.cupo} alumnos): avisa a tu UTP")


def _alumno_inscrito_o_404(curso: Curso, usuario_id: int, db: Session) -> AlumnoCurso:
    inscripcion = db.query(AlumnoCurso).filter_by(curso_id=curso.id, usuario_id=usuario_id).first()
    if inscripcion is None:
        raise HTTPException(status_code=404, detail="Ese alumno no está en este curso")
    return inscripcion


@router.delete("/{curso_id}/alumnos/{usuario_id}", status_code=204)
def quitar_alumno(
    curso_id: int, usuario_id: int, db: Session = Depends(obtener_db), utp: Usuario = Depends(requiere_rol(RolNombre.UTP))
):
    """Lo saca del curso (su cuenta se conserva); deja de ver sus clases."""
    curso = _curso_visible_o_404(curso_id, utp, db)
    db.delete(_alumno_inscrito_o_404(curso, usuario_id, db))
    db.commit()


@router.post("/{curso_id}/alumnos/{usuario_id}/mover", status_code=204)
def mover_alumno(
    curso_id: int,
    usuario_id: int,
    datos: AlumnoMoverIn,
    db: Session = Depends(obtener_db),
    utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    """Pasa al alumno a otro curso (p. ej. cambio de sección) en un solo paso."""
    origen = _curso_visible_o_404(curso_id, utp, db)
    destino = _curso_visible_o_404(datos.curso_destino_id, utp, db)
    inscripcion = _alumno_inscrito_o_404(origen, usuario_id, db)
    if destino.id == origen.id:
        raise HTTPException(status_code=409, detail="El curso de destino es el mismo")
    _exigir_cupo(db, destino)
    inscripcion.curso_id = destino.id
    db.commit()


@router.get("/{curso_id}/codigo", response_model=CodigoCursoOut)
def codigo_curso(
    curso_id: int,
    db: Session = Depends(obtener_db),
    staff: Usuario = Depends(requiere_rol(RolNombre.PROFESOR, RolNombre.UTP)),
):
    """Para mostrar el código/QR del curso en clase: solo staff de ese colegio."""
    return _curso_visible_o_404(curso_id, staff, db)


@router.post("/{curso_id}/bloques", response_model=BloqueOut, status_code=201)
def crear_bloque(
    curso_id: int,
    datos: BloqueCrear,
    db: Session = Depends(obtener_db),
    _utp: Usuario = Depends(requiere_rol(RolNombre.UTP)),
):
    curso = _obtener_curso_o_404(curso_id, db)
    if curso.colegio_id != _utp.colegio_id:
        raise HTTPException(status_code=403, detail="Solo puedes crear bloques en cursos de tu propio colegio")
    verificar_bloque(db, _utp, curso, datos)

    bloque = Bloque(curso_id=curso_id, **datos.model_dump())
    db.add(bloque)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail="profesor_id inexistente") from e
    db.refresh(bloque)
    return bloque


@router.get("/{curso_id}/bloques", response_model=list[BloqueOut])
def listar_bloques(curso_id: int, db: Session = Depends(obtener_db), actual: Usuario = Depends(usuario_actual)):
    _curso_visible_o_404(curso_id, actual, db)
    return db.query(Bloque).options(selectinload(Bloque.profesor)).filter_by(curso_id=curso_id).all()
