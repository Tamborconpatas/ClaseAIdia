import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from infraestructura.modelos_orm import (
    AlumnoCurso,
    Bloque,
    Clase,
    Colegio,
    ContenidoClase,
    Curso,
    RolNombre,
    TipoBloque,
    Usuario,
    UsuarioRol,
)

# Contenido representativo de lo que produce el pipeline real (nucleo/subtitulos.py
# + servicios/servicio_material_estudio.py): acentos, ¿¡, saltos de línea, formato SRT.
TRANSCRIPCION_TEXTO = (
    "Hoy vamos a revisar la Revolución Francesa y sus causas económicas y sociales. "
    "¿Alguien recuerda qué significaba el Antiguo Régimen? Exacto: una sociedad dividida "
    "en estamentos, donde la nobleza y el clero no pagaban impuestos."
)

TRANSCRIPCION_SRT = (
    "1\n"
    "00:00:00,000 --> 00:00:04,500\n"
    "Hoy vamos a revisar la Revolución Francesa y sus causas económicas y sociales.\n"
    "\n"
    "2\n"
    "00:00:04,500 --> 00:00:09,120\n"
    "¿Alguien recuerda qué significaba el Antiguo Régimen?\n"
)

TARJETAS = [
    {"pregunta": "¿Qué es el Antiguo Régimen?", "respuesta": "El sistema social previo a 1789, dividido en estamentos."},
    {"pregunta": "¿Quiénes no pagaban impuestos?", "respuesta": "La nobleza y el clero."},
]


def _crear_cadena_completa(db):
    """Colegio -> Curso -> Bloque -> Clase, sin ContenidoClase todavía."""
    colegio = Colegio(nombre="Liceo de Prueba")
    db.add(colegio)
    db.commit()
    db.refresh(colegio)

    curso = Curso(nombre="8A", colegio_id=colegio.id, codigo_invitacion="ABC123")
    db.add(curso)
    db.commit()
    db.refresh(curso)

    bloque = Bloque(
        curso_id=curso.id,
        tipo=TipoBloque.CLASE,
        asignatura="Historia",
        dia_semana=1,
        hora_inicio=datetime.time(10, 0),
        hora_fin=datetime.time(10, 45),
    )
    db.add(bloque)
    db.commit()
    db.refresh(bloque)

    clase = Clase(bloque_id=bloque.id, fecha=datetime.date(2026, 8, 27))
    db.add(clase)
    db.commit()
    db.refresh(clase)

    return colegio, curso, bloque, clase


def test_contenido_clase_con_datos_reales_de_transcripcion(sesion_db):
    _, _, _, clase = _crear_cadena_completa(sesion_db)

    contenido = ContenidoClase(
        clase_id=clase.id,
        transcripcion_texto=TRANSCRIPCION_TEXTO,
        transcripcion_srt=TRANSCRIPCION_SRT,
        resumen="La clase cubrió las causas del fin del Antiguo Régimen y la Revolución Francesa.",
        puntos_clave="- Antiguo Régimen\n- Estamentos\n- Privilegios fiscales de nobleza y clero",
        hoja_repaso="El Antiguo Régimen importa porque explica por qué estalla la revolución: "
        "la desigualdad fiscal generaba tensión entre estamentos.",
        tarjetas=TARJETAS,
        preguntas_detectadas=None,
        aprobado=False,
    )
    sesion_db.add(contenido)
    sesion_db.commit()

    # Releer desde una sesión nueva (misma conexión en memoria) para forzar
    # una lectura real desde la base, no solo el objeto en memoria de Python.
    sesion_db.expire_all()
    recargado = sesion_db.get(ContenidoClase, contenido.id)

    assert recargado.transcripcion_texto == TRANSCRIPCION_TEXTO
    assert recargado.transcripcion_srt == TRANSCRIPCION_SRT
    assert "Antiguo Régimen" in recargado.resumen
    assert recargado.tarjetas == TARJETAS
    assert recargado.tarjetas[0]["pregunta"].startswith("¿Qué es")
    assert recargado.aprobado is False
    assert recargado.clase.bloque.asignatura == "Historia"
    assert recargado.clase.bloque.curso.nombre == "8A"


def test_bloque_hora_y_clase_fecha_son_tipos_python_reales(sesion_db):
    _, _, bloque, clase = _crear_cadena_completa(sesion_db)

    sesion_db.expire_all()
    bloque_recargado = sesion_db.get(Bloque, bloque.id)
    clase_recargada = sesion_db.get(Clase, clase.id)

    assert isinstance(bloque_recargado.hora_inicio, datetime.time)
    assert isinstance(clase_recargada.fecha, datetime.date)
    assert bloque_recargado.hora_inicio == datetime.time(10, 0)


def test_cascade_borrar_bloque_borra_clase_y_contenido(sesion_db):
    _, _, bloque, clase = _crear_cadena_completa(sesion_db)
    contenido = ContenidoClase(clase_id=clase.id, transcripcion_texto="texto")
    sesion_db.add(contenido)
    sesion_db.commit()

    clase_id, contenido_id = clase.id, contenido.id

    sesion_db.delete(bloque)
    sesion_db.commit()

    assert sesion_db.get(Clase, clase_id) is None
    assert sesion_db.get(ContenidoClase, contenido_id) is None


def test_cascade_borrar_curso_borra_bloques(sesion_db):
    _, curso, bloque, _ = _crear_cadena_completa(sesion_db)
    bloque_id = bloque.id

    sesion_db.delete(curso)
    sesion_db.commit()

    assert sesion_db.get(Bloque, bloque_id) is None


def test_borrar_colegio_con_dependientes_falla(sesion_db):
    colegio, _, _, _ = _crear_cadena_completa(sesion_db)

    sesion_db.delete(colegio)
    with pytest.raises(IntegrityError):
        sesion_db.commit()
    sesion_db.rollback()


def test_usuario_no_permite_rol_duplicado(sesion_db):
    colegio = Colegio(nombre="Liceo de Prueba")
    sesion_db.add(colegio)
    sesion_db.commit()

    usuario = Usuario(rut="11222333-9", nombre="Profe Test", colegio_id=colegio.id)
    usuario.roles = [UsuarioRol(rol=RolNombre.PROFESOR), UsuarioRol(rol=RolNombre.PROFESOR)]
    sesion_db.add(usuario)

    with pytest.raises(IntegrityError):
        sesion_db.commit()
    sesion_db.rollback()


def test_usuario_puede_tener_multiples_roles_distintos(sesion_db):
    colegio = Colegio(nombre="Liceo de Prueba")
    sesion_db.add(colegio)
    sesion_db.commit()

    usuario = Usuario(rut="11222333-9", nombre="Profe y UTP", colegio_id=colegio.id)
    usuario.roles = [UsuarioRol(rol=RolNombre.PROFESOR), UsuarioRol(rol=RolNombre.UTP)]
    sesion_db.add(usuario)
    sesion_db.commit()

    sesion_db.expire_all()
    recargado = sesion_db.get(Usuario, usuario.id)
    assert {r.rol for r in recargado.roles} == {RolNombre.PROFESOR, RolNombre.UTP}


def test_alumno_no_puede_unirse_dos_veces_al_mismo_curso(sesion_db):
    colegio = Colegio(nombre="Liceo de Prueba")
    sesion_db.add(colegio)
    sesion_db.commit()

    curso = Curso(nombre="8A", colegio_id=colegio.id, codigo_invitacion="XYZ999")
    alumno = Usuario(rut="1000005-K", nombre="Alumno Test", colegio_id=colegio.id)
    sesion_db.add_all([curso, alumno])
    sesion_db.commit()

    sesion_db.add(AlumnoCurso(usuario_id=alumno.id, curso_id=curso.id))
    sesion_db.commit()

    sesion_db.add(AlumnoCurso(usuario_id=alumno.id, curso_id=curso.id))
    with pytest.raises(IntegrityError):
        sesion_db.commit()
    sesion_db.rollback()
