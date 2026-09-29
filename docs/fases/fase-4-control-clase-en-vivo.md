# Fase 4 — Control de clase en vivo

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
