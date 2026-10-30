# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

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
    rut: str = Field(max_length=20)
    nombre: str = Field(max_length=120)
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
    activo: bool = True
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

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def _hora_sin_zona(cls, valor: datetime.time) -> datetime.time:
        # "09:00Z" o "09:00+02:00" no se pueden comparar con una hora sin zona (daba error 500): el horario es local.
        if valor.tzinfo is not None:
            raise ValueError("La hora no lleva zona horaria (usa HH:MM)")
        return valor

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
    # Solo al entrar: BloqueOut hereda de BloqueBase y no debe fallar con textos largos que ya estuvieran guardados.
    asignatura: str | None = Field(default=None, max_length=100)
    sala: str | None = Field(default=None, max_length=50)


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

    colegio_nombre: str = Field(max_length=120)
    rut: str = Field(max_length=20)
    nombre: str = Field(max_length=120)
    password: str = Field(max_length=LARGO_MAX_SECRETO)

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
    rut: str = Field(max_length=20)
    # Sin mínimo (no se delata la política en el login), pero con tope.
    password: str = Field(max_length=LARGO_MAX_SECRETO)

    @field_validator("rut")
    @classmethod
    def _normalizar_rut(cls, valor: str) -> str:
        return normalizar_rut(valor)


class LoginAlumnoIn(BaseModel):
    rut: str = Field(max_length=20)
    pin: str = Field(max_length=64)

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


class RestablecerPasswordIn(BaseModel):
    """El personal fija una contraseña nueva con el código de un solo uso que le dio un UTP."""

    rut: str = Field(max_length=20)
    codigo: str = Field(max_length=32)
    password: str = Field(max_length=LARGO_MAX_SECRETO)

    @field_validator("rut")
    @classmethod
    def _normalizar_rut(cls, valor: str) -> str:
        return normalizar_rut(valor)

    @field_validator("codigo")
    @classmethod
    def _normalizar_codigo(cls, valor: str) -> str:
        return valor.strip().upper()

    @field_validator("password")
    @classmethod
    def _validar_password(cls, valor: str) -> str:
        return _password_valida(valor)

    @model_validator(mode="after")
    def _password_no_contiene_rut(self):
        _password_sin_rut(self.rut, self.password)
        return self


class RestablecerPinIn(BaseModel):
    rut: str = Field(max_length=20)
    codigo: str = Field(max_length=32)
    pin: str = Field(max_length=64)

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
    codigo_invitacion: str = Field(max_length=32)
    rut: str = Field(max_length=20)
    nombre: str = Field(max_length=120)
    pin: str = Field(max_length=64)

    @field_validator("pin")
    @classmethod
    def _validar_pin(cls, valor: str) -> str:
        return _pin_6_digitos(valor)

    @field_validator("rut")
    @classmethod
    def _validar_rut(cls, valor: str) -> str:
        return _rut_valido_normalizado(valor)


EstadoClase = Literal["grabando", "procesando", "error", "por_aprobar", "provisoria", "publicada", "retirada"]


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


class PizarraOut(BaseModel):
    """Lo que se leyó de una foto de la pizarra (la imagen ya no existe). Puede traer LaTeX ($...$, $$...$$)."""

    id: int
    segundo: int
    texto: str


class RelacionMapa(BaseModel):
    """Una flecha del mapa conceptual: «de» —relacion→ «a»."""

    de: str = Field(max_length=60)
    relacion: str = Field(default="", max_length=40)
    a: str = Field(max_length=60)

    @field_validator("de", "relacion", "a")
    @classmethod
    def _limpiar(cls, valor: str) -> str:
        return " ".join(valor.split())  # sin saltos de línea ni espacios de más

    @model_validator(mode="after")
    def _completa(self):
        if not self.de or not self.a:
            raise ValueError("Cada relación necesita un concepto de origen y uno de destino")
        return self


class MapaEditar(BaseModel):
    relaciones: list[RelacionMapa] = Field(max_length=30)


class PizarraEditar(BaseModel):
    texto: str = Field(max_length=8_000)

    @field_validator("texto")
    @classmethod
    def _recortar(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("El texto no puede quedar vacío (si no sirve, quita la foto)")
        return valor


class ContenidoOut(BaseModel):
    resumen: str | None
    puntos_clave: str | None
    hoja_repaso: str | None
    tarjetas: list[TarjetaOut]
    transcripcion_texto: str | None
    pizarra: list[PizarraOut] = []
    mapa: list[RelacionMapa] = []


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


# --- Grabación en vivo ---------------------------------------------------------------------------

AccionGrabacion = Literal[
    "iniciar", "pausar", "reanudar", "silenciar", "activar_audio", "terminar", "cancelar", "marcar_prioritaria", "quitar_prioritaria"
]
_ID_DISPOSITIVO = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class AjusteFotosEditar(BaseModel):
    activada: bool


class DescargaOut(BaseModel):
    estado: Literal["descargando", "lista", "error"]
    porcentaje: float
    mensaje: str


class AjusteFotosOut(BaseModel):
    """Lo que el UTP necesita para decidir si activa las fotos de la pizarra, y para dejarlas listas sin una consola."""

    activada: bool
    modelo: str
    ollama_responde: bool
    modelo_instalado: bool
    memoria_total_gb: float | None
    memoria_recomendada_gb: float
    descarga: DescargaOut | None = None


# --- Estado del servidor (panel del UTP) ---------------------------------------------------------


class EstadoClaseOut(BaseModel):
    clase_id: int
    asignatura: str | None
    curso: str
    fecha: datetime.date


class EstadoEnVivoOut(EstadoClaseOut):
    estado: str


class EstadoProcesandoOut(EstadoClaseOut):
    turno: Literal["ahora", "espera"]
    minutos: int | None  # desde que el trabajador arrancó con esta clase; None si todavía espera su turno
    posicion: int | None  # lugar en la cola (1 = la próxima); None si ya está en marcha
    prioritaria: bool


class EstadoReintentoOut(EstadoClaseOut):
    intentos: int
    reintento_en: datetime.datetime  # UTC
    error: str | None


class EstadoErrorOut(EstadoClaseOut):
    error: str | None


class EstadoProcesamientoOut(BaseModel):
    en_vivo: list[EstadoEnVivoOut]
    procesando: list[EstadoProcesandoOut]
    con_reintento: list[EstadoReintentoOut]
    con_error: list[EstadoErrorOut]
    terminadas_24h: int


class EstadoOllamaOut(BaseModel):
    responde: bool
    modelo_texto: str
    modelo_texto_instalado: bool


class EstadoDiscoOut(BaseModel):
    libre_gb: float
    total_gb: float
    audio_temporal_mb: float
    fotos_temporales_mb: float
    base_de_datos_mb: float | None


class EstadoRespaldosOut(BaseModel):
    carpeta: str
    cantidad: int
    mb: float
    ultimo: datetime.date | None
    hace_dias: int | None
    en_el_mismo_disco: bool | None


class EstadoMemoriaOut(BaseModel):
    total_gb: float | None
    libre_gb: float | None


class EstadoVigilanciaOut(BaseModel):
    ultima_pasada: datetime.datetime | None  # UTC
    activa: bool | None  # None: la vigilancia no está encendida en este servidor (solo pasa en pruebas)


class EstadoAlertaOut(BaseModel):
    tema: Literal["disco", "ollama", "respaldos", "memoria", "vigilancia", "clases"]  # a qué parte del panel se refiere
    nivel: Literal["critico", "aviso"]
    texto: str


class EstadoServidorOut(BaseModel):
    generado_en: datetime.datetime  # UTC
    alertas: list[EstadoAlertaOut]
    procesamiento: EstadoProcesamientoOut
    ollama: EstadoOllamaOut
    disco: EstadoDiscoOut
    respaldos: EstadoRespaldosOut
    memoria: EstadoMemoriaOut
    vigilancia: EstadoVigilanciaOut


class GrabacionCrear(BaseModel):
    bloque_id: int


class GrabacionComando(BaseModel):
    accion: AccionGrabacion


class GrabadorRegistrar(BaseModel):
    dispositivo: str = _ID_DISPOSITIVO
    forzar: bool = False  # tomar el lugar de otro equipo que ya graba


class GrabadorLatido(BaseModel):
    dispositivo: str = _ID_DISPOSITIVO
    segundos: int = Field(ge=0, le=24 * 3600)
    nivel: float = Field(ge=0, le=1)


class GrabadorFinalizar(BaseModel):
    dispositivo: str = _ID_DISPOSITIVO


class FotoPizarraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    segundo: int
    estado: str  # pendiente | leida | error
    texto: str | None = None
    error: str | None = None


class GrabacionOut(BaseModel):
    id: int
    clase_id: int
    bloque_id: int
    asignatura: str | None
    curso_nombre: str
    sala: str | None
    fecha: datetime.date
    hora_inicio: datetime.time
    hora_fin: datetime.time
    estado: str
    silenciada: bool
    prioritaria: bool
    corte_en: datetime.datetime
    segundos_grabados: int
    nivel: float
    trozos: int
    grabador_id: str | None
    grabador_conectado: bool
    error: str | None
    reintento_en: datetime.datetime | None = None  # cuándo se reintenta sola (UTC), si hay un reintento programado
    posicion_en_cola: int | None = None  # procesando y esperando turno: su lugar (1 = la próxima); None si ya la procesan o no aplica
    fotos: list[FotoPizarraOut] = []  # fotos de la pizarra de esta clase (la imagen no se guarda: solo el texto leído)
    fotos_habilitadas: bool = False  # el UTP activó las fotos de la pizarra en Ajustes


class BloqueDeHoyOut(BaseModel):
    bloque_id: int
    asignatura: str | None
    curso_nombre: str
    sala: str | None
    hora_inicio: datetime.time
    hora_fin: datetime.time
    puede_grabar: bool
    motivo: str | None
    grabacion: GrabacionOut | None
