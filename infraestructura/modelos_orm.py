import datetime
import enum

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infraestructura.basedatos import Base


class RolNombre(str, enum.Enum):
    ALUMNO = "ALUMNO"
    PROFESOR = "PROFESOR"
    UTP = "UTP"


class TipoBloque(str, enum.Enum):
    CLASE = "CLASE"
    RECREO = "RECREO"
    ALMUERZO = "ALMUERZO"


class Colegio(Base):
    __tablename__ = "colegios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="colegio")
    cursos: Mapped[list["Curso"]] = relationship(back_populates="colegio")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rut: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    # Solo profesor/UTP tienen contraseña; solo alumno tiene PIN. La lógica
    # de hashing/login llega en la Fase 2 — por ahora quedan en None.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    colegio_id: Mapped[int] = mapped_column(ForeignKey("colegios.id"), nullable=False)

    colegio: Mapped["Colegio"] = relationship(back_populates="usuarios")
    roles: Mapped[list["UsuarioRol"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")
    cursos: Mapped[list["AlumnoCurso"]] = relationship(back_populates="usuario", cascade="all, delete-orphan")


class UsuarioRol(Base):
    __tablename__ = "usuario_roles"
    __table_args__ = (UniqueConstraint("usuario_id", "rol", name="uq_usuario_rol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    rol: Mapped[RolNombre] = mapped_column(Enum(RolNombre), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="roles")


class Curso(Base):
    __tablename__ = "cursos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    colegio_id: Mapped[int] = mapped_column(ForeignKey("colegios.id"), nullable=False)
    codigo_invitacion: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    colegio: Mapped["Colegio"] = relationship(back_populates="cursos")
    bloques: Mapped[list["Bloque"]] = relationship(back_populates="curso", cascade="all, delete-orphan")
    alumnos: Mapped[list["AlumnoCurso"]] = relationship(back_populates="curso", cascade="all, delete-orphan")


class AlumnoCurso(Base):
    __tablename__ = "alumno_curso"
    __table_args__ = (UniqueConstraint("usuario_id", "curso_id", name="uq_alumno_curso"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="cursos")
    curso: Mapped["Curso"] = relationship(back_populates="alumnos")


class Bloque(Base):
    __tablename__ = "bloques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    curso_id: Mapped[int] = mapped_column(ForeignKey("cursos.id"), nullable=False)
    tipo: Mapped[TipoBloque] = mapped_column(Enum(TipoBloque), nullable=False)
    # Nulo si el bloque es RECREO/ALMUERZO (no lectivo).
    asignatura: Mapped[str | None] = mapped_column(String, nullable=True)
    profesor_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    sala: Mapped[str | None] = mapped_column(String, nullable=True)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=lunes ... 6=domingo
    hora_inicio: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[datetime.time] = mapped_column(Time, nullable=False)

    curso: Mapped["Curso"] = relationship(back_populates="bloques")
    profesor: Mapped["Usuario | None"] = relationship()
    clases: Mapped[list["Clase"]] = relationship(back_populates="bloque", cascade="all, delete-orphan")


class Clase(Base):
    __tablename__ = "clases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bloque_id: Mapped[int] = mapped_column(ForeignKey("bloques.id"), nullable=False)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    # Marcador manual que la futura cola EDF (Fase 5) usará para priorizar.
    prioritaria: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    bloque: Mapped["Bloque"] = relationship(back_populates="clases")
    contenido: Mapped["ContenidoClase | None"] = relationship(
        back_populates="clase", cascade="all, delete-orphan", uselist=False
    )


class ContenidoClase(Base):
    __tablename__ = "contenido_clases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clase_id: Mapped[int] = mapped_column(ForeignKey("clases.id"), nullable=False, unique=True)
    transcripcion_texto: Mapped[str | None] = mapped_column(String, nullable=True)
    transcripcion_srt: Mapped[str | None] = mapped_column(String, nullable=True)
    resumen: Mapped[str | None] = mapped_column(String, nullable=True)
    puntos_clave: Mapped[str | None] = mapped_column(String, nullable=True)
    hoja_repaso: Mapped[str | None] = mapped_column(String, nullable=True)
    tarjetas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    preguntas_detectadas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # El profesor debe aprobar antes de que el alumno vea el contenido.
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    clase: Mapped["Clase"] = relationship(back_populates="contenido")
