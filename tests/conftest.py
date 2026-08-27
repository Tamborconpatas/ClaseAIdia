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

    with TestClient(app) as c:
        yield c


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
def colegio_id(cliente):
    r = cliente.post("/colegios", json={"nombre": "Liceo de Prueba"})
    assert r.status_code == 201
    return r.json()["id"]


@pytest.fixture()
def token_utp(cliente, colegio_id, rut_utp):
    r = cliente.post(
        "/auth/bootstrap-utp",
        json={"rut": rut_utp, "nombre": "UTP Test", "password": "clave-segura-123", "colegio_id": colegio_id},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


@pytest.fixture()
def headers_utp(token_utp):
    return {"Authorization": f"Bearer {token_utp}"}
