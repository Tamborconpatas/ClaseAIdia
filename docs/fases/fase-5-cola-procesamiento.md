# Fase 5 — Cola de procesamiento (EDF)

**Estado (2026-10-03): hecha y probada con el servidor, el trabajador, Whisper y Ollama reales; detalle y mediciones en `QA.md` («Fase 5»).** Cómo quedó: `servicios/servicio_grabacion.py` (`clave_de_cola`, `cola`, `despachar`, `_recoger_perdidos`), columna `grabaciones.iniciada_en` (migración `c5f7a9b1d3e6`), `posicion_en_cola` en «Grabar» y la cola en orden en «Estado». Lo que sigue pendiente de esta fase: ver el cluster de Ollama de Docker corriendo con la aplicación real (el compose de hoy es el del prototipo Gradio; pasa a la Fase 6).

- [x] Orden EDF por la próxima vez que se dicta el mismo bloque (fecha de la clase + 7 días, a la hora de inicio); a igual plazo, la que se grabó antes.
- [x] `Clase.prioritaria` se salta el orden (la marca el profesor durante la clase o mientras espera).
- [x] Despachador con lugares configurables (`PROCESAMIENTOS_SIMULTANEOS`, 1 por defecto): una clase en marcha nunca se interrumpe; la cola vive en la base y sobrevive a un reinicio.
- [x] Una clase tomada cuyo trabajador desapareció se recoge y se reintenta sola.
- [x] Cluster de Ollama de Docker con la aplicación real (hecho 2026-10-08, con podman compose: las dos réplicas bajan el modelo, la app genera a través del balanceador y reparte entre las dos; ver `QA.md`). Falta con GPU dentro de contenedores.

## Plan original de la fase

Solo tiene sentido una vez que exista más de una `Clase` disparándose para procesar al mismo tiempo (Fase 4 en funcionamiento). Decisión ya tomada: cola de una sola máquina para este semestre — la versión distribuida multi-servidor queda fuera de alcance.

## Qué debe tener

- **Orden EDF (Earliest Deadline First)**: cada `Clase` pendiente se ordena por la próxima ocurrencia del mismo (`Curso`, `Bloque`) según el horario — no por orden de llegada simple.
- **Marcador manual de prioridad**: `Clase.prioritaria` (ya existe en el modelo desde la Fase 1) debe poder saltarse el orden EDF normal cuando el profesor lo activa.
- **Worker/consumidor de la cola**: proceso que toma la siguiente `Clase` pendiente según el orden de arriba y le aplica el pipeline de transcripción + material de estudio (los mismos servicios ya conectados en la Fase 4).
- **Aprovechar el cluster local de Ollama**: ya existe en Docker (`docker/docker-compose.yml`, instancias `ollama-1`/`ollama-2` + `ollama-lb`) pero hoy no acelera nada porque no hay concurrencia real (documentado en el README) — esta es la fase donde eso empieza a tener efecto real, procesando más de una clase en paralelo.

## Fuera de esta fase

- Cola distribuida entre múltiples máquinas — explícitamente fuera de alcance.

## Verificación esperada

- Encolar varias `Clase`s de prueba con distintos horarios y confirmar que se procesan en el orden EDF esperado.
- Confirmar que activar "clase prioritaria" efectivamente adelanta el procesamiento por sobre el orden EDF normal.
- Con el cluster de Ollama de Docker activo, confirmar que dos clases en cola se procesan en paralelo (una por instancia) en vez de en serie.
