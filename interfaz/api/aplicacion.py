# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import asyncio
import datetime
import os
import traceback
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from interfaz.api import (
    limite_cuerpo,
    limites,
    rutas_ajustes,
    rutas_auth,
    rutas_bloques,
    rutas_clases,
    rutas_colegios,
    rutas_cursos,
    rutas_estado,
    rutas_grabaciones,
    rutas_usuarios,
)
from servicios import servicio_grabacion, servicio_modelos, servicio_respaldo

# Orígenes explícitos de desarrollo (nunca "*" en producción, por CLAUDE.md).
# Se amplía cuando exista el frontend real (Vite) y el dominio del túnel.
ORIGENES_PERMITIDOS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


INTERVALO_VIGILANTE_S = 10


def _respaldar():
    """Una vez al día (la primera pasada del día) copia la base a CARPETA_RESPALDOS."""
    from infraestructura.basedatos import engine

    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        return
    try:
        servicio_respaldo.respaldar_si_toca(
            Path(engine.url.database), servicio_respaldo.carpeta_de_respaldos(), datetime.datetime.now(),
            int(os.environ.get("DIAS_DE_RESPALDO", servicio_respaldo.DIAS_POR_DEFECTO)),
        )
    except Exception:  # un respaldo fallido no debe frenar la vigilancia de las grabaciones
        traceback.print_exc()


async def _vigilante(fabrica):
    """Corte automático de las grabaciones y limpieza: cada pocos segundos revisa las sesiones en curso."""
    while True:
        await asyncio.sleep(INTERVALO_VIGILANTE_S)
        try:
            def pasada():
                with fabrica() as db:
                    servicio_grabacion.vigilar(db, fabrica)
                _respaldar()

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

    # /docs, /redoc y /openapi.json muestran toda la superficie de la API: solo se publican si quien administra lo pide
    # (API_DOCS=1; `scripts.iniciar` lo hace en desarrollo).
    docs = os.environ.get("API_DOCS") == "1"
    app = FastAPI(
        title="ClaseAIdia API", lifespan=ciclo,
        docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None,
    )
    app.state.vigilando = vigilar  # el panel de estado solo exige el latido de la vigilancia si está encendida

    app.middleware("http")(limites.limitar_por_ip)

    app.add_middleware(limite_cuerpo.LimiteDeCuerpo)

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

    @app.exception_handler(OverflowError)
    async def _numero_fuera_de_rango(_request, exc: OverflowError):
        # Un id como 99999999999999999999 en la URL o en el cuerpo no cabe en un entero de SQLite y llegaba como error 500.
        if "SQLite INTEGER" in str(exc):
            return JSONResponse(status_code=422, content={"detail": "Número fuera de rango"})
        traceback.print_exception(exc)
        return JSONResponse(status_code=500, content={"detail": "Error interno"})

    @app.exception_handler(servicio_modelos.ErrorModelo)
    async def _error_modelo(_request, exc: servicio_modelos.ErrorModelo):
        return JSONResponse(status_code=exc.estado, content={"detail": exc.detalle})

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
    app.include_router(rutas_ajustes.router)
    app.include_router(rutas_estado.router)

    return app
