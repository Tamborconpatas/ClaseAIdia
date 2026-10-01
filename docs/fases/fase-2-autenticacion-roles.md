# Fase 2 — Autenticación y roles (Completada)

Requisito previo cumplido: modelo de datos y backend FastAPI (`Fase 1`, ver `QA.md`). `Usuario` ya tiene las columnas `password_hash`/`pin_hash` en `None`; esta fase las llena y las hace cumplir.

## Qué debe tener

- **Login alumno**: RUT + PIN de 6 dígitos.
  - El PIN lo elige el alumno en su primer ingreso (no lo asigna el UTP) — endpoint separado de "primer ingreso" que fija el PIN una sola vez.
- **Login profesor/UTP**: RUT + contraseña.
- **Hashing**: `passlib` con `bcrypt` o `argon2` para ambos (password y PIN). Nunca texto plano, ni siquiera para el PIN.
- **Sesión**: `PyJWT`, token vía header `Authorization: Bearer <token>` — no cookies (reduce riesgo CSRF). Definir expiración razonable (ej. 8-12h, una jornada escolar).
- **Límite de intentos**: 5 intentos fallidos → bloqueo temporal creciente, tanto en login de alumno como de staff. Requiere columnas nuevas en `Usuario` (ej. `intentos_fallidos`, `bloqueado_hasta`) → nueva migración Alembic.
- **Verificación de rol en el backend**: cada endpoint existente (`/colegios`, `/usuarios`, `/cursos`, `/cursos/{id}/bloques`) debe quedar protegido según corresponda — nunca solo ocultar botones en la UI. Ej: crear Colegio/Usuario/Curso/Bloque debería requerir rol UTP.
  - Implementar como dependencia de FastAPI reutilizable (ej. `requiere_rol(RolNombre.UTP)`), no como chequeos manuales repetidos en cada ruta.
- **Validación de RUT**: ya existe (`nucleo/validadores.py`, Fase 1) — reutilizar, no duplicar.

## Fuera de esta fase

- Frontend de login (Fase 3) — esta fase es solo backend/API.
- Recuperación de contraseña olvidada por correo/autoservicio — no está en el alcance del proyecto, evaluar solo si se pide explícitamente.

## Verificación esperada (hecha, ver `QA.md`)

- Tests pytest: login exitoso y fallido (RUT/PIN o RUT/contraseña incorrectos), bloqueo tras 5 intentos, expiración de token, acceso denegado (403/401) a un endpoint protegido sin el rol correcto o sin token.
- Confirmado a mano contra `escuela.db` real (no solo la base de pruebas en memoria) que un PIN/contraseña nunca aparece en texto plano — solo hashes `argon2id`.

## Decisiones tomadas durante la implementación

- ~~Bootstrap del primer UTP vía `POST /auth/bootstrap-utp`~~ — reemplazado el 2026-10-01 por `POST /auth/setup` (ver más abajo).
- Alta de alumno: combinada con "unirse a curso" (`POST /cursos/unirse`) — no hay paso separado de registro.
- Hash: `argon2` vía `passlib`.
- ~~`POST /colegios` y los `GET` de colegios/cursos/bloques sin autenticación~~ — era a propósito en esta fase, pero se cerró el 2026-10-01 (ver más abajo).

## Decisiones de acceso (2026-10-01)

Tomadas antes de empezar el frontend, porque cambian las rutas que la Fase 3 va a consumir:

- **El primer colegio y su primer UTP se crean en la primera ejecución del servidor**: `POST /auth/setup` (nombre del colegio + RUT, nombre y contraseña del UTP) crea ambos y devuelve el token. Se cierra solo: responde 409 apenas existe un colegio. Reemplaza a `POST /colegios` (eliminada, junto con el listado `GET /colegios`) y a `/auth/bootstrap-utp`. El modo "varios colegios en un servidor" queda fuera de alcance, igual que el modo universidad. Límite conocido: antes de ese primer alta el servidor está abierto, así que hay que hacerlo antes de exponerlo por el túnel (Fase 6).
- **Toda lectura requiere login**: `GET /colegios/{id}` (solo el propio, 404 si no), `GET /cursos`, `/cursos/{id}` y `/cursos/{id}/bloques`. El staff ve los cursos de su colegio; un alumno, solo aquellos a los que está inscrito. Un curso ajeno responde 404, no 403, para no revelar qué ids existen.
- **`GET /cursos/{id}/codigo`**: UTP y profesores del colegio pueden volver a ver el código de invitación (para mostrar el QR en clase). Un alumno no, aunque esté inscrito.
- Siguen públicas, a propósito, solo `/salud`, `GET /auth/estado` (solo un booleano: si el servidor ya fue configurado), `/auth/setup` (se cierra sola), los logins, `/auth/restablecer-pin` y `/cursos/unirse` (el alumno se registra con el código del curso).

## Pendiente agregado después de cerrar la fase

- **Arreglos de seguridad de la auditoría del 2026-09-29** (detalle y reproducción en `QA.md`) — **hechos el mismo día**, con un test de regresión por cada uno en `tests/test_auth.py`:
  - [x] `/cursos/unirse` no debe fijar PIN a un usuario sin rol ALUMNO (hoy permite tomar la cuenta de un UTP) y debe aplicar el mismo contador/bloqueo de intentos que el login.
  - [x] `GET /cursos` sin auth no debe devolver `codigo_invitacion`.
  - [x] Aislamiento por colegio: `crear_usuario`/`crear_curso`/`crear_bloque` (y `profesor_id` del bloque) solo dentro del `colegio_id` del UTP autenticado.
  - [x] PIN exactamente 6 dígitos en `LoginAlumnoIn` y `UnirseCursoIn`.
  - [x] Normalizar RUT (sin puntos, DV en mayúscula) antes de guardar y de buscar.
  - [x] `GET /usuarios/{id}`: solo el propio usuario o staff de su colegio.
  - [x] Sacar `allow_credentials=True` de CORS.
- [x] **Reseteo de PIN por profesor o UTP** (hecho 2026-09-29): `POST /usuarios/{id}/reset-pin` (profesor o UTP del mismo colegio, solo sobre cuentas con rol ALUMNO) invalida el PIN, desbloquea la cuenta y devuelve un **código de un solo uso que vence en 15 minutos** (`VIGENCIA_CODIGO_RESET_MINUTOS`), guardado hasheado. El staff se lo entrega al alumno en persona, y el alumno fija su PIN nuevo en `POST /auth/restablecer-pin` (RUT + código + PIN), que cuenta intentos igual que el login. Conocer el RUT o el código del curso no alcanza para quedarse con la cuenta: login y `/cursos/unirse` rechazan una cuenta con PIN reseteado. Migración `a7e3c91d2b40` (columnas `codigo_reset_hash`, `codigo_reset_vence`).
- [x] **Nunca PIN ni contraseñas en los logs** (verificado 2026-09-29): la API no tiene `print`/`logging` propios y el log de uvicorn (incluso en `debug`) solo registra método, ruta y código — 0 apariciones de contraseñas, PINs o tokens en una prueba real. Además, los 422 ya no devuelven el valor recibido (`input`), para que un PIN mal escrito no viaje de vuelta ni quede en un proxy.
- [x] **`.env.example`** (hecho 2026-09-29) con `JWT_SECRET_KEY`, `SERVER_NAME`, `SERVER_PORT`, `OLLAMA_URL`. Antes nada leía el `.env`: ahora `api.py` y `app.py` lo cargan con `nucleo.configuracion.cargar_env()` (stdlib, sin dependencia nueva; las variables del sistema tienen prioridad).

## Endurecimiento (2026-10-01)

Pedido: contraseñas sólidas e invulnerables a inyección SQL y otras vulnerabilidades. Evidencia y mediciones en `QA.md`; los tests están en `tests/test_seguridad.py`.

- **Contraseña de staff** (`POST /auth/setup`, `POST /usuarios`): 10 a 128 caracteres, al menos 4 caracteres distintos y sin contener el RUT. El login solo impone el tope de 128 (no delata la política y evita gastar argon2 con textos enormes).
- **PIN del alumno**: 6 dígitos ASCII que no sean repetidos (`111111`) ni secuencias (`123456`, `654321`); se filtra al elegirlo (`/cursos/unirse` al crear la cuenta, `/auth/restablecer-pin` sin gastar el código). Los intentos de login siguen limitados a 5 con bloqueo creciente.
- **Inyección SQL**: no hay SQL armado a mano en el backend (todo ORM, con consultas parametrizadas). Un test recorre el código y falla si aparece `text(`, `exec_driver_sql` o `.execute(` fuera de las dos excepciones conocidas (el `PRAGMA` fijo de `basedatos.py` y el historial de Gradio, todo con `?`), y otro envía 10 payloads clásicos a todos los campos de texto verificando que ninguno entrega sesión ni causa un 500, y que se guardan como texto sin ejecutarse.
- **Tokens**: se exigen `exp` y `sub`; solo HS256 (rechaza `alg: none`, otros algoritmos, clave ajena, firma alterada, vencidos). `JWT_SECRET_KEY` de menos de 32 caracteres impide arrancar.
- **RUT registrado vs no registrado**: los logins gastan lo mismo con un RUT inexistente (verificación contra un hash de relleno). Medido: 3 ms contra 57 ms antes; 59 ms ahora.

### Límites conocidos (no corregidos, a propósito)

- **Los tokens no se revocan.** Un token robado sigue valiendo hasta 12 h aunque se resetee el PIN o se bloquee la cuenta. Cerrarlo requiere una columna de "sesiones válidas desde" y su migración.
- **El bloqueo delata cuentas existentes**: tras 5 intentos fallidos un RUT real responde 429 y uno inexistente sigue respondiendo 401. Y el mismo bloqueo permite que alguien deje fuera a un alumno concreto fallando a propósito (el bloqueo crece hasta 60 min).
- **No hay límite por IP**: el bloqueo es por cuenta, así que probar una sola contraseña común contra muchas cuentas no lo activa. Se resuelve mejor en el túnel/proxy (Fase 6).
- `/cursos/unirse` responde 409 cuando el RUT es de personal del colegio (hace falta un código de curso válido para ver esa respuesta).
