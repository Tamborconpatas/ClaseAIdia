# Fase 3 — Frontend (React + TypeScript + Vite + Tailwind + shadcn/ui)

**Estado (2026-10-01): completa y probada en navegador (PC y marco de teléfono).** Solo falta algo que no depende del código: la prueba en un teléfono físico.

Requisito previo: Fase 2 (login y JWT funcionando en el backend). El código vive en `frontend/` (ver `frontend/README.md` para correrlo).

## Qué debe tener, y cómo va

- [x] **Setup**: Vite + React + TypeScript, Tailwind CSS, `shadcn/ui`, `lucide-react`. `npm run build` genera el sitio estático. *Falta*: que el propio servidor del colegio lo sirva (Fase 6; nunca hosting de terceros, decisión ya tomada).
- [x] **Primera ejecución**: si el servidor no tiene colegio se muestra la pantalla para crear el colegio y el primer UTP en vez del login (`GET /auth/estado` → `{"configurado": bool}`, y `POST /auth/setup`, que se cierra sola).
- [x] **Login**: dos flujos — RUT + PIN (alumno) y RUT + contraseña (profesor/UTP). El JWT se guarda en `localStorage` (vence a las 12 h; es razonable porque la app no usa `dangerouslySetInnerHTML`: un token ahí solo se roba con XSS) y se manda por el header `Authorization`.
- [x] **Alumno**: unirse a un curso con código o QR; recuperar el PIN con el código que da el profesor; horario personal; lista de clases de su curso con el detalle (resumen, puntos clave, hoja de repaso, tarjetas con "ver respuesta", transcripción). No tiene pestaña de cursos: tiene uno solo, que se muestra junto a su nombre ("Alumno · 8°A").
- [x] **Profesor**: "Mi horario" (solo sus bloques), Cursos (solo donde dicta, con sus asignaturas y un acceso a sus clases y al código/QR), Clases agrupadas por curso, y **aprobar / retirar** el material.
- [x] **UTP**: Cursos (crear, renombrar, eliminar si están vacíos, ver el código/QR), Clases de todo el colegio, y la **grilla de horario editable**.
- [x] **UTP**: pestaña **Personal** (profesores y UTP): agregar personal con su rol y **resetear la contraseña** de otra persona con un código de un solo uso. Un UTP no resetea la propia: otro UTP lo hace, o quien administra el servidor con `python -m scripts.restablecer_utp <RUT>`.
- [x] **Recuperación de contraseña** del personal desde la pantalla de entrada ("Olvidé mi contraseña": RUT + código + contraseña nueva), igual que el PIN del alumno.
- [x] **Resetear el PIN de un alumno**: profesor (alumnos de sus cursos) o UTP, desde el panel "Alumnos" de cada curso.
- [x] **Profesor**: **editar el material** (resumen, puntos clave, hoja de repaso y tarjetas; la transcripción no se edita) antes o después de aprobarlo.
- [x] **Formularios**: validación también en el cliente (RUT; contraseña de staff de 10 a 128 caracteres, sin el RUT y con ≥ 4 caracteres distintos; PIN de 6 dígitos que no sea repetido ni secuencia; horas de bloque), con mensajes claros. Es comodidad: la validación que cuenta es la del backend.
- [x] **Seguridad del cliente**: sin `dangerouslySetInnerHTML` ni `innerHTML` (el contenido generado por la IA se renderiza como texto), sin llamadas a servicios externos ni trackers, `npm audit` sin vulnerabilidades.
- [x] **Archivos estáticos**: favicon con el logo, `robots.txt` con `Disallow: /` y `<meta name="robots" content="noindex, nofollow">`.
- [x] **Páginas**: política de privacidad y términos y condiciones (`#/privacidad`, `#/terminos`), enlazadas en el pie. Son el **respaldo** del "Aviso para el colegio" del `README.md`, que el colegio acepta al instalar y usar la plataforma (esa es la versión que vale). El contacto (tambotconpatas@proton.me) viene de `VITE_CONTACTO` en `frontend/.env.production`.
- [x] **Accesibilidad automática**: `axe-core` (WCAG 2.0/2.1 A y AA) sin violaciones en entrada, alumno, profesor, UTP y páginas legales (se corrigió el texto alternativo del QR). *Falta* una prueba manual con lector de pantalla y revisión de contraste con ojos humanos: axe no lo cubre todo.
- [x] **Desactivar personal** (pestaña Personal): `POST /usuarios/{id}/desactivar|activar` (solo UTP, no a uno mismo, así siempre queda un UTP activo). Una cuenta desactivada no entra y **su sesión abierta se corta de inmediato**; su nombre se conserva en horarios y clases y no se le asignan bloques nuevos. No se borra personal: borrarlo arrastraría su historial.
- [ ] **Teléfono real**: lo probado fue un marco del tamaño de un teléfono, no un aparato (ver "Verificación").

## Decisiones de diseño

- **PC o teléfono se decide por ancho *y* alto**, no solo por ancho. `desk` = al menos 768 × 480 px; `short` = menos de 480 px de alto (definidos en `frontend/src/index.css`). Un teléfono en horizontal mide ~800 px de ancho pero <430 de alto: con el diseño de PC (barra lateral + dos paneles) quedaba apretado. En horizontal conserva el diseño de teléfono con barras compactas, agenda en dos columnas, contenido de ancho acotado y márgenes para la muesca.
  - **PC**: barra lateral, horario como grilla semanal, Clases con lista + detalle en dos paneles.
  - **Teléfono**: barra superior mínima y pestañas abajo (al alcance del pulgar), horario como agenda de un día con chips, detalle de clase a pantalla completa, editor del horario como hoja desde abajo. Botones y campos de 44 px.
- **Revisión del material con publicación provisoria** (ver `CLAUDE.md`): estados `procesando`, `por_aprobar`, `provisoria`, `publicada`, `retirada`. Pasado el plazo (24 h; `HORAS_REVISION_PROFESOR`) sin que el profesor revise, el alumno ve el material con la advertencia "Sin revisar". Lo retirado nunca se publica solo.
- **Jornadas de cualquier largo**: ni el backend ni la pantalla fijan una hora mínima o máxima (hay colegios de 8:30 a 18:15, o más). Con más de 10 filas la grilla se hace más densa (profesor y sala en una línea, menos relleno), de modo que 8:30–18:15 cabe en una pantalla (735 px en vez de ~1100), y el encabezado de los días queda fijo.
- **Editor del horario** (`PUT`/`DELETE /bloques/{id}`, solo UTP): un bloque no puede cruzarse con otro del mismo curso, un profesor no puede estar en dos cursos a la vez, la hora de término debe ser posterior, una clase necesita asignatura, el profesor debe tener rol PROFESOR, y **un bloque con clases registradas no se puede borrar** (el borrado en cascada se llevaría el material).
- **Desde el horario a la clase**: alumno y profesor tocan un bloque y se abre la clase más reciente de ese bloque que pueden ver; si no hay ninguna, un aviso lo explica (`GET /clases` devuelve el `bloque_id`).
- **QR del curso**: codifica `<dirección con que se abrió la app>/?unirse=<código>` (verificado decodificándolo). Si se abrió como `localhost`, un teléfono no puede usarlo y la pantalla lo avisa: en uso real hay que abrir la app con la dirección del servidor en la red del colegio (Fase 6: la del túnel).
- **Misma origen**: el frontend llama a `/api/...`; en desarrollo Vite lo reenvía al backend (`API_URL` cambia el destino), así no hay CORS y se puede abrir desde un teléfono en la red.
- **Al iniciar sesión** se limpia `?unirse=` de la dirección, y el estado de pestañas vive en un componente que solo existe con sesión (cada persona empieza en su primera pestaña).

## Datos de prueba

`python -m scripts.sembrar_demo` crea `escuela_demo.db` (no toca `escuela.db`) con un colegio, 1 UTP, 7 profesores, 4 alumnos y 3 cursos: 8°A y 8°B (jornada de 8:00 a 13:45) y 3°M (de 8:30 a 18:15, viernes hasta las 15:45), más 9 clases de ejemplo en los 5 estados. Imprime las cuentas al terminar. El script comprueba que ningún profesor quede en dos lugares a la vez. Para usarla: `DATABASE_URL=sqlite:///./escuela_demo.db uvicorn api:app --port 8000`.

## Fuera de esta fase

- Pantalla de control de clase en vivo — Fase 4 (restricción de red distinta: solo red local del colegio).
- Cola de procesamiento y "clase prioritaria" visible al profesor — Fase 5.

## Verificación

Detalle, hallazgos y mediciones en `QA.md` (entradas del 2026-10-01).

- **Backend**: 164 tests (`pytest tests/`).
- **Frontend, en navegador** (PC y un marco del tamaño de un teléfono vertical 390 × 780 y horizontal 820 × 380): login de los tres roles, primer arranque (validaciones, alta y cierre automático), horario por rol, jornada larga, editor del horario completo (editar, rechazo por cruce, eliminar, crear con profesor), clases, aprobar y retirar (también con toques en el marco de teléfono), unirse con QR, y el QR decodificado.
- **Tests del frontend**: `npm test` (vitest, 15 pruebas) cubre RUT, PIN, contraseña y horario, para que el cliente no se desvíe de las reglas del backend. Los componentes se prueban en el navegador, no automáticamente. Además `tsc`, `oxlint` y `npm run build`.
- **Pantallas nuevas en teléfono** (marco de 390 × 780 px, 2026-10-01): Personal, alumnos y reseteo de PIN, editor de material (incluida una clase "por aprobar", editada y aprobada), páginas legales: sin desbordes, sin botones de menos de 36 px ni campos de letra chica; se corrigieron dos fallos que mostró la revisión (filas de Personal aplastadas, botones "Volver" de 20 px).
- **Pendiente**: un teléfono físico (teclado, muesca, toques reales).
