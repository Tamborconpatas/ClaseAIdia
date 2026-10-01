import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from infraestructura.modelos_orm import RolNombre, TipoBloque
from nucleo.validadores import normalizar_rut, validar_rut


def _rut_valido_normalizado(valor: str) -> str:
    if not validar_rut(valor):
        raise ValueError("RUT inválido (dígito verificador no corresponde)")
    return normalizar_rut(valor)


LARGO_MIN_PASSWORD = 10
# Tope: argon2 con textos enormes es una forma barata de saturar el servidor.
LARGO_MAX_SECRETO = 128


def _password_valida(valor: str) -> str:
    if len(valor) < LARGO_MIN_PASSWORD:
        raise ValueError(f"La contraseña debe tener al menos {LARGO_MIN_PASSWORD} caracteres")
    if len(valor) > LARGO_MAX_SECRETO:
        raise ValueError(f"La contraseña no puede superar {LARGO_MAX_SECRETO} caracteres")
    if len(set(valor)) < 4:
        raise ValueError("La contraseña es demasiado repetitiva (usa al menos 4 caracteres distintos)")
    return valor


def _password_sin_rut(rut: str, password: str) -> None:
    if normalizar_rut(rut).split("-")[0] in password.replace(".", ""):
        raise ValueError("La contraseña no puede contener el RUT")


def pin_es_facil(pin: str) -> bool:
    """Repetido (111111) o secuencia (123456, 654321). El alumno elige su PIN, así que se filtra al elegirlo."""
    return len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210"


def _pin_6_digitos(valor: str) -> str:
    if not (len(valor) == 6 and valor.isascii() and valor.isdigit()):
        raise ValueError("El PIN debe tener exactamente 6 dígitos")
    return valor


class ColegioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str


class UsuarioBase(BaseModel):
    rut: str
    nombre: str
    colegio_id: int
    roles: list[RolNombre] = []

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        return _rut_valido_normalizado(valor)


class UsuarioCrear(UsuarioBase):
    """Alta administrativa de staff (profesor/UTP) por un UTP ya autenticado.
    El alumno se da de alta vía POST /cursos/unirse, no por acá."""

    password: str

    @field_validator("password")
    @classmethod
    def _validar_password(cls, valor: str) -> str:
        return _password_valida(valor)

    @model_validator(mode="after")
    def _password_no_contiene_rut(self):
        _password_sin_rut(self.rut, self.password)
        return self

    @field_validator("roles")
    @classmethod
    def _solo_roles_staff(cls, valor: list[RolNombre]) -> list[RolNombre]:
        if not valor:
            raise ValueError("Debe especificar al menos un rol (PROFESOR o UTP)")
        if RolNombre.ALUMNO in valor:
            raise ValueError("Los alumnos se registran vía /cursos/unirse, no por este endpoint")
        return valor


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rut: str
    nombre: str
    colegio_id: int
    roles: list[RolNombre] = []

    @field_validator("roles", mode="before")
    @classmethod
    def _extraer_roles(cls, valor):
        if valor and hasattr(valor[0], "rol"):
            return [r.rol for r in valor]
        return valor


def _nombre_de_curso(valor: str) -> str:
    valor = valor.strip()
    if not valor:
        raise ValueError("El curso necesita un nombre")
    if len(valor) > 60:
        raise ValueError("El nombre del curso no puede superar los 60 caracteres")
    return valor


class CursoBase(BaseModel):
    nombre: str
    colegio_id: int

    @field_validator("nombre")
    @classmethod
    def _validar_nombre(cls, valor: str) -> str:
        return _nombre_de_curso(valor)


class CursoRenombrar(BaseModel):
    nombre: str

    @field_validator("nombre")
    @classmethod
    def _validar_nombre(cls, valor: str) -> str:
        return _nombre_de_curso(valor)


class AlumnoOut(BaseModel):
    """Lo que un profesor o el UTP ve de un alumno de un curso."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    rut: str


class CursoCrear(CursoBase):
    pass


class CursoOut(CursoBase):
    """Vista pública: sin el código de invitación (con él cualquiera podría unirse)."""

    model_config = ConfigDict(from_attributes=True)
    id: int


class CursoConCodigoOut(CursoOut):
    """Solo para el UTP que crea el curso."""

    codigo_invitacion: str


class CodigoCursoOut(BaseModel):
    codigo_invitacion: str


class BloqueBase(BaseModel):
    tipo: TipoBloque
    asignatura: str | None = None
    profesor_id: int | None = None
    sala: str | None = None
    dia_semana: int
    hora_inicio: datetime.time
    hora_fin: datetime.time

    @field_validator("dia_semana")
    @classmethod
    def _validar_dia_semana(cls, valor: int) -> int:
        if not 0 <= valor <= 6:
            raise ValueError("dia_semana debe estar entre 0 (lunes) y 6 (domingo)")
        return valor

    @model_validator(mode="after")
    def _coherente(self):
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("La hora de término debe ser posterior a la de inicio")
        self.asignatura = (self.asignatura or "").strip() or None
        self.sala = (self.sala or "").strip() or None
        if self.tipo == TipoBloque.CLASE:
            if not self.asignatura:
                raise ValueError("Una clase necesita asignatura")
        else:
            # Recreo y almuerzo no tienen asignatura ni profesor: si no, aparecerían en el horario del profesor.
            self.asignatura = self.profesor_id = None
        return self


class BloqueCrear(BloqueBase):
    pass


class BloqueOut(BloqueBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    curso_id: int
    # Un alumno no puede consultar usuarios, así que el nombre viaja en el propio bloque.
    profesor_nombre: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    roles: list[RolNombre]
    colegio_id: int


class SetupIn(BaseModel):
    """Primera ejecución del servidor: crea el colegio y su primer UTP."""

    colegio_nombre: str
    rut: str
    nombre: str
    password: str

    @field_validator("password")
    @classmethod
    def _validar_password(cls, valor: str) -> str:
        return _password_valida(valor)

    @model_validator(mode="after")
    def _password_no_contiene_rut(self):
        _password_sin_rut(self.rut, self.password)
        return self

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        return _rut_valido_normalizado(valor)


class LoginStaffIn(BaseModel):
    rut: str
    # Sin mínimo (no se delata la política en el login), pero con tope.
    password: str = Field(max_length=LARGO_MAX_SECRETO)

    @field_validator("rut")
    @classmethod
    def _normalizar_rut(cls, valor: str) -> str:
        return normalizar_rut(valor)


class LoginAlumnoIn(BaseModel):
    rut: str
    pin: str

    @field_validator("rut")
    @classmethod
    def _normalizar_rut(cls, valor: str) -> str:
        return normalizar_rut(valor)

    @field_validator("pin")
    @classmethod
    def _validar_pin(cls, valor: str) -> str:
        return _pin_6_digitos(valor)


class ResetPinOut(BaseModel):
    """Se muestra una sola vez al staff, que se lo entrega al alumno en persona."""

    codigo: str
    vence: datetime.datetime


class RestablecerPinIn(BaseModel):
    rut: str
    codigo: str
    pin: str

    @field_validator("rut")
    @classmethod
    def _normalizar_rut(cls, valor: str) -> str:
        return normalizar_rut(valor)

    @field_validator("codigo")
    @classmethod
    def _normalizar_codigo(cls, valor: str) -> str:
        return valor.strip().upper()

    @field_validator("pin")
    @classmethod
    def _validar_pin(cls, valor: str) -> str:
        return _pin_6_digitos(valor)


class UnirseCursoIn(BaseModel):
    codigo_invitacion: str
    rut: str
    nombre: str
    pin: str

    @field_validator("pin")
    @classmethod
    def _validar_pin(cls, valor: str) -> str:
        return _pin_6_digitos(valor)

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        return _rut_valido_normalizado(valor)


EstadoClase = Literal["procesando", "por_aprobar", "provisoria", "publicada", "retirada"]


class ClaseOut(BaseModel):
    id: int
    bloque_id: int  # el bloque del horario del que es una instancia (el bloque se repite cada semana)
    fecha: datetime.date
    curso_id: int
    curso_nombre: str
    asignatura: str | None
    sala: str | None
    hora_inicio: datetime.time
    hora_fin: datetime.time
    profesor_id: int | None
    # procesando = aún sin material; por_aprobar = el profesor está a tiempo de revisarlo (los alumnos aún no lo ven);
    # provisoria = pasó el plazo sin revisión y los alumnos lo ven con una advertencia; publicada = aprobada por el
    # profesor; retirada = el profesor la ocultó.
    estado: EstadoClase
    # Hasta cuándo puede revisarla el profesor antes de que se publique como provisoria (solo en por_aprobar).
    revision_vence: datetime.datetime | None
    prioritaria: bool


class TarjetaOut(BaseModel):
    pregunta: str
    respuesta: str


class ContenidoOut(BaseModel):
    resumen: str | None
    puntos_clave: str | None
    hoja_repaso: str | None
    tarjetas: list[TarjetaOut]
    transcripcion_texto: str | None


class ContenidoEditar(BaseModel):
    """Lo que el profesor puede corregir del material generado. La transcripción no se edita: es el registro de lo dicho."""

    resumen: str = Field(max_length=20_000)
    puntos_clave: str = Field(max_length=20_000)
    hoja_repaso: str = Field(max_length=20_000)
    tarjetas: list[TarjetaOut] = Field(max_length=40)

    @field_validator("resumen", "puntos_clave", "hoja_repaso")
    @classmethod
    def _recortar(cls, valor: str) -> str:
        return valor.strip()

    @field_validator("tarjetas")
    @classmethod
    def _tarjetas_completas(cls, tarjetas: list[TarjetaOut]) -> list[TarjetaOut]:
        limpias = [TarjetaOut(pregunta=t.pregunta.strip(), respuesta=t.respuesta.strip()) for t in tarjetas]
        if any(not t.pregunta or not t.respuesta for t in limpias):
            raise ValueError("Cada tarjeta necesita pregunta y respuesta")
        return limpias


class ClaseDetalleOut(ClaseOut):
    contenido: ContenidoOut | None
