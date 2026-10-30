# Demostración de ClaseAIdia — cómo iniciarla y con qué usuarios entrar

Todos los datos son **de ejemplo** (los crea `scripts/sembrar_demo.py`); no hay personas ni claves reales. La base de demostración es `escuela_demo.db` y **no toca la base real** (`escuela.db`).

## Cómo iniciar

Doble clic en **`iniciar.bat demo`** (o `python -m scripts.iniciar demo`). Rehace la base de ejemplo, levanta el servidor y la interfaz, y abre `http://localhost:5173`. Se detiene con Ctrl+C o cerrando la ventana.

La demo se usa en el mismo PC (el micrófono funciona en `localhost`). Grabar con un celular exige https y se prueba con `iniciar.bat celular`, que usa la base real, no la demo.

## Claves

| Quién | Clave |
|---|---|
| **Todo el personal** (UTP y los 7 profesores) | contraseña **`demo-clave-2026`** |
| **Los 4 alumnos** | PIN **`482915`** |

- **Personal:** pestaña **«Profesor o UTP»** → RUT + contraseña.
- **Alumnos:** pestaña **«Soy alumno»** → RUT + PIN.

## Usuarios

| Rol | RUT | Nombre | Dicta o cursa |
|---|---|---|---|
| **UTP** | `11111111-1` | Carolina Rojas | Administra horario, cursos, personal, estado y ajustes |
| Profesor | `12345678-5` | Marcos Fuentes | Matemática en 8.°A y 8.°B; Ed. Física |
| Profesor | `13456789-9` | Paula Soto | Historia y Lenguaje en 8.°A y 8.°B |
| Profesor | `14567890-0` | Andrés Vera | Ciencias y Ed. Física en 8.°A y 8.°B |
| Profesor | `15678901-1` | Daniela Muñoz | Inglés, Artes y Música en 8.°A y 8.°B |
| Profesor | `16789012-1` | Ricardo Lagos | Matemática y Física en 3.°M |
| Profesor | `17890123-0` | Carmen Ibáñez | Lenguaje, Historia y Filosofía en 3.°M |
| Profesor | `18901234-9` | Tomás Bravo | Biología, Química, Inglés, Ed. Física y Taller PAES en 3.°M |
| Alumno | `21000001-1` | Sofía Contreras | 8.°A |
| Alumno | `21000002-K` | Matías Pizarro | 8.°A |
| Alumno | `21000003-8` | Valentina Araya | 8.°B |
| Alumno | `21000004-6` | Camila Soto | 3.°M (jornada de 8:30 a 18:15) |

## Cursos y códigos de invitación

Sirven para probar **«Únete a tu curso»** (un alumno nuevo ingresa el código, su RUT y elige su PIN):

| Curso | Código |
|---|---|
| 8.°A | `DEMO8A` |
| 8.°B | `DEMO8B` |
| 3.°M | `DEMO3M` |

## Qué mostrar con cada rol

- **UTP (`11111111-1`):** «Horario» (grilla editable con recreos y almuerzo), «Cursos» (alumnos y códigos), «Personal» (crear, desactivar y restablecer claves), «Clases» (todas las del colegio), **«Estado»** (cola de procesamiento, Ollama, disco, respaldos, memoria, avisos) y «Ajustes» (fotos de la pizarra).
- **Profesor (p. ej. `12345678-5`):** «Mi horario», «Clases» (revisar, editar con el editor visual de fórmulas y diagramas, aprobar o retirar) y **«Grabar»**.
- **Alumno (p. ej. `21000001-1`):** su horario personal y el material de las clases publicadas (resumen, puntos clave, hoja de repaso, tarjetas, mapa conceptual), con descarga a PDF o Word.

La demo trae **9 clases de ejemplo** en todos los estados: publicada, por aprobar, provisoria, retirada y procesando.

## Para tener en cuenta

- **«Grabar»** solo muestra los bloques que el profesor tiene **hoy**; el horario de la demo es de lunes a viernes, así que en fin de semana no hay clase para grabar. Para grabar de verdad hace falta **Ollama** abierto con `llama3.2:1b` instalado (la transcripción usa Whisper local).
- Grabar solo funciona desde la **red local** del colegio; en la demo, desde el mismo equipo.
- Al cerrar y volver a abrir con `iniciar.bat demo` los datos vuelven a su estado inicial (lo que se haya cambiado en la demo se pierde).
