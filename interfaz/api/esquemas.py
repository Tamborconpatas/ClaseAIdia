import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from infraestructura.modelos_orm import RolNombre, TipoBloque
from nucleo.validadores import validar_rut


class ColegioBase(BaseModel):
    nombre: str


class ColegioCrear(ColegioBase):
    pass


class ColegioOut(ColegioBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class UsuarioBase(BaseModel):
    rut: str
    nombre: str
    colegio_id: int
    roles: list[RolNombre] = []

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        if not validar_rut(valor):
            raise ValueError("RUT inválido (dígito verificador no corresponde)")
        return valor


class UsuarioCrear(UsuarioBase):
    """Alta administrativa de staff (profesor/UTP) por un UTP ya autenticado.
    El alumno se da de alta vía POST /cursos/unirse, no por acá."""

    password: str

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


class CursoBase(BaseModel):
    nombre: str
    colegio_id: int


class CursoCrear(CursoBase):
    pass


class CursoOut(CursoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
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


class BloqueCrear(BloqueBase):
    pass


class BloqueOut(BloqueBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    curso_id: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    roles: list[RolNombre]
    colegio_id: int


class BootstrapUtpIn(BaseModel):
    rut: str
    nombre: str
    password: str
    colegio_id: int

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        if not validar_rut(valor):
            raise ValueError("RUT inválido (dígito verificador no corresponde)")
        return valor


class LoginStaffIn(BaseModel):
    rut: str
    password: str


class LoginAlumnoIn(BaseModel):
    rut: str
    pin: str


class UnirseCursoIn(BaseModel):
    codigo_invitacion: str
    rut: str
    nombre: str
    pin: str

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        if not validar_rut(valor):
            raise ValueError("RUT inválido (dígito verificador no corresponde)")
        return valor
