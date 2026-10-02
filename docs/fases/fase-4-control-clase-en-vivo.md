# Fase 4 — Control de clase en vivo

**Estado (2026-10-01): hecha y probada de punta a punta con voz real, en PC y en marco de teléfono, con el corte automático probado en vivo; falta probarla con un celular y un lavalier reales.** Detalle y mediciones en `QA.md` (secciones «Fase 4»).

## Cómo quedó (decisión del usuario: las dos formas de grabar son válidas)

- **Una sesión de grabación por clase** (`Grabacion`, `servicios/servicio_grabacion.py`, `interfaz/api/rutas_grabaciones.py`): el servidor guarda el estado y es quien manda. Quien **controla** (el celular del profesor, o el mismo equipo que graba) manda comandos; el **equipo grabador** (un PC de la sala o el celular: es el mismo código) consulta con su latido y obedece, y sube el audio en trozos.
- **Frontend**: pestaña «Grabar» del profesor (`views/Grabar.tsx`, `lib/grabador.ts`). Se puede cambiar de equipo a mitad de clase; un equipo que se interrumpe puede retomar y el servidor une los flujos de audio.

## Qué debía tener, y cómo va

- [x] **Pantalla de control**: iniciar, pausar, silenciar, terminar, cancelar, marcar prioritaria. **Solo red local, verificado en el servidor** (una conexión con cabeceras de proxy o de un túnel cuenta como internet).
- [x] **Corte automático** (probado con el servidor y el vigilante reales): pasado el término del bloque + 15 min (`MINUTOS_CORTE_GRABACION`), o tras 10 min sin ningún equipo conectado; si el equipo no finaliza, el servidor procesa lo recibido a los 45 s.
- [x] **Disparo del pipeline real**: se unen los trozos → `TranscriptionService` (Whisper) → `generate_study_material` (Ollama) → `ContenidoClase` de la `Clase` real, **por aprobar** (el flujo de revisión de la Fase 3). Un solo procesamiento a la vez (la cola con prioridad es la Fase 5).
- [x] **Marcador de «clase prioritaria»**: usable desde la pantalla (`Clase.prioritaria`); la Fase 5 lo usa.
- [x] **Subida de audio**: tipo permitido, firma del archivo, tope por trozo (8 MB) y por grabación (500 MB), nombre de archivo que pone el servidor, solo el equipo grabador registrado.
- [x] **Borrado de audio**: siempre, en un `finally` (también si falla), y tras un reinicio se borra cualquier carpeta huérfana.
- [x] **Si falla solo la generación** (p. ej. Ollama apagado): la transcripción se conserva (oculta a los alumnos) y «Reintentar» regenera el material sin volver a grabar.
- [x] **`transcriptions_history.db`** (historial del prototipo Gradio): se borró el archivo (estaba vacío, 0 filas, y no estaba en git). El código del prototipo (`app.py`, `infraestructura/repositorio_historial.py`) sigue y lo vuelve a crear vacío si se ejecuta; el flujo real guarda todo en `escuela.db`. Si algún día se quiere retirar el historial del prototipo también, hay que sacar `repositorio_historial` y `servicio_historial`.
- [x] **https para grabar con el celular por la red local**: `python -m scripts.generar_certificado` crea un certificado propio (válido para `localhost` y las direcciones de la red) que usan uvicorn (`--ssl-keyfile/--ssl-certfile`) y `npm run dev:https`. La primera vez cada equipo muestra una advertencia que hay que aceptar. *Falta*: confirmar en un celular real que, aceptada la advertencia, el navegador da el micrófono; y, para el despliegue sin advertencias, un dominio propio con certificado válido (Fase 6).
- [x] **Clase real de 92 minutos** (2026-10-02): probada por la API de punta a punta: transcripción de ~4 min con Whisper `small` en una GPU de 4 GB y material generado en ~6-9 min más (ver `QA.md`). Encontró una falla que ninguna prueba corta había visto (el prompt final no cabía en la ventana de Ollama y el material salía sin hoja de repaso ni tarjetas): corregida.
- [ ] **Probar con un celular real** (micrófono, Wake Lock, qué hace al bloquearse la pantalla), un lavalier, audio de sala con ruido, Safari/iOS y clases de 90 minutos.

## Contexto original de la fase

Esta es la fase que conecta el backend real (Fases 1-2) con el pipeline de IA que ya existe y funciona (`servicios/servicio_transcripcion.py`, `servicios/servicio_material_estudio.py`, hoy usados por el prototipo Gradio). Decisión ya tomada: el backend FastAPI corre aparte del prototipo Gradio hasta ahora — se conectan recién en esta fase de control de clase en vivo.

## Qué debe tener

- **Pantalla de control**: iniciar, pausar, silenciar la grabación — solo accesible desde la **red local del colegio** (frontera de privacidad del proyecto: es la única pantalla que controla un dispositivo grabando audio en tiempo real). Esto es una restricción de red real, no solo de UI — validar en el backend el origen de la conexión, no confiar en que el frontend oculte el botón.
- **Corte automático**: pasado un tiempo del término programado del `Bloque` (por si el profesor olvida terminar la grabación) — necesita leer la hora de término del `Bloque` correspondiente a la `Clase` en curso.
- **Disparo del pipeline real**: al terminar una grabación, el backend llama a `TranscriptionService.transcribe_file(...)` y luego a `generate_study_material(...)` (los mismos servicios de siempre, ya probados en `QA.md` con datos reales) — pero ahora el resultado se guarda en `ContenidoClase` de la `Clase` real (bloque_id + fecha), no en `transcriptions_history.db`.
- **Marcador de "clase prioritaria"**: botón que el profesor puede activar antes/durante la clase — ya existe el campo `Clase.prioritaria` en el modelo (Fase 1), esta fase lo hace usable desde la UI de control.
- **Subida de audio**: validar tipo y tamaño, y el nombre del archivo lo genera el servidor (nunca el que manda el cliente).
- **Borrado de audio tras procesar**: ya implementado en el pipeline existente, pero en `interfaz/app_gradio.py` el `os.remove` va después del bucle y no en un `finally` (si se cancela a mitad, el audio queda en disco — ver `QA.md`, 2026-09-29). En el flujo nuevo, borrar siempre en `finally`. Confirmar que se mantiene igual en el flujo nuevo (el audio nunca debe sobrevivir más allá del procesamiento, sea cual sea la ruta que lo dispara).

## Decisión pendiente a tomar en esta fase

¿`transcriptions_history.db` (historial del prototipo Gradio) se retira por completo una vez que el flujo real graba directo en `ContenidoClase`, o convive como herramienta de prueba manual? Evaluar cuando se llegue a esta fase — no es necesario decidirlo ahora.

## Fuera de esta fase

- Cola de procesamiento con prioridad EDF — por ahora una clase se procesa de inmediato al terminar; la cola real es Fase 5.

## Verificación esperada

- Grabar una clase real (o simulada) desde la pantalla de control, confirmar que termina en una `Clase`+`ContenidoClase` reales en `escuela.db`, con `aprobado = False` hasta que el profesor la revise (vista de Fase 3).
- Confirmar que el corte automático funciona con un bloque de prueba corto.
- Confirmar que la pantalla de control rechaza conexiones fuera de la red local (o al menos lo señala claramente si el mecanismo real de red — firewall/proxy — se implementa fuera de la app).
