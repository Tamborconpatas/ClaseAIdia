# Registro de QA

Bitácora de qué se prueba en cada fase del proyecto, complementaria a la suite automatizada en `tests/` (`pytest`). Se actualiza a medida que avanzan las fases de `CLAUDE.md`, para tener evidencia de qué quedó cubierto y qué no en cada versión.

## Cómo correr las pruebas

```bash
transcriptor-env/bin/python -m pytest tests/ -v
```

No toca `escuela.db` (la base de desarrollo real) ni `transcriptions_history.db` — cada test de API usa una SQLite en memoria aislada (`tests/conftest.py`).

## Pipeline de IA (Gradio + Ollama) — validación con datos reales (2026-08-27)

El prototipo Gradio ya se había probado antes solo con audio corto/de prueba. Para esta ronda se descargó un video real de YouTube (una clase grabada tipo curso, ~47MB de audio) usando la propia función `infraestructura/youtube.py` que ya usa la UI, y se corrió todo el pipeline real de punta a punta:

- **Transcripción** (`servicios/servicio_transcripcion.py`, motor `faster-whisper-tiny`, GPU): 37.605 caracteres / 6.579 palabras / 601 segmentos SRT en 40.4s. Confirma que FFmpeg + faster-whisper + formato SRT aguantan un audio largo real, no solo clips cortos.
- **Material de estudio** (`servicios/servicio_material_estudio.py`, `llama3.2:3b` vía Ollama): al ser >6.000 caracteres, activó el chunking map-reduce por primera vez con datos reales — **7 bloques condensados secuencialmente**, resumen + puntos clave + hoja de repaso + 6 tarjetas (`{pregunta, respuesta}`) generados correctamente en 84.9s.

El audio descargado y la transcripción de prueba se borraron después de esta validación (misma política de privacidad que sigue la app: no se guarda audio, y acá tampoco se guardó como dato de prueba permanente).

**No cubierto por esta prueba:** el contenido generado no se guardó en `escuela.db`/`ContenidoClase` — ese pipeline (Gradio) y el backend nuevo (FastAPI) siguen sin conectarse, como ya se documentó arriba.

## Fase 1 — Backend FastAPI y modelo de datos (2026-08-27)

**Automatizado** (`tests/test_validadores.py`, `tests/test_api.py`, 20 tests):
- Validación de RUT: válido con/sin puntos, dígito verificador `K`, dígito verificador incorrecto, formato inválido, vacío.
- CRUD de Colegio: crear, listar, 404 en inexistente.
- Curso: crear (genera `codigo_invitacion` de 6 caracteres), 409 si `colegio_id` no existe.
- Bloque: crear bajo un curso, listar, 409 si `profesor_id` no existe, 422 si `dia_semana` fuera de rango (0-6).
- Usuario: crear con roles, 422 si el RUT es inválido, 409 si el RUT está duplicado, 409 si `colegio_id` no existe, 404 en inexistente.
- `/salud` y `/docs` responden.

**Probado manualmente antes de automatizar** (vía `curl`, ver historial de la sesión): flujo completo colegio → curso → bloque → usuario contra un `escuela.db` real, migrado con Alembic; confirmado que `python app.py` (Gradio) sigue arrancando sin verse afectado por las dependencias nuevas (`sqlalchemy`, `alembic`, `pytest`).

**Modelo ORM directo** (`tests/test_modelo_orm.py`, 8 tests — `Clase`/`ContenidoClase`/`AlumnoCurso` no tienen rutas CRUD todavía, así que se prueban contra la sesión de SQLAlchemy directamente, no vía API):
- `ContenidoClase` guarda y recupera datos con forma real de transcripción (texto largo, SRT multilínea, acentos, `¿¡`, tarjetas como lista de dicts `{pregunta, respuesta}`) sin pérdida — confirmado releyendo desde la base, no solo el objeto en memoria.
- `Bloque.hora_inicio`/`Clase.fecha` se recuperan como `datetime.time`/`datetime.date` reales, no strings.
- Cascadas: borrar un `Bloque` borra sus `Clase`s y `ContenidoClase`; borrar un `Curso` borra sus `Bloque`s.
- Borrar un `Colegio` con `Usuario`/`Curso` dependientes falla (`IntegrityError`) — no hay cascada ahí a propósito, para no destruir datos por accidente.
- `UsuarioRol` no permite el mismo rol dos veces en el mismo usuario, pero sí permite roles distintos (ej. PROFESOR + UTP) en un mismo usuario.
- `AlumnoCurso` no permite que el mismo alumno se una dos veces al mismo curso.

**Migración Alembic** (validado a mano contra una copia descartable, no contra `escuela.db`): ciclo `upgrade head` → `downgrade base` → `upgrade head` limpio, sin errores — confirma que la migración inicial es reversible, no solo que "corrió una vez".

**Fuera de alcance todavía** (no hay nada que probar aún — llega en fases futuras):
- Frontend (Fase 3), control de clase en vivo (Fase 4), cola EDF (Fase 5).
- Integración real con el pipeline de Gradio: nada llena `ContenidoClase` con datos reales todavía — eso es la Fase 4.

## Fase 2 — Autenticación y roles (2026-08-27)

**Automatizado** (`tests/test_auth.py` + extensiones a `tests/test_api.py`, 15 tests nuevos, 43 en total):
- Bootstrap del primer UTP de un colegio; un segundo intento sobre el mismo colegio falla (409).
- Login staff: éxito, RUT inexistente, contraseña incorrecta, y bloqueo real tras 5 fallos seguidos (verificado que incluso la contraseña correcta es rechazada con 429 mientras dura el bloqueo).
- `/cursos/unirse`: alta de alumno nuevo, unión a un segundo curso con el mismo PIN, rechazo (401) con PIN incorrecto sobre una cuenta ya existente, 404 con código de invitación inválido.
- `requiere_rol`: un token de rol ALUMNO no puede crear un Curso (403); todos los endpoints de escritura (`POST /cursos`, `/cursos/{id}/bloques`, `/usuarios`) y `GET /usuarios`/`GET /usuarios/{id}` rechazan sin token (401).
- `UsuarioCrear` rechaza el rol ALUMNO (422) — ese alta es exclusiva de `/cursos/unirse`.

**Probado a mano contra `escuela.db` real** (no la base de pruebas en memoria): se creó un UTP real vía `/auth/bootstrap-utp` y un alumno real vía `/cursos/unirse`, y se inspeccionó la tabla `usuarios` directamente con `sqlite3` — confirmado que `password_hash`/`pin_hash` son hashes `argon2id` reales (`$argon2id$v=19$...`), nunca el valor plano, y que cada tipo de cuenta solo llena el campo que le corresponde (staff sin `pin_hash`, alumno sin `password_hash`).

**Fuera de alcance todavía:**
- Endpoints de lectura (`GET /colegios`, `/cursos`, `/cursos/{id}/bloques`) siguen sin autenticación — decisión consciente de esta fase, documentada en el plan; el enforcement fino de "cada quien ve solo lo suyo" llega con el frontend (Fase 3/4).
- Recuperación de contraseña/PIN olvidado — no está en el alcance de `CLAUDE.md`.

**Advertencias conocidas (no bloqueantes):**
- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` — advertencia de una futura migración de Starlette, no afecta los resultados. Revisar cuando `httpx2` sea estable.
