import asyncio
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from interfaz.api import (
    rutas_auth,
    rutas_bloques,
    rutas_clases,
    rutas_colegios,
    rutas_cursos,
    rutas_grabaciones,
    rutas_usuarios,
)
from servicios import servicio_grabacion

# Orígenes explícitos de desarrollo (nunca "*" en producción, por CLAUDE.md).
# Se amplía cuando exista el frontend real (Vite) y el dominio del túnel.
ORIGENES_PERMITIDOS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


INTERVALO_VIGILANTE_S = 10


async def _vigilante(fabrica):
    """Corte automático de las grabaciones y limpieza: cada pocos segundos revisa las sesiones en curso."""
    while True:
        await asyncio.sleep(INTERVALO_VIGILANTE_S)
        try:
            def pasada():
                with fabrica() as db:
                    servicio_grabacion.vigilar(db, fabrica)

            await asyncio.to_thread(pasada)
        except Exception:  # un fallo de una pasada no debe matar la vigilancia
            traceback.print_exc()


def crear_app(vigilar: bool = False) -> FastAPI:
    """`vigilar` enciende el corte automático de grabaciones (lo usa api.py; los tests lo dejan apagado
    para no tocar la base real)."""

    @asynccontextmanager
    async def ciclo(_app):
        tarea = None
        if vigilar:
            from infraestructura.basedatos import SessionLocal

            with SessionLocal() as db:
                servicio_grabacion.recuperar_al_iniciar(db, SessionLocal)
            tarea = asyncio.create_task(_vigilante(SessionLocal))
        yield
        if tarea:
            tarea.cancel()

    app = FastAPI(title="ClaseAIdia API", lifespan=ciclo)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENES_PERMITIDOS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validacion_sin_eco(_request, exc: RequestValidationError):
        # Por defecto el 422 devuelve el valor recibido ("input"): un PIN o contraseña
        # mal formado viajaría de vuelta y quedaría en cualquier proxy que guarde respuestas.
        errores = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errores)})

    @app.exception_handler(servicio_grabacion.ErrorGrabacion)
    async def _error_grabacion(_request, exc: servicio_grabacion.ErrorGrabacion):
        return JSONResponse(status_code=exc.estado, content={"detail": exc.detalle})

    @app.get("/salud")
    def salud():
        return {"status": "ok"}

    app.include_router(rutas_auth.router)
    app.include_router(rutas_colegios.router)
    app.include_router(rutas_usuarios.router)
    app.include_router(rutas_cursos.router)
    app.include_router(rutas_bloques.router)
    app.include_router(rutas_clases.router)
    app.include_router(rutas_grabaciones.router)

    return app
