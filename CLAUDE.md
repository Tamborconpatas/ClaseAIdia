# Contexto del proyecto — Transcriptor de clases

Este archivo resume todas las decisiones de diseño y producto tomadas para este proyecto de título. Cualquier asistente de IA (o persona) que trabaje en este código debería leerlo antes de proponer cambios de arquitectura — la mayoría de las decisiones aquí ya fueron evaluadas contra alternativas y tienen una razón concreta detrás.

## Qué es el proyecto

Aplicación web que graba, transcribe y sintetiza clases usando IA ejecutada localmente, para ayudar a alumnos que se distraen o faltan a clases. Dirigida a colegios (7° básico a 4° medio) y, como extensión, a universidades. Prioridad de diseño: bajo costo, privacidad, instalación sin fricción.

**Público objetivo:** 7° básico a 4° medio (justificado por el desarrollo de la corteza prefrontal durante la pubertad — atención sostenida en pleno desarrollo en ese rango de edad).

## Restricciones del proyecto (no negociables al programar)

- Duración: un semestre (agosto–diciembre 2026).
- Equipo: 2 personas. El usuario es el programador principal; su compañero escribe la memoria de título; ambos colaboran en la app según disponibilidad.
- Se usará asistencia de IA para programar.
- Debe quedar como **prototipo funcional demostrable** para la defensa, no solo diseñado.
- El piloto de validación es acotado: 1-2 cursos, no un colegio completo.

## Alcance funcional

### Núcleo indispensable (construir primero, sin excepción)
- Captura de audio vía lavalier del profesor, desde el dispositivo disponible (PC de sala, notebook, o celular).
- Control de clase desde el navegador: iniciar, pausar, silenciar. Corte automático de la grabación pasado un tiempo del término programado del bloque (por si el profesor olvida terminarla).
- Transcripción local con `faster-whisper` (modelo liviano cuantizado, no "large" — el hardware objetivo es modesto, sin GPU).
- Generación local con Ollama: resumen, puntos clave, hoja de repaso, tarjetas de estudio — incorporando recuperación activa, repetición espaciada, elaboración e interleaving en el diseño del prompt.
- El profesor revisa el contenido generado y lo aprueba o lo retira. Si se olvida (pasa el plazo de revisión, 24 h por defecto, configurable con `HORAS_REVISION_PROFESOR`), el material se publica igual como **provisorio**: los alumnos lo ven con una advertencia de que no fue revisado, y el profesor puede aprobarlo (quita la advertencia) o retirarlo. Lo retirado nunca se publica solo. Así un olvido no deja a los alumnos sin material, y el contenido sin revisar nunca se presenta como si lo estuviera.
- Modelo de datos Curso → Bloque (ver sección de datos).
- Tres roles con permisos verificados **en el backend** (nunca solo ocultos en la interfaz): UTP/administrador, profesor, alumno.
- UTP: grilla de horario editable (bloques de clase + bloques no lectivos: recreo, almuerzo).
- Alumno: unirse a curso vía código/QR, ver horario personal automático, ver contenido de cada clase procesada.
- Autenticación: alumno con RUT + PIN de 6 dígitos (elegido por el alumno en su primer ingreso, no asignado); profesor/UTP con RUT + contraseña.
- Cola de procesamiento con prioridad *Earliest Deadline First*: ordena por la próxima ocurrencia del mismo (Curso, Bloque) según el horario, más un marcador manual de "clase prioritaria" que puede activar el profesor.
- Solo se almacena texto (transcripción completa + contenido generado). El audio se descarta después de procesarse — nunca se guarda.
- Instalación portable (Windows), sin instalador, sin permisos de administrador.

### Extras (agregar solo si el núcleo va sólido y sobra tiempo)
En este orden de prioridad si hay que elegir:
1. Captura de foto de pizarra (botón en el control del profesor, asociada al timestamp/tema).
2. Segmentación automática de temas (comparar horario planificado vs. desarrollo real).
3. Detección de preguntas de alumnos (por parafraseo del profesor — **no** se agrega micrófono de sala adicional).
4. Exportación del horario a Excel.

### Explícitamente fuera de alcance (documentado como trabajo futuro, no construir)
- Importación automática de horario desde Excel del colegio (usar en cambio la grilla editable del UTP).
- Modo universidad con servidor centralizado multi-sala.
- Banco de preguntas acumulativo por curso (FAQ del semestre).
- Cola de procesamiento distribuida entre múltiples máquinas.
- Registro de auditoría avanzado.
- Elementos de sitio web público que no aplican a una app privada con login: sitemap.xml, meta títulos/descripciones SEO, imagen Open Graph, banner de cookies (la sesión va por header, no cookies), página de "Gracias", Google Analytics, botones CTA. Página 404 personalizada: opcional, baja prioridad.

## Arquitectura

**Frontera de privacidad (principio central del proyecto):** la voz/audio nunca sale del colegio. Solo el texto ya generado por la IA puede salir. En consecuencia, la frontera de red es:
- **Solo red local del colegio:** la pantalla de control de clase en vivo (porque controla un dispositivo grabando audio en tiempo real).
- **Accesible desde cualquier lugar:** todo lo demás — vistas de alumno, UTP, y revisión de clases pasadas del profesor — porque solo involucra texto ya procesado.

**Cómo se logra el acceso remoto:** el propio servidor del colegio se expone directo a internet mediante un túnel (tipo Cloudflare Tunnel), sin pasar por un servidor intermediario de terceros. El servidor del colegio debe permanecer encendido de forma permanente para que esto funcione (configurar el PC para que nunca entre en suspensión).

**Procesamiento:** 100% local en el servidor del colegio (Whisper + Ollama), sin dependencia de servicios de IA en la nube ni costo recurrente por uso.

## Stack técnico

**Backend:** Python 3.12 o superior (probado en 3.12 y 3.14), FastAPI, Uvicorn, SQLAlchemy (ORM), Pydantic.
**IA local:** `faster-whisper` (STT, modelo liviano/cuantizado) como motor por defecto (CPU y GPU NVIDIA); si se detecta GPU AMD (ROCm, solo Linux) se usa `transformers` + PyTorch como motor alternativo, porque CTranslate2 (el motor detrás de faster-whisper) no soporta ROCm. Ollama (LLM, modelo 7-9B cuantizado, ej. Qwen o Gemma según benchmark real) — en el despliegue con Docker puede correr como varias instancias locales (mismo PC) balanceadas con nginx para paralelizar la generación cuando hay varias clases en cola.
**Base de datos:** SQLite local (servidor del colegio) sincronizado vía Turso/libSQL con réplica en la nube (capa de acceso remoto).
**Frontend:** React + TypeScript + Vite, Tailwind CSS, shadcn/ui, lucide-react (íconos).
**Empaquetado:** PyInstaller (ejecutable portable, sin instalador) como vía principal; Docker Compose como alternativa para colegios con soporte técnico (ver decisión más abajo).
**Seguridad:** `argon2-cffi` directo (argon2id; hash de contraseñas/PIN; se dejó `passlib`, abandonado desde 2020), `PyJWT` (tokens de sesión, vía header `Authorization`, no cookies — reduce riesgo CSRF), límite de intentos con bloqueo temporal creciente (recomendado: 5 intentos) en login de alumno y de staff, CORS configurado explícitamente (nunca `*` en producción), validación de tipo/tamaño en subida de audio, secretos solo en variables de entorno (`.env` en `.gitignore` desde el primer commit), validación de dígito verificador de RUT en el backend, nunca SQL crudo con concatenación de strings (siempre vía ORM). Además: contraseñas de staff de 10 a 128 caracteres sin el RUT y PIN de alumno que no sea repetido ni secuencia (política validada en el backend); JWT siempre con expiración y clave de al menos 32 caracteres; nombre de archivo de audio subido generado por el servidor (nunca el que manda el cliente); `.env.example` sin valores reales junto al `.env`; ninguna clave/token/credencial escrita en el código; nunca PIN ni contraseñas en los logs; `pip-audit` y `npm audit` antes de la entrega final.

**Privacidad en el frontend y la web:** sin Google Analytics ni trackers externos (si se miden cosas, analíticas propias guardadas en la base de datos); `robots.txt` con `Disallow: /` y `noindex` en las páginas de la app (es privada, no se indexa); sin `dangerouslySetInnerHTML` salvo justificado y sanitizado.

**Repositorio:** sin datos reales de alumnos ni audios de prueba commiteados; el repo se mantiene privado mientras contenga cualquier dato del piloto.

## Modelo de datos (resumen)

```
Colegio/Universidad
 └─ Curso (ej. "8°A" en colegio; una asignatura-sección en universidad)
     └─ Bloque (asignatura, profesor, sala, día, hora inicio/fin — o tipo "no lectivo": recreo/almuerzo)

Usuario (RUT) → Rol (alumno / profesor / UTP) — un usuario puede tener más de un rol
Alumno ↔ Curso (relación muchos a muchos, vía código/QR de invitación)
Clase (instancia de un Bloque en una fecha) → Transcripción, Resumen, Puntos clave, Hoja de repaso, Tarjetas, Preguntas detectadas
```

En colegio, un Curso agrupa varios Bloques (toda la semana de un grupo fijo de alumnos). En universidad, casi siempre 1 Curso = 1 Bloque.

## Decisiones ya evaluadas (no reabrir sin razón nueva)

- **NoSQL fue descartado** — el modelo de datos es fuertemente relacional (Curso/Bloque/Usuario/Rol), SQL es la elección correcta.
- **No se expone el motor de IA (Whisper/Ollama) directo a internet** — solo el resultado de texto ya generado.
- **No se guarda audio, bajo ninguna circunstancia** — decisión de espacio (900MB/bloque x muchos bloques es inviable) y de privacidad.
- **No se usa importación automática de Excel para el horario** — los formatos varían demasiado entre colegios; se prioriza la grilla editable por el UTP como fuente de verdad, con exportación a Excel disponible.
- **La cola de procesamiento es de una sola máquina para el prototipo** — la versión multi-servidor coordinada por carpeta compartida queda documentada pero no se construye este semestre.
- **El PIN del alumno lo elige el alumno**, no lo asigna el UTP (evita carga operativa de distribución segura de PINs). Si lo olvida, un profesor o UTP puede resetearlo: el reseteo entrega un código de un solo uso (vence en 15 min) que el staff le pasa en persona, y con ese código el alumno elige su PIN nuevo. Nunca "el siguiente login fija el PIN": dejaría que cualquiera con el RUT se quede con la cuenta.
- **Recuperar la contraseña del personal** funciona igual (código de un solo uso, 15 min, entregado en persona): un UTP resetea la de un profesor u otro UTP, pero nunca la propia. El UTP es el rol más importante, así que además hay una salida de último recurso para quien administra el servidor: `python -m scripts.restablecer_utp <RUT>` (solo funciona sobre una cuenta UTP y valida la política de contraseñas). Las sesiones ya abiertas siguen válidas hasta 12 h: no hay revocación de tokens (Fase 6).
- **Vercel u otro hosting de terceros para el frontend no aplica** — rompería la decisión de que el propio servidor del colegio sirva todo sin intermediarios.
- **Selección de motor de transcripción automática por hardware, nunca manual** — CPU o GPU NVIDIA usan `faster-whisper`; GPU AMD (ROCm, solo Linux) usa `transformers` + PyTorch porque CTranslate2 no soporta ROCm. Sin toggle en la UI: la app detecta y elige sola.
- **Docker Compose se agrega como opción de despliegue adicional** (app + cluster local de Ollama en la misma máquina, balanceado con nginx) para colegios con soporte técnico — excepción consciente a la restricción de "instalación portátil sin admin", que sigue siendo el objetivo principal vía PyInstaller para el resto de los casos. El "cluster" de Ollama son varias instancias en un solo PC, no un despliegue distribuido entre servidores (eso sigue fuera de alcance, ver más abajo).
- **La GPU no se pasa a los contenedores por defecto** — Docker aísla la GPU del host salvo que se pida explícitamente. Por eso hay archivos de override separados (`docker-compose.gpu-nvidia.yml`, `docker-compose.gpu-amd.yml`) en vez de intentar detectarla sola: para NVIDIA requiere además instalar el NVIDIA Container Toolkit en el host (paso manual con `sudo`, no automatizable desde la app). Sin el override, `app` y Ollama corren en CPU dentro de Docker aunque el PC tenga GPU — coherente con que el hardware objetivo del proyecto no la necesita, pero hay que acordarse de habilitarlo a propósito en un despliegue con GPU real.
- **El backend FastAPI (`api.py`, `interfaz/api/`) corre aparte del prototipo Gradio** (`app.py`, `interfaz/app_gradio.py`) mientras se construye la app real — cada uno con su propia base de datos (`escuela.db` para el modelo Colegio/Curso/Bloque/Usuario/Clase vía SQLAlchemy+Alembic, `transcriptions_history.db` para el historial del prototipo Gradio). Se conectan recién en la fase de control de clase en vivo, cuando el backend real dispare el pipeline de transcripción que hoy solo usa Gradio.

- **El frontend vive en `frontend/`** (React + Vite) y llama a `/api/...`: en desarrollo Vite lo reenvía al backend (sin CORS, y sirve para probar desde un teléfono en la red); en producción lo servirá el propio servidor del colegio (Fase 6). Detalle y estado en `docs/fases/fase-3-frontend.md`.
- **PC o teléfono se decide por ancho y alto, no solo por ancho** (variantes `desk:` y `short:`, nunca `md:`): un teléfono en horizontal mide ~800 px de ancho pero <430 de alto, y con el diseño de PC quedaba apretado.
- **El horario no restringe horas** (hay colegios de 8:30 a 18:15, o más): ni el backend ni la pantalla fijan una hora mínima o máxima, y la grilla se densifica cuando hay muchas filas en vez de alargarse.
- **Reglas del horario** (las aplica el backend al crear y editar bloques): un bloque no puede cruzarse con otro del mismo curso, un profesor no puede estar en dos cursos a la vez, y un bloque con clases registradas no se puede borrar (el borrado en cascada se llevaría el material de estudio).
- **Datos de prueba**: `python -m scripts.sembrar_demo` crea `escuela_demo.db` (con jornadas corta y larga y clases en todos los estados); nunca se siembra sobre `escuela.db`.

- **Los términos de privacidad y uso los acepta el colegio al instalar la aplicación**: están en el "Aviso para el colegio" del `README.md` (esa es la versión que vale). Las páginas `#/privacidad` y `#/terminos` del frontend son solo su respaldo para alumnos y apoderados; si cambia una, cambia la otra.

## Pendiente por resolver antes del piloto (no técnico, pero bloqueante)

- Consentimiento informado de apoderados para el colegio piloto (dato personal de menores, aunque sea descartado tras procesarse).
- Respaldo simple y periódico de la base de datos (no del audio — de la estructura: horario, usuarios, contenido de texto acumulado).
