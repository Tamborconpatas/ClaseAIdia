# Fases del proyecto: especificación y estado

Cada archivo de esta carpeta especifica qué debe tener una fase y cómo quedó. **Estado al 2026-11-27**: las Fases 0 a 5 están hechas y probadas; la Fase 6 (despliegue y acceso remoto) está en curso. El registro de validación de cada una está en `QA.md` (raíz). Cada fase asume que las anteriores ya están hechas.

| Fase | Qué es | Estado | Lo que falta |
|---|---|---|---|
| [0 — Origen: pipeline de IA](fase-0-origen-pipeline-ia.md) | Transcripción y material de estudio con IA local | Completa | Nada (el prototipo Gradio se retiró) |
| [1 — Backend y modelo de datos](fase-1-backend-modelo-datos.md) | FastAPI, SQLAlchemy, Curso → Bloque → Clase | Completa | Nada |
| [2 — Autenticación y roles](fase-2-autenticacion-roles.md) | UTP, profesor y alumno, con permisos en el servidor | Completa, con la seguridad previa al túnel hecha (revocación de sesiones, límites por intento y por dirección, auditorías) | Nada |
| [3 — Frontend](fase-3-frontend.md) | React: horario, cursos, material, descargas, panel «Estado» y «Ajustes» | Completa y probada en navegador (PC, marco de teléfono y dos teléfonos Android reales) | Probar con lectores de pantalla reales (NVDA, VoiceOver, TalkBack): axe no los reemplaza |
| [4 — Control de clase en vivo](fase-4-control-clase-en-vivo.md) | Grabar, pausar y cortar la clase; el celular graba o controla | Hecha y probada con voz real, corte automático y dos celulares Android reales | Lavalier real, audio de sala con ruido, Safari/iOS, qué hace el celular al bloquearse la pantalla y clases de 90 minutos |
| [5 — Cola de procesamiento (EDF)](fase-5-cola-procesamiento.md) | Orden por plazo, prioridad manual, recuperación tras reinicio | Hecha y probada con el servidor, el trabajador, Whisper y Ollama reales; el cluster de Ollama de Docker con la app real, el 2026-10-08 | La cola con solo CPU y clases de 90 min en un equipo lento (hoy es una estimación) y el cluster con GPU dentro de contenedores |
| [6 — Despliegue y acceso remoto](fase-6-despliegue-acceso-remoto.md) | Instalación portable, túnel y réplica en la nube | **En curso**: hechas la seguridad previa al túnel y Docker | Empaquetado portable (PyInstaller), túnel de acceso remoto, réplica Turso/libSQL, CORS de producción y la configuración del PC (sin suspensión) |

## Lo que bloquea el piloto y no es código

- **Consentimiento informado de apoderados** (datos de menores, aunque la voz se descarte tras procesarse).
- **Revisión de un abogado** sobre tratar datos de menores, incluido el registro de dispositivos. La Ley 21.719 rige plenamente desde el 1 de diciembre de 2026 (hay un proyecto que la posterga).
- **Un equipo real de colegio**: nada se midió todavía en un PC con Windows de 4 núcleos y 12–16 GB. Los requisitos mínimos (`README.md` raíz) salen de mediciones en Linux más una estimación para Windows.

## Lo construido fuera de las fases

Las fases ordenan lo planificado; después se sumaron cosas que no tienen una fase propia y están en `CLAUDE.md` y `QA.md`: panel «Estado» del UTP, respaldo diario con restauración probada y prueba de humo, fotos de la pizarra (opcional), descarga de la clase en PDF y Word, tema claro u oscuro, gestión de alumnos con cupo por curso, validación de RUT y nombres, un solo curso y una sola sesión por alumno, registro de dispositivos sin IP, y modelo de resumen por defecto sin GPU (`gemma4:e2b`).
