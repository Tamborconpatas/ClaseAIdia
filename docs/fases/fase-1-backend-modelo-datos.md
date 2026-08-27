# Fase 1 — Backend FastAPI y modelo de datos ✅ Completada

Requisito previo: Fase 0 (pipeline de IA funcional, pero sin modelo de datos ni backend real).

## Qué debía tener

- Modelo de datos vía SQLAlchemy: `Colegio`, `Usuario`/`Rol` (M2M vía `UsuarioRol`), `Curso`, `AlumnoCurso` (M2M), `Bloque`, `Clase`, `ContenidoClase`.
- Migraciones con Alembic (no editar el esquema a mano).
- Backend FastAPI nuevo y separado del prototipo Gradio (que sigue intacto) — cada uno con su propia base (`escuela.db` vs `transcriptions_history.db`).
- CRUD básico (sin autenticación todavía, eso es la Fase 2) para Colegio, Usuario, Curso, Bloque.
- Validación de RUT chileno (dígito verificador) en el backend.
- CORS explícito (nunca `*`), pensado para el futuro frontend Vite.

## Qué se hizo

Todo lo de arriba, más ajustes que solo aparecieron al probar con datos reales:
- `infraestructura/basedatos.py`, `infraestructura/modelos_orm.py`, `nucleo/validadores.py`, `nucleo/codigos.py` (código de invitación de curso).
- `interfaz/api/` (`aplicacion.py`, `esquemas.py`, `rutas_colegios.py`, `rutas_usuarios.py`, `rutas_cursos.py`), `api.py` como entry point.
- `alembic/` con la migración inicial (8 tablas).
- Suite de pruebas (`tests/`, pytest) nacida en esta fase — se decidió registrar QA automatizado desde acá en adelante, no solo probar a mano.

## Fuera de esta fase

- Autenticación, roles, JWT — Fase 2.
- `Clase`/`ContenidoClase` quedaron solo como modelo ORM, sin rutas CRUD (se llenan naturalmente desde el pipeline real en la Fase 4, no por edición manual).

## Verificación (hecha, ver `QA.md`)

CRUD completo probado (éxito y errores: FK inexistente, duplicados, rangos inválidos), modelo ORM probado directamente con datos con forma real de transcripción (acentos, SRT, tarjetas JSON), cascadas de borrado correctas, migración Alembic reversible (`upgrade` → `downgrade` → `upgrade` limpio), y confirmado que el prototipo Gradio sigue funcionando sin verse afectado por las dependencias nuevas.
