import datetime
import enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infraestructura.basedatos import Base


def _ahora_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class RolNombre(str, enum.Enum):
    ALUMNO = "ALUMNO"
    PROFESOR = "PROFESOR"
    UTP = "UTP"


class TipoBloque(str, enum.Enum):
    CLASE = "CLASE"
    RECREO = "RECREO"
    ALMUERZO = "ALMUERZO"


class EstadoGrabacion(str, enum.Enum):
    ESPERANDO = "esperando"  # sesión creada, aún no se inicia
    GRABANDO = "grabando"
    PAUSADA = "pausada"
    TERMINANDO = "terminando"  # se pidió terminar: el equipo grabador sube lo último y finaliza
    PROCESANDO = "procesando"  # transcribiendo y generando el material
    TERMINADA = "terminada"
    ERROR = "error"


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
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_hasta: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # Código de un solo uso que entrega el staff al resetear el PIN de un alumno.
    codigo_reset_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    codigo_reset_vence: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # Una cuenta desactivada (personal que se fue) no entra ni con una sesión ya abierta, pero conserva su historial.
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    @property
    def profesor_nombre(self) -> str | None:
        """Solo el nombre (nunca el RUT): lo ven los alumnos del curso en su horario."""
        return self.profesor.nombre if self.profesor else None
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
    grabacion: Mapped["Grabacion | None"] = relationship(
        back_populates="clase", cascade="all, delete-orphan", uselist=False
    )


class Grabacion(Base):
    """Sesión de grabación de una clase. El estado que guarda el servidor es el que manda: quien controla
    (el celular del profesor, o el mismo equipo que graba) lo cambia con comandos, y el equipo grabador
    (un PC de la sala o el celular) lo consulta y obedece. El audio no se guarda aquí: son trozos temporales
    en disco que se borran al terminar de procesarse."""

    __tablename__ = "grabaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clase_id: Mapped[int] = mapped_column(ForeignKey("clases.id"), nullable=False, unique=True)
    estado: Mapped[EstadoGrabacion] = mapped_column(Enum(EstadoGrabacion), default=EstadoGrabacion.ESPERANDO, nullable=False)
    silenciada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Hora local (la del horario del colegio, sin zona) en que se corta sola la grabación si el profesor olvida terminarla.
    corte_en: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    # Equipo que está grabando (un id al azar que genera su navegador) y su último latido (UTC, sin zona).
    grabador_id: Mapped[str | None] = mapped_column(String, nullable=True)
    latido_en: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    segundos_grabados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nivel: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # volumen del micrófono, 0 a 1
    trozos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_recibidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mime: Mapped[str | None] = mapped_column(String, nullable=True)
    creada_en: Mapped[datetime.datetime] = mapped_column(DateTime, default=_ahora_utc, nullable=False)
    terminando_desde: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    # Reintentos automáticos: nadie está frente al computador cuando algo falla, así que un fallo del procesamiento se
    # reintenta solo (con esperas crecientes) mientras queden intentos; el audio se conserva hasta el último.
    intentos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reintento_en: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    clase: Mapped["Clase"] = relationship(back_populates="grabacion")


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
    # El profesor revisa el material: aprobado = lo ven los alumnos sin advertencia. Si pasa el plazo de
    # revisión sin aprobarlo ni retirarlo, se publica como "provisorio" (con advertencia) — así un olvido
    # del profesor no deja a los alumnos sin material. `retirado` lo oculta y evita esa publicación.
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retirado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Cuándo quedó listo el material (UTC, sin zona): desde ahí corre el plazo de revisión.
    generado_en: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True, default=_ahora_utc)

    clase: Mapped["Clase"] = relationship(back_populates="contenido")
