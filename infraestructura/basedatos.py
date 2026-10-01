import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Variable de entorno solo para apuntar a otra base (p. ej. la de demostración).
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./escuela.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _activar_foreign_keys(conexion_dbapi, _):
    # SQLite no valida FKs por defecto; sin esto las relaciones del modelo
    # (Curso.colegio_id, Bloque.curso_id, etc.) no se harían cumplir.
    cursor = conexion_dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def obtener_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
