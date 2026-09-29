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

- Bootstrap del primer UTP: endpoint auto-limitado `POST /auth/bootstrap-utp` (funciona solo si el colegio aún no tiene UTP).
- Alta de alumno: combinada con "unirse a curso" (`POST /cursos/unirse`) — no hay paso separado de registro.
- Hash: `argon2` vía `passlib`.
- `POST /colegios` y los `GET` de colegios/cursos/bloques quedaron sin autenticación a propósito en esta fase (ver el plan de implementación para el razonamiento) — no es una omisión.

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
- **Nunca PIN ni contraseñas en los logs** del servidor (revisar logging de requests y errores de validación).
- **`.env.example`** sin valores reales junto al `.env` (que ya está en `.gitignore`).
