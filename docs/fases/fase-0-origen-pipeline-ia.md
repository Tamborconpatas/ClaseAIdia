# Fase 0 — Origen: pipeline de IA (Completada)

A diferencia de las demás fases, esta no viene de un roadmap planificado de antemano — es el punto de partida real del proyecto: un proyecto personal preexistente que se adoptó y adaptó como base para la memoria de título.

## De dónde viene

El código original era un prototipo Gradio de un solo archivo/estructura plana, en inglés, con varios motores de transcripción alternativos configurables a mano (`faster-whisper`, `transformers`, `NeMo`, más diarización de hablantes) — pensado como herramienta genérica de transcripción, no específicamente para colegios ni con los requisitos de privacidad de audio, roles, o modelo Curso/Bloque que sí tiene el proyecto de título.

## Qué se hizo para adaptarlo al proyecto de título

1. **Simplificación del motor de IA**: de varios backends configurables a mano, a una selección automática por hardware — `faster-whisper` (CPU/GPU NVIDIA) o `transformers`+PyTorch (GPU AMD/ROCm, porque CTranslate2 no soporta ROCm) — sin diarización ni NeMo (fuera del alcance del proyecto de título).
2. **Arquitectura en capas**: de estructura plana en inglés a `interfaz → servicios → infraestructura → nucleo`, con nombres de archivos y carpetas en español (decisión explícita: el proyecto es para colegios chilenos).
3. **Privacidad de audio**: el audio se borra siempre después de procesarse — nunca se guarda, ni el original ni los temporales (FFmpeg, limpieza DSP).
4. **Material de estudio completo**: de solo resumen + puntos clave, a 4 secciones (+ hoja de repaso + tarjetas), con principios de aprendizaje (recuperación activa, elaboración, interleaving, repetición espaciada) incorporados al diseño del prompt.
5. **Transcripciones largas**: chunking secuencial (map-reduce) antes de mandar el texto a Ollama, para no colapsar memoria/procesamiento en hardware modesto.
6. **Catálogos de modelos por hardware**: Whisper y Ollama (`llama3.2:1b`/`3b`) eligen tamaño de modelo según CPU/GPU disponible y VRAM, sin toggle manual en la UI.
7. **Docker**: opción de despliegue adicional (app + cluster local de Ollama balanceado con nginx), con overrides explícitos de GPU (NVIDIA/AMD) — sin reemplazar el objetivo de instalación portátil sin admin.
8. **Documentación**: diagramas Mermaid en el README, `QA.md` como bitácora de validación.

## Resultado

El pipeline de transcripción + material de estudio quedó funcional y validado con datos reales (ver `QA.md`), pero sigue siendo un prototipo Gradio de un solo usuario — sin modelo de datos, sin roles, sin autenticación. Ese es exactamente el punto donde arranca la Fase 1.

## Verificación (ya hecha, ver `QA.md`)

Transcripción y generación de material de estudio probadas de punta a punta con un video real (no solo audio de prueba corto), incluyendo el chunking map-reduce con contenido real por primera vez.
