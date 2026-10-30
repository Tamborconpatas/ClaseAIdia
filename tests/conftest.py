# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from infraestructura.basedatos import Base, obtener_db
from interfaz.api.aplicacion import crear_app


def _crear_motor_prueba():
    """Motor SQLite en memoria, aislado por test — nunca toca escuela.db,
    la base de desarrollo real. Con FKs activas, igual que en producción."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _activar_foreign_keys(conexion_dbapi, _):
        cursor = conexion_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def sin_contadores_de_intentos():
    """Los contadores de intentos fallidos viven en memoria del proceso: cada prueba parte de cero."""
    from interfaz.api import limites

    limites.reiniciar()
    yield
    limites.reiniciar()


@pytest.fixture(autouse=True)
def sin_trabajadores_de_verdad(monkeypatch):
    """Ninguna prueba arranca un trabajador (Whisper, Ollama) de verdad (lo que llega a la cola se queda ahí) ni depende del disco real,
    salvo que la prueba diga otra cosa."""
    from servicios import servicio_grabacion as sg

    monkeypatch.setattr(sg, "_arrancar", lambda *a: None)
    monkeypatch.setattr(sg, "espacio_libre_gb", lambda: 100.0)  # un disco con espacio: el disco real de quien corre las pruebas no debe decidir nada


@pytest.fixture()
def cliente():
    """Cliente de pruebas contra la API (rutas CRUD que sí existen)."""
    engine = _crear_motor_prueba()
    SesionPrueba = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _obtener_db_prueba():
        db = SesionPrueba()
        try:
            yield db
        finally:
            db.close()

    app = crear_app()
    app.dependency_overrides[obtener_db] = _obtener_db_prueba

    with TestClient(app, client=("127.0.0.1", 50000)) as c:  # conexión local, como un PC de la sala
        c.sesion = SesionPrueba  # para armar datos que la API ya no permite crear (otro colegio)
        yield c


@pytest.fixture()
def cliente_remoto(cliente):
    """Mismo servidor, pero la conexión viene de internet (una dirección pública)."""
    return TestClient(cliente.app, client=("93.184.216.34", 50000))


@pytest.fixture()
def sesion_db():
    """Sesión ORM directa, sin pasar por la API — para probar entidades que
    todavía no tienen rutas CRUD (Clase, ContenidoClase, AlumnoCurso)."""
    engine = _crear_motor_prueba()
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Sesion()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def rut_valido():
    return "11222333-9"


@pytest.fixture()
def rut_utp():
    """RUT distinto de rut_valido — evita choques cuando un test crea un
    Usuario con rut_valido Y necesita un token UTP en la misma prueba."""
    return "7654321-6"


@pytest.fixture()
def setup_inicial(cliente, rut_utp):
    """Primera ejecución del servidor: crea el colegio y su UTP vía POST /auth/setup."""
    r = cliente.post(
        "/auth/setup",
        json={"colegio_nombre": "Liceo de Prueba", "rut": rut_utp, "nombre": "UTP Test", "password": "clave-segura-123"},
    )
    assert r.status_code == 201
    return r.json()


@pytest.fixture()
def colegio_id(setup_inicial):
    return setup_inicial["colegio_id"]


@pytest.fixture()
def token_utp(setup_inicial):
    return setup_inicial["access_token"]


@pytest.fixture()
def headers_utp(token_utp):
    return {"Authorization": f"Bearer {token_utp}"}


@pytest.fixture()
def otro_colegio(cliente, setup_inicial):
    """Segundo colegio con su propio UTP, creado directo en la base (la API solo
    permite crear el primero). Devuelve (colegio_id, headers del UTP)."""
    from infraestructura.modelos_orm import Colegio, RolNombre, Usuario, UsuarioRol
    from infraestructura.seguridad import hashear_secreto

    with cliente.sesion() as db:
        colegio = Colegio(nombre="Otro Colegio")
        utp = Usuario(rut="1000005-K", nombre="UTP B", colegio=colegio, password_hash=hashear_secreto("clave-segura-123"))
        utp.roles = [UsuarioRol(rol=RolNombre.UTP)]
        db.add(utp)
        db.commit()
        colegio_id = colegio.id
    r = cliente.post("/auth/login/staff", json={"rut": "1000005-K", "password": "clave-segura-123"})
    assert r.status_code == 200
    return colegio_id, {"Authorization": f"Bearer {r.json()['access_token']}"}
