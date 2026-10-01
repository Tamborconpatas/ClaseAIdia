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

**Reseteo de PIN (mismo día)**: primera versión dejaba que el siguiente login fijara el PIN — riesgo: entre el reseteo y el alumno, cualquiera con el RUT (o con el código del curso vía `/cursos/unirse`, que tenía el mismo hueco) se quedaba con la cuenta. Versión final: el reseteo devuelve un código de un solo uso (15 min, hasheado con argon2) y el PIN nuevo solo se fija en `POST /auth/restablecer-pin`. 5 tests: flujo completo (desbloquea, PIN viejo deja de servir, RUT con puntos y código en minúsculas aceptados, código de un solo uso), el ataque original (login con PIN inventado → 401, `/cursos/unirse` → 409, adivinar el código bloquea al 5° intento → 429), código vencido (16 min → 401), permisos (alumno → 403, UTP de otro colegio → 404) y staff (409, y sin PIN no entra por login alumno). `pytest tests/` **55 passed**. Migración `a7e3c91d2b40` probada `upgrade` → `downgrade` → `upgrade` sobre `escuela.db` (vacía, de desarrollo).

**Logs y `.env` (mismo día)**: API levantada con uvicorn en `--log-level debug` sobre una copia de `escuela.db`, con bootstrap, logins de staff (contraseña buena y mala), unirse a curso, login de alumno (PIN bueno, malo y mal formado): **0 apariciones** de contraseñas, PINs o el token en el log — uvicorn solo registra método, ruta y código. Lo único encontrado: el 422 devolvía el PIN mal formado en `"input"` → handler en `aplicacion.py` que quita `input`/`ctx` de los errores de validación. Además se descubrió que **nada cargaba el `.env`** (no está `python-dotenv`): se agregó `cargar_env()` (stdlib) en `api.py`/`app.py`, `.env.example` en la raíz, y `.env` a `.dockerignore`. Probado de punta a punta: con un `.env` en el directorio de trabajo, `import api` con la salida redirigida carga `JWT_SECRET_KEY` y no se cae. 2 tests nuevos → `pytest tests/` **57 passed**.

**Decisiones de acceso (2026-10-01)**, tomadas antes de la Fase 3 (detalle en `docs/fases/fase-2-autenticacion-roles.md`): `POST /auth/setup` crea el primer colegio + UTP y se cierra solo (409 después), reemplazando `POST /colegios` y `/auth/bootstrap-utp`; `GET /auth/estado` dice si ya está configurado; toda lectura de colegios/cursos/bloques exige login (alumno: solo sus cursos; ajeno → 404); `GET /cursos/{id}/codigo` para staff del colegio. Verificado con un cliente anónimo contra la app: `/colegios/1`, `/cursos`, `/cursos/1`, `/cursos/1/bloques`, `/usuarios`, `/usuarios/1` → 401, segundo setup → 409. Tests: fixtures reescritos sobre `/auth/setup` + un fixture `otro_colegio` que crea el segundo colegio directo en la base (la API ya no lo permite); 11 tests nuevos → `pytest tests/` **64 passed**.

Con esto la Fase 2 queda sin pendientes. Siguen abiertos en la Fase 6: el `UnicodeEncodeError` al arrancar sin `JWT_SECRET_KEY` con salida redirigida (con `.env` completo ya no se dispara, pero el aviso sigue teniendo el emoji)., `fase-4` (borrado de audio en `finally`), `fase-6` (encoding y `.dockerignore`).

## Endurecimiento de contraseñas, inyección SQL y tokens (2026-10-01)

Pedido: que las contraseñas sean sólidas y que no sea posible la inyección SQL ni otras vulnerabilidades. Detalle de qué se hizo y los límites que quedan: `docs/fases/fase-2-autenticacion-roles.md`, sección "Endurecimiento".

**Inyección SQL — auditoría**: se buscó SQL armado a mano en `interfaz/`, `infraestructura/`, `servicios/` y `nucleo/`. Solo hay `PRAGMA foreign_keys=ON` (constante) en `basedatos.py` y el historial del prototipo Gradio, cuyas tres sentencias son constantes o usan `?`. Todo lo demás es ORM. Se dejó un test que lo vigila (`test_no_hay_sql_armado_a_mano_en_el_backend`) y otro que envía 10 payloads clásicos (`' OR '1'='1`, `'; DROP TABLE usuarios; --`, `UNION SELECT`, byte nulo...) a login de staff y alumno, restablecer PIN, setup y unirse (con y sin código válido): ninguno entrega un token ni causa un 500, y los mismos textos guardados como nombre de curso vuelven idénticos (se tratan como datos).

**Hallazgos corregidos**
1. **Sin política de contraseñas**: se aceptaba cualquier contraseña de personal, incluso `x`. Ahora 10-128 caracteres, ≥ 4 distintos y sin el RUT.
2. **Sin tope de largo**: un login con 100 000 caracteres iba a argon2. Ahora 422 antes de hashear.
3. **PIN trivial**: `111111`, `123456`, etc. se podían elegir. Ahora se rechazan al elegir el PIN.
4. **Enumeración de RUT por tiempo de respuesta**: login con RUT inexistente respondía en 3 ms contra 57 ms con un RUT real (mediana de 7, base en memoria). Ahora 59 ms.
5. **`JWT_SECRET_KEY` corta aceptada** sin aviso: ahora impide arrancar con menos de 32 caracteres.
6. **Tokens sin `exp`/`sub` aceptados** si estaban bien firmados: ahora se exigen.
7. El aviso de arranque sin `JWT_SECRET_KEY` llevaba un emoji que hacía fallar la API con la salida redirigida en Windows (pendiente de la Fase 6, cerrado acá).

**Verificación**: `pytest tests/` → **93 passed** (29 tests nuevos en `tests/test_seguridad.py`). Para comprobar que los tests no pasan "en vacío" se revirtió una defensa a la vez (largo mínimo, PIN fácil, `exp` obligatorio, algoritmos permitidos, clave corta, PIN fácil en `/cursos/unirse`): cada reversión hizo fallar exactamente su test, y restaurado vuelve a 93 passed. Tokens probados: otro algoritmo, `alg: none`, clave ajena, sin `exp`, vencido, sin `sub`, basura y firma alterada → todos 401.

**No cubierto** (documentado como límites en la Fase 2): revocación de tokens, bloqueo que delata cuentas existentes, límite por IP, `/docs` abierto. `pip-audit` y `npm audit` siguen pendientes para la entrega final.


## Fase 3 — primer avance del frontend y clases por rol (2026-10-01)

**Qué se agregó**: `frontend/` (Vite + React + TypeScript + Tailwind + shadcn/ui); backend `GET /auth/me`, `GET /clases`, `GET /clases/{id}`; variable `DATABASE_URL` para apuntar a otra base; `scripts/sembrar_demo.py` (base de demostración con colegio, 1 UTP, 4 profesores, 3 alumnos, 2 cursos con horario semanal y 7 clases de ejemplo en los 3 estados).

**Cambio de reglas de visibilidad** (pedido del usuario): el alumno no ve cursos (tiene uno solo); el profesor ve solo los cursos donde dicta; las clases se filtran por rol — alumno: las de su curso con el material ya aprobado; profesor: las de sus bloques en cualquier estado (`procesando` / `por_aprobar` / `publicada`); UTP: todas las del colegio.

**Verificación**: `pytest tests/` → **102 passed** (8 tests nuevos en `tests/test_clases.py`: visibilidad por rol y por colegio, estados, detalle con material, orden por fecha, filtro por curso, cursos del profesor). Con la base de demostración y a través del proxy de Vite se verificó por rol: una alumna de 8°A ve 3 clases (solo publicadas de su curso; no la "por aprobar", ni la "procesando", ni las de 8°B); un profesor de Matemática ve sus 2 clases y sus 2 cursos; uno de Ciencias ve su única clase por aprobar. `npm run build` y `tsc` sin errores.

**No verificado**: la apariencia. La extensión de Chrome no estaba conectada, así que no se hicieron capturas ni pruebas de interacción en navegador; el aspecto en PC y en teléfono lo revisa el usuario en vivo. Tampoco hay tests automatizados del frontend.

**Horario -> clase (2026-10-01)**: al tocar un bloque del horario (alumno o profesor) se abre la clase más reciente de ese bloque entre las que el usuario puede ver; sin ninguna, un aviso. `GET /clases` ahora incluye `bloque_id` (cubierto en `tests/test_clases.py`). Verificado con los datos de demostración, simulando lo que hace el botón: para la alumna de 8°A, 3 bloques abren una clase (Matemática lun 08:00, Lenguaje mar 08:00, Historia jue 09:45) y los otros 27 muestran el aviso — incluidos Ciencias (material por aprobar) e Inglés (procesando), que el alumno no debe ver. No verificado en navegador (extensión no conectada).

**Revisión provisoria del material y nombre del profesor en el horario (2026-10-01)**: pedido del usuario — el profesor puede olvidarse de aprobar. Ahora, pasado el plazo de revisión (24 h desde `generado_en`, configurable con `HORAS_REVISION_PROFESOR`), el material sin aprobar ni retirar se publica como `provisoria` (el alumno lo ve con la advertencia "Sin revisar"); `retirada` nunca se publica sola; el profesor (o UTP) aprueba/retira con `POST /clases/{id}/aprobar|retirar`, y una clase retirada se puede volver a aprobar. `GET /clases` informa `revision_vence` (UTC con zona) mientras el profesor está a tiempo. Migración `b4d2f81c6e17` probada `upgrade` → `downgrade` → `upgrade` (la base de desarrollo no tenía filas, así que el relleno de `generado_en` de filas existentes no se ejercitó). 12 tests nuevos (plazo, provisoria, retirada, plazo configurable, permisos: otro profesor 404, alumno 403, sin sesión 401, otro colegio 404, sin material 409, y que el nombre del profesor viaja en el bloque sin exponer RUT) -> `pytest tests/` **114 passed**. Con los datos de demostración, por rol: la alumna de 8°A ve 3 publicadas y 1 provisoria (Inglés), no ve la "por aprobar" ni la "procesando"; una profesora ve su clase provisoria y su clase retirada; un profesor ve su clase "por aprobar" con el plazo de revisión. Nombre del profesor verificado en la API para la alumna (cada bloque trae su profesor, los recreos y el almuerzo no). No verificado en navegador.

**Teléfono en horizontal (2026-10-01)**: captura del usuario (alumno, ~800 × 380 px): se veía mal porque 800 px superaba el límite de ancho del diseño de PC (768 px) y recibía barra lateral + lista y detalle lado a lado en ~480 px. Corrección: el diseño de PC exige ancho >= 768 px **y** alto >= 480 px (variante `desk`); con menos alto aplica el diseño de teléfono (`short`: barras compactas, pestañas en fila, contenido de máx. 48rem, márgenes `safe-area` para la muesca). Se cambiaron los 72 usos de `md:` por `desk:` (incluidos los campos de texto, que en horizontal quedaban en 14 px y harían zoom en iPhone). `tsc` y `npm run build` sin errores y las dos media queries presentes en el CSS generado. **No verificado visualmente** (sin navegador conectado): el usuario debe confirmar en el teléfono. Límite: un navegador de PC con la ventana de menos de 480 px de alto también verá el diseño de teléfono.

**Verificación visual con el complemento del navegador (2026-10-01)**: se reconectó la extensión de Chrome y por primera vez se vio la interfaz. La ventana del navegador no cambia su viewport al redimensionarla (quedó en 1920 × 895), así que los tamaños de teléfono se reprodujeron cargando la app en un `<iframe>` del tamaño pedido (las media queries se evalúan con el tamaño del marco). Resultados con la sesión de una alumna: **PC** (1920 px): barra lateral, grilla semanal con el profesor bajo cada asignatura y "hoy" marcado; **teléfono horizontal** (820 × 380; el caso del usuario): `desk: false`, `short: true` -> diseño de teléfono compacto, sin barra lateral; se vio que con una sola columna cabían ~1,5 tarjetas, así que en pantallas bajas la agenda pasa a 2 columnas con menos relleno (ahora caben 4, los recreos ocupan el ancho completo y se oculta el título del día, que ya muestra el chip); Clases en horizontal: lista legible y detalle con la advertencia "Material sin revisar" completa; **teléfono vertical** (390 × 780): sin cambios (una columna, pestañas abajo). **No probado en navegador**: la vista de profesor y de UTP (botones aprobar/retirar, crear curso con QR), el primer arranque, y un teléfono real. 

**Revisión en navegador de las vistas de profesor y UTP (2026-10-01)**: con las cuentas de la base de demostración, en PC. **Profesor**: "Mi horario" (solo sus bloques, con curso y sala), Cursos (sus 2 cursos con la asignatura que dicta, "Ver clases" y "Código"), Clases agrupadas por curso con filtro, y el detalle de una clase por aprobar con el aviso del plazo ("antes del viernes 2 de octubre, 11:47") y los botones; **Aprobar y publicar** la pasó a "Publicada" en el detalle y en la lista a la vez y quitó el aviso, y **Retirar** la pasó a "Retirada" con su aviso y dejó solo el botón de aprobar. **UTP**: Cursos (crear un curso lo agrega con su código y QR), Horario con selector de curso y Clases con todas las del colegio en los 5 estados. El enlace del QR (`/?unirse=CODIGO`) abre el registro con el código ya puesto.

Fallos encontrados y corregidos en esa revisión: (1) **la pestaña activa se arrastraba entre sesiones**: al cerrar sesión como profesor y entrar como UTP se aterrizaba en "Clases" y no en la primera pestaña; peor, para un cambio de rol sin esa pestaña (UTP -> alumno) se habría mostrado la vista de Cursos con el menú de alumno. Corregido moviendo ese estado a un componente que solo existe con sesión (`Principal`, con `key` por usuario), así se reinicia solo, incluso si la sesión vence. (2) **`?unirse=` quedaba en la dirección tras iniciar sesión**: al cerrar sesión se volvía a mostrar el formulario de unirse; ahora se limpia al entrar. (3) "1 clases" (singular) y los cursos de Clases se ordenaban por fecha de su última clase, no por nombre. (4) Con el servidor caído el panel decía "Algo salió mal"; ahora dice que el servidor no está disponible (un 5xx sin cuerpo JSON). Verificado en navegador: tras los arreglos, la dirección queda limpia y el UTP empieza en Cursos.

**No probado en navegador**: crear/editar bloques del horario (la grilla editable del UTP aún no existe), la vista en teléfono de profesor y UTP, el primer arranque, y un teléfono real. Los datos de demostración se regeneraron al terminar (las pruebas habían aprobado/retirado una clase y creado un curso).

**Grilla editable del UTP y revisión en navegador de lo pendiente (2026-10-01)**: se construyó la edición del horario (backend `PUT`/`DELETE /bloques/{id}` + editor en pantalla) y se probó todo lo que faltaba salvo un teléfono real.

*Backend*: reglas de horario en `interfaz/api/rutas_bloques.py` (compartidas por crear y editar). 10 tests nuevos (`tests/test_bloques.py`) -> `pytest tests/` **124 passed**; al quitar una a una la protección contra cruces de horario, contra el profesor en dos lugares y contra borrar bloques con clases, falló justo su test.

*Hallazgo*: la regla nueva descubrió que **los datos de demostración eran imposibles**: el 8°B (el horario de 8°A corrido un día) ponía a un profesor en dos cursos a la vez (p. ej. Daniela, viernes 12:15). Lo encontró el editor al intentar crear un bloque ("El profesor ya tiene un bloque a esa hora en el curso 8°B"). `scripts/sembrar_demo.py` ahora arma el 8°B con una búsqueda con retroceso y, al final, comprueba con la misma regla que ningún profesor choque.

*En navegador (PC)*: UTP editó un bloque (sala), vio el rechazo por cruce de horario con el mensaje en el cuadro, eliminó un bloque con la confirmación de dos pasos, tocó una celda vacía (se abre "Nuevo bloque" con día y hora ya puestos) y lo creó con profesor asignado; un curso nuevo sin bloques ofrece "Agregar el primer bloque". *Primer arranque* (servidor con base vacía en el puerto 8002 y un segundo frontend en el 5174, ya detenidos): validaciones en pantalla (campos vacíos, RUT inválido, contraseñas distintas), alta correcta entrando como UTP con el estado "Sin cursos", y el servidor quedó `configurado: true` (el alta se cierra sola).

*En navegador (teléfono, marco de 390 × 780)*: UTP — agenda con bloques tocables y recreos como filas, y el editor como hoja desde abajo (la hoja se abrió; no se editó ahí); en teléfono solo se ve el botón "Agregar bloque el <día>" (el de PC queda oculto). Profesor — "Mi horario" (sin su nombre, con curso y sala), Cursos, y la clase por aprobar con el aviso del plazo y los botones. Entrada/unirse con el código precargado.

*QR*: se verificó decodificando la imagen (matriz de módulos leída del navegador, decodificada con `jsqr` en Node): contiene `http://localhost:5173/?unirse=DEMO8A`, es decir la dirección con que se abrió la app + el código. Con `localhost` un teléfono no puede abrirlo; se agregó un aviso en pantalla.

*No probado*: un teléfono real (toques, teclado, muesca), editar un bloque desde la hoja del teléfono, aprobar/retirar tocando en el teléfono (se vio la pantalla, no se pulsó), y el primer arranque en teléfono. Los datos de demostración se regeneraron.

**Jornadas largas (2026-10-01)**: pedido del usuario — el horario no debe tener restricciones de horas (hay colegios de 8:30 a 18:15) y debe adaptarse sin alargar la tabla. Revisión: no existía ninguna restricción real (el backend solo exige que el término sea posterior al inicio; los `08:00` del código son valores sugeridos por defecto); lo que fallaba era el diseño, pensado para la jornada corta de la demo. Se agregó 3°M a los datos de demostración (15 bloques al día de 8:30 a 18:15, viernes hasta las 15:45, con su propio profesorado) y se midió en el navegador: la grilla ocupaba ~1100 px y obligaba a bajar (página de 1406 px en una ventana de 895); con la grilla densa cuando hay más de 10 filas, la tabla mide **735 px** y la jornada completa cabe en una pantalla, con asignatura, profesor y sala en cada bloque, el encabezado de los días fijo (`sticky`), el viernes corto con sus celdas libres y la clase en curso resaltada. Test nuevo (`test_el_horario_no_restringe_las_horas_de_la_jornada`: 14 bloques de 00:15 a 23:59, incluidos 8:30–18:15, se aceptan todos). No verificado: la vista de teléfono con una jornada larga (la agenda es una lista por día y solo crece hacia abajo).

## Réplica de lo que faltaba por ver, y cierre de la sesión de la Fase 3 (2026-10-01)

Pedido del usuario: replicar lo que no se había visto. Todo en navegador (extensión de Chrome), con un marco `<iframe>` del tamaño de un teléfono porque la ventana no cambia de viewport (las media queries se evalúan con el tamaño del marco); datos de la base de demostración.

- **Agenda de teléfono con jornada larga** (alumna de 3°M, 390 × 780): 15 elementos el jueves (12 clases + 3 recreos/almuerzo), "Alumno · 3°M", marca "Ahora" en la clase en curso, y al llegar al final la última tarjeta (17:30–18:15) queda **48 px por encima** de la barra de abajo (medido), o sea no la tapa.
- **Editar un bloque desde la hoja del teléfono** (UTP): un toque en la tarjeta abre "Editar bloque" con sus datos; se cambió la sala a "Lab 2", se guardó y la tarjeta mostró "Lab 2". (Un toque mal dirigido abrió la lista del campo "Día": se cerró con Escape sin perder lo escrito; error del script de prueba, no de la interfaz.)
- **Aprobar y retirar con toques en teléfono** (profesor): "Aprobar y publicar" -> "Publicada" y queda solo "Retirar"; "Retirar" -> "Retirada" con el aviso rosa y el botón de aprobar a lo ancho.
- **Primer arranque en teléfono** (servidor con base vacía en el puerto 8002 y un segundo frontend en el 5174, ya detenidos): vertical 390 × 780, el formulario completo cabe con el botón visible; horizontal 820 × 380, cabecera compacta y formulario centrado con desplazamiento.

**Comprobaciones del checklist del proyecto**: `npm audit` -> 0 vulnerabilidades; sin `dangerouslySetInnerHTML` ni `innerHTML` en el código (el único resultado de la búsqueda es un comentario); sin llamadas a servicios externos ni trackers; favicon, `robots.txt` y `noindex` presentes.

**Estado final de pruebas**: `pytest tests/` -> **125 passed**; `tsc`, `oxlint` y `npm run build` sin errores. **Sigue sin probarse**: un teléfono físico (teclado, muesca, toques reales); no hay tests automatizados del frontend; la revisión formal de contraste y lector de pantalla; `pip-audit` (aún no instalado).

**Nota de método**: los toques en el marco se hicieron con clics reales del navegador; las coordenadas del marco no necesitan el factor de escala de la captura (un primer intento con el factor erró el botón). Algunos pasos (guardar en la hoja, abrir filas de lista) se hicieron con clics programáticos; los flujos completos se verificaron por el resultado en pantalla.

## Gestión del UTP y del profesor: alumnos, resetear PIN, cursos y profesores (2026-10-01)

*Backend* (`tests/test_gestion.py`, 6 tests; `pytest tests/` **131 passed**; al quitar la restricción del profesor para resetear PIN y la que impide borrar un curso con alumnos, falló justo su test): `GET /cursos/{id}/alumnos` (UTP y profesor del curso; solo id, nombre y RUT), `PUT` y `DELETE /cursos/{id}` (solo UTP; solo se borra un curso vacío), y un profesor solo resetea el PIN de alumnos de sus cursos.

*En navegador (PC)*: **Alumnos y resetear PIN** — el UTP abre "Alumnos" de 8°A (ordenados por nombre, con RUT), "Resetear PIN" pide confirmación y entrega el código de un solo uso con su hora de vencimiento y las instrucciones. **Recorrido completo**: con ese código, "Olvidé mi PIN" dejó a la alumna elegir un PIN nuevo; comprobado en el servidor que el PIN nuevo entra (200), el viejo no (401) y reusar el código da "Código inválido o vencido". **Cursos**: renombrar actualiza el nombre; eliminar un curso con bloques y alumnos muestra el motivo y lo conserva; un curso vacío recién creado se elimina. **Profesores** (pestaña nueva del UTP): las validaciones salen en pantalla (nombre, RUT, contraseña), el alta muestra el mensaje de éxito, el profesor aparece en la lista y el servidor confirma que puede entrar con la contraseña dada.

*Incidentes de la prueba (no del producto)*: (1) el servidor de desarrollo del puerto 5173 quedó sin el proxy y devolvía la página principal para `/api/...`; mis comprobaciones de "200" no lo detectaron porque ese código también lo devuelve la página. Para verificar el proxy hay que mirar el **cuerpo** (`{"status":"ok"}`), no el código. (2) Una extensión del navegador dio por ratos "Cannot access a chrome-extension:// URL of different extension" al ejecutar scripts y sacar capturas; un script que dio ese error sí se ejecutó, lo que confundió un paso. Se verificó por el estado del servidor. En esta parte no se pudo sacar captura de la pestaña Profesores (se comprobó el contenido de la página).

*No probado*: la vista de estas pantallas en teléfono, y borrar o desactivar profesores (no existe todavía).

## Recuperación de contraseña del personal, sobre todo del UTP (2026-10-01)

Pedido del usuario: si el UTP olvida su contraseña "deberíamos colocar algo, porque ese es el rol más importante". Hasta entonces **no había ninguna forma de recuperar la contraseña del personal**: si el único UTP la olvidaba, nadie podía ayudarlo (y tampoco a un profesor). Sin correo (el proyecto no usa servicios externos) se hicieron dos vías: (1) otro UTP genera un código de un solo uso (`POST /usuarios/{id}/reset-password`) y la persona elige una contraseña nueva con él (`POST /auth/restablecer-password`); (2) último recurso, desde la consola del servidor: `python -m scripts.restablecer_utp <RUT>`, seguro porque exige acceso al PC del colegio.

*Hueco cerrado de paso*: `restablecer-pin` y el login de alumno no comprobaban el rol; con códigos para el personal, un profesor o UTP habría podido ponerse un PIN de 6 dígitos en su cuenta. Los códigos de PIN (alumnos) y de contraseña (personal) ya no se cruzan.

*Backend*: 18 tests (`tests/test_recuperacion.py`) -> `pytest tests/` **154 passed**; al quitar cada defensa (rol en restablecer-pin, rol en restablecer-password, "no resetear la propia") falló su test. La consola, además de su función, se probó como programa sobre una copia de la base de demostración en sus cuatro casos: RUT que no es de un UTP, contraseñas distintas, contraseña débil y el caso correcto (la anterior deja de servir). Hallazgo: en Windows `getpass` lee del teclado y no de una tubería (mi primera prueba se colgó); ahora la herramienta lee de la entrada estándar cuando no hay consola interactiva.

*En navegador (PC)*: la pestaña "Profesores" pasó a **Personal** (profesores y UTP, con rol elegible al agregar). Con la única UTP (Carolina) la nota dice "hoy eres el único UTP, así que agrega a otro" y la consola del servidor; al agregar un segundo UTP (Ricardo, entra como UTP, comprobado) la nota pasa a "pídeselo a otro UTP". Ricardo no ve el botón de reseteo en su propia fila; genera el código de Carolina con confirmación, vencimiento e instrucciones. Carolina, desde la pantalla de entrada ("Olvidé mi contraseña": RUT + código + contraseña nueva), recuperó su cuenta: confirmado en el servidor que la contraseña vieja da 401, la nueva 200 y el código no se reutiliza. El resto de la pantalla (mensaje de contraseñas distintas, estado final) no pudo leerse: la extensión del navegador devolvió "Cannot access a chrome-extension:// URL" en esa lectura, aunque el script anterior sí se había ejecutado.

*No probado*: estas pantallas en teléfono. *Límites*: las sesiones ya abiertas de una cuenta siguen válidas hasta 12 h tras cambiar la contraseña (no hay revocación de tokens; Fase 6). No hay forma de desactivar o borrar personal todavía.

## Edición del material por el profesor (2026-10-01)

*Backend* (`PUT /clases/{id}/contenido`; 5 tests nuevos; `pytest tests/` **136 passed** al momento del commit del backend): corrige resumen, puntos clave, hoja de repaso y tarjetas; la transcripción no se edita; no cambia el estado; solo el profesor de la clase o el UTP. Al quitar las validaciones fallan sus tests. Un test mío tenía una aserción vacía (`... or True`) que se detectó al revisarlo y se reemplazó por una comprobación real (los rechazos no cambian el material).

*En navegador (PC, profesor)*: sobre una clase **publicada** se abre "Editar material"; al guardar con una tarjeta vacía avisa "Cada tarjeta necesita pregunta y respuesta (o quítala)"; se agregó una tarjeta, se quitó la primera, se cambió el resumen y se guardó: el detalle mostró el resumen nuevo con 3 tarjetas y el estado siguió "Publicada". Comprobado después en el servidor, como la alumna: ve el resumen corregido, las tarjetas nuevas (sin la quitada) y la transcripción intacta. *No probado*: el editor en teléfono (los campos usan 44 px y 16 px de letra, pero no se vio), ni editar una clase "por aprobar" desde la pantalla (cubierto por un test del backend).

## Páginas de privacidad, términos y contacto (2026-10-01)

Rutas públicas `#/privacidad` y `#/terminos` (con hash, para no depender de cómo se sirva el sitio), con enlaces en el pie de la pantalla de entrada y de cada pantalla con sesión. Son un **borrador** (lo dice la propia página): describe cómo funciona el sistema —datos que se guardan, que el audio nunca se guarda, que el PIN y la contraseña se guardan cifrados, quién ve qué, el material "sin revisar", menores y consentimiento de apoderados, derechos— pero un texto sobre datos de menores debe revisarlo el colegio o quien corresponda antes del piloto. El **medio de contacto real no se inventó**: se toma de `VITE_CONTACTO` (ver `frontend/.env.example`); sin él, la página dice que se consulte a UTP y que falta configurarlo. Verificado en navegador: ambas páginas (6 y 5 secciones, aviso de borrador, texto de contacto alternativo), la navegación entre ellas con el enlace, y los enlaces presentes con sesión (profesor) y sin sesión; y que compilando con `VITE_CONTACTO` el valor aparece en el sitio y sin él no. *No probado*: en teléfono; la redacción legal (pendiente de revisión humana); el contacto real (pendiente de que el equipo lo configure).

## Auditoría de accesibilidad con axe-core (2026-10-01)

Se agregó `axe-core` como dependencia de desarrollo y se corrió (reglas WCAG 2.0/2.1 A y AA) sobre las pantallas en el navegador: entrada (todas sus variantes), alumna, profesor y UTP (Cursos con código y QR, alumnos con confirmación de reseteo, Horario, editor de bloque abierto, Personal con confirmación, Clases) y las páginas de privacidad y términos. *Hallazgo*: el código QR no tenía texto alternativo (`svg-img-alt`); se le puso título y se comprobó que desaparece. Resto: **0 violaciones**. *Control*: se insertó a propósito un botón sin nombre, una imagen sin alt y texto de bajo contraste, y axe detectó los tres, así que el "0" no es una herramienta ciega. *Límite*: axe cubre solo lo que se puede comprobar automáticamente (suele ser un tercio de los problemas); no sustituye una prueba con lector de pantalla ni con teléfono real.

## Pruebas automáticas del frontend (2026-10-01)

Se agregó `vitest` (`npm test` en `frontend/`): 15 pruebas sobre las utilidades que duplican reglas del backend (`lib/rut.ts`, `lib/validar.ts`, `lib/horario.ts`): dígito verificador del RUT (incluida la K), formato y envío al API, PIN (largo, repetidos, secuencias ascendentes y descendentes), contraseña (10–128 caracteres, repetitiva, RUT con y sin puntos), conversión y orden de horas. Su objetivo es que el cliente no se desvíe del backend, que es quien manda. *Mutaciones*: se alteró una regla a la vez (largo mínimo, repetitiva, secuencia descendente, RUT con puntos, módulo del dígito verificador, K) y en las seis falló su prueba; la primera vez "RUT con puntos" pareció sobrevivir, pero era mi `sed` que no había aplicado el cambio: reaplicado bien, falló como debía. `npm run build` y `npm run lint` siguen igual (solo los avisos previos). *No cubierto*: componentes (siguen probándose en el navegador); la paridad con el backend se revisó leyendo las reglas, no se ejecuta contra él.
