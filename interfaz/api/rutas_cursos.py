from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infraestructura.basedatos import obtener_db
from infraestructura.modelos_orm import AlumnoCurso, Bloque, Curso, RolNombre, Usuario, UsuarioRol
from infraestructura.seguridad import hashear_secreto, verificar_secreto
from interfaz.api.dependencias_auth import emitir_token, requiere_rol
from interfaz.api.esquemas import (
    BloqueCrear,
    BloqueOut,
    CursoConCodigoOut,
    CursoCrear,
    CursoOut,
    TokenOut,
    UnirseCursoIn,
)
from interfaz.api.rutas_auth import registrar_resultado_intento, verificar_bloqueo
from nucleo.codigos import generar_codigo_invitacion

router = APIRouter(prefix="/cursos", tags=["cursos"])


def _obtener_curso_o_404(curso_id: int, db: Session) -> Curso:
    curso = db.get(Curso, curso_id)
    if curso is None:
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
def listar_cursos(db: Session = Depends(obtener_db)):
    return db.query(Curso).all()


@router.post("/unirse", response_model=TokenOut)
def unirse_curso(datos: UnirseCursoIn, db: Session = Depends(obtener_db)):
    curso = db.query(Curso).filter_by(codigo_invitacion=datos.codigo_invitacion).first()
    if curso is None:
        raise HTTPException(status_code=404, detail="Código de invitación inválido")

    usuario = db.query(Usuario).filter_by(rut=datos.rut).first()
    if usuario is None:
        usuario = Usuario(
            rut=datos.rut,
            nombre=datos.nombre,
            colegio_id=curso.colegio_id,
            pin_hash=hashear_secreto(datos.pin),
        )
        usuario.roles = [UsuarioRol(rol=RolNombre.ALUMNO)]
        db.add(usuario)
        db.flush()
    else:
        # Una cuenta de staff no se convierte en alumno por esta vía: si no, bastaría
        # un código de invitación + el RUT de un UTP para fijarle PIN y entrar como él.
        if RolNombre.ALUMNO not in {r.rol for r in usuario.roles}:
            raise HTTPException(status_code=409, detail="Este RUT pertenece a una cuenta de personal del colegio")

        if usuario.pin_hash is None:
            usuario.pin_hash = hashear_secreto(datos.pin)
        else:
            # Mismo límite de intentos que /auth/login/alumno — si no, esta ruta
            # serviría para adivinar el PIN sin bloqueo.
            verificar_bloqueo(usuario)
            if not verificar_secreto(datos.pin, usuario.pin_hash):
                registrar_resultado_intento(usuario, exitoso=False, db=db)
                raise HTTPException(status_code=401, detail="PIN incorrecto para este RUT")
            registrar_resultado_intento(usuario, exitoso=True, db=db)

    ya_inscrito = db.query(AlumnoCurso).filter_by(usuario_id=usuario.id, curso_id=curso.id).first()
    if ya_inscrito is None:
        db.add(AlumnoCurso(usuario_id=usuario.id, curso_id=curso.id))

    db.commit()
    db.refresh(usuario)
    return emitir_token(usuario)


@router.get("/{curso_id}", response_model=CursoOut)
def obtener_curso(curso_id: int, db: Session = Depends(obtener_db)):
    return _obtener_curso_o_404(curso_id, db)


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
    if datos.profesor_id is not None:
        profesor = db.get(Usuario, datos.profesor_id)
        if profesor is None or profesor.colegio_id != _utp.colegio_id:
            raise HTTPException(status_code=409, detail="profesor_id inexistente")

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
def listar_bloques(curso_id: int, db: Session = Depends(obtener_db)):
    _obtener_curso_o_404(curso_id, db)
    return db.query(Bloque).filter_by(curso_id=curso_id).all()
