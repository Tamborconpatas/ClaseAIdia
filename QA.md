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

## Instalación desde cero como usuario nuevo (2026-09-03)

Se siguió el README literalmente en una máquina Linux limpia (Nobara/Fedora 44, sin Docker/Ollama/venv previos) para medir qué tan "sin fricción" es la instalación real — no solo si el código corre, sino si el proceso documentado alcanza para un usuario nuevo sin ayuda. Resultado: la app terminó levantando correctamente (`python app.py` → interfaz Gradio en `http://127.0.0.1:7862`, HTTP 200, config y DB del historial generados solos), pero el camino documentado en ese momento no llegaba solo — se encontraron y corrigieron 3 problemas:

1. **`numpy==1.26.4` no soporta Python 3.14+.** El único Python del sistema de prueba era 3.14 (recién liberado); `numpy` no tiene wheel para esa versión y falla al compilar desde fuente por falta de `python3.14-devel`. No había ninguna nota de versión mínima/máxima de Python en el README. **Fix**: se agregó la restricción "Python 3.10 a 3.13" como paso 0 en `README.md` y `docs/Notas_de_Instalacion.md`, con el comando de instalación de una versión soportada por distro. Se resolvió instalando `python3.12` aparte (`sudo dnf install python3.12 python3.12-devel`) y creando el venv con ese binario. **Corrección (2026-09-04)**: ese rango estaba mal — nunca se probó Python 3.13 realmente, solo se asumió que funcionaba. Verificando después contra los archivos publicados en PyPI, `numpy==1.26.4` tampoco tiene wheel para 3.13 en ningún sistema operativo (solo publica `cp39` a `cp312`). El rango correcto y ya corregido en ambos README es **Python 3.10 a 3.12**.
2. **`deepfilternet` rompía la instalación completa.** Es una dependencia usada solo por el modo opcional `'deepfilter'` de `infraestructura/mejorador_audio.py` (que ya la importa de forma perezosa y cae a otros modos si falta), pero al estar listada sin marcar en `requirements.txt`, su dependencia `deepfilterlib` (compila una extensión nativa en Rust, sin Cargo instalado por defecto) hacía fallar `pip install -r requirements.txt` completo — ni gradio, ni fastapi, ni sqlalchemy llegaban a instalarse. **Fix**: se sacó `deepfilternet` de `requirements.txt` a un archivo aparte opcional (`requirements-deepfilter.txt`), documentado en ambos README como paso opcional que requiere Rust/Cargo.
3. **La instalación "sin GPU" descargaba ~1.5GB de paquetes CUDA de todos modos.** `pip install torch==2.13.0 torchaudio==2.11.0` sin índice explícito resuelve, incluso en la rama "Sin GPU" del README, a una build de PyPI con CUDA 13 empaquetado (`nvidia-cublas`, `nvidia-cudnn`, etc.) — el mismo tipo de problema que el propio `requirements.txt` ya advertía para el caso GPU NVIDIA, pero también aplicaba al caso CPU. **Fix**: se cambió el comando "Sin GPU" en ambos README a `--index-url https://download.pytorch.org/whl/cpu` (build `+cpu` real, confirmada disponible para `torch==2.13.0`/`torchaudio==2.11.0` en `cp312`), evitando la descarga innecesaria en el hardware modesto que es el objetivo del proyecto.

**No cubierto por esta prueba:** instalación en Windows (el target real de despliegue) ni la vía Docker Compose — solo se probó el camino nativo en Linux.

## Instalación desde cero en Windows con Conda (2026-09-04)

Validación en Windows 11 real con GPU dedicada (NVIDIA GeForce RTX 2050, driver 32.0.16.1664), sobre un entorno Conda (`transcriptor-env`, Python 3.12.14) ya preparado por una sesión anterior en la misma máquina cuyas notas habían quedado sin commitear. Antes de confiar en esas notas se re-verificó cada afirmación contra el sistema real y contra PyPI — dos resultaron falsas (ver abajo), el resto se confirmó corriendo los comandos de verdad:

1. **Índice de git corrupto al mover el proyecto de Linux a Windows.** `.git/index` quedó en 0 bytes (probablemente por cómo se sincronizó la carpeta entre máquinas) — cualquier comando de git fallaba con `index file smaller than expected`. **Fix**: se borró el índice vacío y se reconstruyó desde HEAD (`rm .git/index && git reset`), que no toca el working tree ni pierde historial — solo regenera el cache de staging.
2. **Restricción de Python confirmada, pero con una razón mal atribuida.** El borrador previo (sin commitear) afirmaba que además de `numpy`, `ctranslate2` carecía de wheels de Windows para 3.13+, y que había "incompatibilidades de PyTorch y PyInstaller" — **ambas afirmaciones eran falsas**: se verificó contra los archivos publicados en PyPI que `ctranslate2==4.8.1` sí publica wheels de Windows para 3.13 e incluso 3.14. El único bloqueador real, en Windows igual que en Linux, es `numpy==1.26.4` (sin wheel para 3.13+ en ningún SO). Se corrigió el texto en `README.md`, `docs/Notas_de_Instalacion.md` y `docs/Guia_Instalacion_Windows.md` para no seguir citando una razón que no es cierta.
3. **`docs/Guia_Instalacion_Windows.md` afirmaba que `app.spec` y `construir_exe.py` ya "estaban preparados en el repositorio"** para el empaquetado con PyInstaller — falso, ninguno de los dos archivos existe (`ls` lo confirma, y no están en ningún commit). Es trabajo de la Fase 6 (que va después de Frontend y Control de Clase en Vivo), no algo ya hecho. Se corrigió la guía para dejarlo marcado como pendiente en vez de darlo por completado.
4. **PyTorch con CUDA 12.6, verificado de verdad**: con `torch==2.13.0`/`torchaudio==2.11.0` instalados vía `--index-url https://download.pytorch.org/whl/cu126` en el env existente, `torch.cuda.is_available()` devuelve `True` y `torch.cuda.get_device_name(0)` reconoce la RTX 2050; `infraestructura.hardware.detect_gpu_vendor()` devuelve `'nvidia'`.
5. **Pruebas automatizadas, corridas de verdad**: `python -m pytest tests/ -v` → **43 passed, 3 warnings en 3.85s** (mismos warnings conocidos que en Linux, ver más arriba).
6. **La app arranca y sirve, verificado con una petición HTTP real**: `python app.py` (mismo entry point que Linux) levantó Gradio en `http://127.0.0.1:7862`; `Invoke-WebRequest` contra esa URL devolvió `HTTP 200`.
7. **FFmpeg vía `winget install Gyan.FFmpeg`**: confirmado que instala y queda disponible en el PATH tras reiniciar la terminal (reemplaza la recomendación anterior de Chocolatey en `docs/Notas_de_Instalacion.md`, no verificada). El código (`infraestructura/herramientas_ffmpeg.py`) sigue buscando `ffmpeg` solo en el PATH del sistema — el borrador previo afirmaba (incorrectamente) que ya buscaba una copia local junto al ejecutable. Ese ajuste no está hecho; queda anotado como pendiente de la Fase 6 en `docs/Guia_Instalacion_Windows.md`.

**No cubierto por esta prueba:** instalación desde cero real (sin un Conda/env ya preparado de antemano) — se reusó el entorno que ya existía en la máquina en vez de crear uno nuevo desde el Windows recién instalado. Los pasos de `docs/Guia_Instalacion_Windows.md` para crear el entorno están documentados pero no se re-ejecutaron paso a paso en esta sesión.

## Instalación sin Conda (solo Python) en Windows (2026-09-05)

El usuario pidió explícitamente que la instalación fuera fácil para alguien que solo tiene Python, no Conda. Se probó el camino alternativo de punta a punta:

1. **Python 3.12 "de verdad" (python.org, sin Conda), instalado sin admin**: `winget install --id Python.Python.3.12 -e --scope user` — quedó instalado en `%LOCALAPPDATA%\Programs\Python\Python312`, sin tocar Program Files. La máquina de prueba ya tenía además un Python 3.14 (de la Microsoft Store) y un 3.14.7 gestionado por `uv` — confirma que `py -0p` es necesario para elegir la versión correcta cuando hay varias instaladas, no alcanza con `python` a secas.
2. **Entorno con `venv` puro (sin Conda) en un venv nuevo**: `python -m venv`, luego `pip install torch==2.13.0 torchaudio==2.11.0 --index-url .../cu126`, luego `pip install -r requirements.txt` — **ambos completaron al 100% sin errores ni compilador C**, igual que con Conda. `pytest tests/ -v` → **43 passed** de nuevo. `detect_gpu_vendor()` → `nvidia`. `python app.py` levantó Gradio y sirvió correctamente. **Conclusión: Conda nunca fue necesario** — el README y `Notas_de_Instalacion.md` sobre-recomendaban Conda como camino principal en Windows; se corrigió para que `venv` (stdlib, sin instalar nada extra) sea el camino principal y Conda quede como alternativa para quien ya lo use.


## Instalación en Windows sin GPU funcional + auditoría de seguridad (2026-09-29)

**Instalación**: Windows 11 con el driver NVIDIA sin responder (`nvidia-smi` falla) → se instaló la vía CPU: venv nuevo con Python 3.12.10, `torch==2.13.0`/`torchaudio==2.11.0` desde `--index-url .../whl/cpu`, luego `pip install -r requirements.txt` — ambos sin errores. `pytest tests/` → **43 passed**. `detect_gpu_vendor()` → `none`. `alembic upgrade head` creó `escuela.db` limpia. `uvicorn api:app` respondió `/salud` → `{"status":"ok"}` y `python app.py` sirvió Gradio (HTTP 200). Ollama instalado (0.34.2) pero no corriendo — la generación de material de estudio no se probó en esta sesión.

**Problema de instalación encontrado**: con la salida redirigida (archivo, servicio, o un futuro `.exe` sin consola) la API **no arranca**: el `print` con emoji ⚠️ de `infraestructura/seguridad.py:17` lanza `UnicodeEncodeError` (cp1252) al importar, cuando `JWT_SECRET_KEY` no está definido. En una consola interactiva no se nota. Se esquivó con `PYTHONIOENCODING=utf-8`; sin corregir.

**Auditoría contra el checklist del proyecto** (sin modificar código). Hallazgos reproducidos con un script contra SQLite en memoria (misma técnica que `tests/conftest.py`), no contra datos reales:

1. **Crítico — toma de cuenta de staff sin credenciales**: `GET /cursos` es público y devuelve `codigo_invitacion`; `POST /cursos/unirse` con ese código + el RUT de un UTP (que tiene `pin_hash = None`) le fija un PIN y devuelve un token con roles `['ALUMNO','UTP']`. Con ese token, `GET /usuarios` → 200.
2. **Crítico — fuerza bruta de PIN**: `/cursos/unirse` verifica el PIN de un alumno existente sin contar intentos ni aplicar el bloqueo de 5 intentos del login. 8 intentos fallidos seguidos, el 9° entró.
3. **Crítico — sin aislamiento entre colegios**: un UTP del colegio B creó un UTP en el colegio A (201). `crear_usuario`, `crear_curso` y `crear_bloque` aceptan cualquier `colegio_id`/`curso_id` sin compararlo con el colegio del UTP autenticado; como `POST /colegios` y `bootstrap-utp` son públicos, cualquiera puede hacerse UTP de un colegio propio y usar ese hueco.
4. **Medio — PIN sin validar**: se aceptó un PIN vacío (200); no se exige 6 dígitos.
5. **Medio — RUT sin normalizar**: `12.345.678-5` y `12345678-5` crean dos cuentas distintas.
6. **Medio — `.env` entraría a la imagen Docker**: `.dockerignore` no lo excluye y el Dockerfile hace `COPY . .`.
7. **Medio — `GET /usuarios/{id}`** solo exige estar autenticado: un alumno puede ver RUT/nombre de cualquier usuario.
8. **Menor**: `allow_credentials=True` en CORS innecesario (sesión por header); en Gradio el audio se borra después del bucle, no en un `finally` — si se cancela la transcripción a mitad, el archivo queda en disco.

**Confirmado bien**: hash argon2, JWT con expiración (12h), roles verificados en backend vía `requiere_rol`, sin SQL armado a mano (solo ORM y consultas fijas), dígito verificador de RUT, `.env`/`*.db` en `.gitignore` y nada de eso commiteado, Gradio escuchando solo en `127.0.0.1`.

**Arreglos (mismo día)**: 1-5, 7 y CORS corregidos. `/cursos/unirse` rechaza con 409 un RUT sin rol ALUMNO y aplica el mismo bloqueo de intentos que el login; `GET /cursos` ya no devuelve el código (solo la respuesta de `POST /cursos`, que ve el UTP que lo crea); crear usuario/curso/bloque fuera del colegio del UTP → 403, y `GET /usuarios` solo lista su colegio; PIN exactamente 6 dígitos ASCII; RUT normalizado (`nucleo/validadores.normalizar_rut`) al guardar y al hacer login; `GET /usuarios/{id}` → solo uno mismo o staff del mismo colegio (404 si no, para no revelar ids); sin `allow_credentials` en CORS. Dos tests existentes cambiaron de 409 a 403 (colegio `9999` ahora es "colegio ajeno" antes que "inexistente"). 7 tests de regresión nuevos → `pytest tests/` **50 passed**. Re-ejecutado el script de reproducción: el ataque 1 ya falla en el primer paso (sin código en `GET /cursos`).

Seguimiento de lo restante: `docs/fases/fase-2-autenticacion-roles.md` (reseteo de PIN, logs, `.env.example`), `fase-4` (borrado de audio en `finally`), `fase-6` (encoding y `.dockerignore`).
