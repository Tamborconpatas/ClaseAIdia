from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from interfaz.api import rutas_auth, rutas_colegios, rutas_cursos, rutas_usuarios

# Orígenes explícitos de desarrollo (nunca "*" en producción, por CLAUDE.md).
# Se amplía cuando exista el frontend real (Vite) y el dominio del túnel.
ORIGENES_PERMITIDOS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def crear_app() -> FastAPI:
    app = FastAPI(title="ClaseAIdia API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ORIGENES_PERMITIDOS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/salud")
    def salud():
        return {"status": "ok"}

    app.include_router(rutas_auth.router)
    app.include_router(rutas_colegios.router)
    app.include_router(rutas_usuarios.router)
    app.include_router(rutas_cursos.router)

    return app
