# Fase 3 — Frontend (React + TypeScript + Vite + Tailwind + shadcn/ui)

Requisito previo: Fase 2 (login y JWT funcionando en el backend) — el frontend real necesita endpoints de auth para tener sentido; sin eso solo se podría maquetar sin conectar.

## Qué debe tener

- **Setup**: proyecto Vite + React + TypeScript, Tailwind CSS, `shadcn/ui`, `lucide-react`. Servido eventualmente por el propio servidor del colegio (build estático), nunca por un hosting de terceros (decisión ya tomada).
- **Login**: pantalla con los dos flujos — RUT+PIN (alumno) y RUT+contraseña (profesor/UTP) — guardando el JWT (ej. `localStorage` o memoria, a decidir) y mandándolo en cada request subsiguiente.
- **Vista UTP**: grilla de horario editable (bloques de clase + no lectivos: recreo, almuerzo), CRUD de Curso/Bloque/Usuario contra la API ya existente (Fase 1) — ahora protegida por rol (Fase 2).
- **Vista Alumno**:
  - Unirse a un curso vía código/QR (usa `codigo_invitacion` de `Curso`, ya generado en Fase 1).
  - Ver su horario personal automático (derivado de los cursos a los que pertenece).
  - Ver el contenido ya procesado de cada clase (transcripción, resumen, puntos clave, hoja de repaso, tarjetas) — solo el contenido con `aprobado = True`.
- **Vista Profesor**: revisar y aprobar/editar el contenido generado antes de que se publique al alumno (flag `aprobado` en `ContenidoClase`).
- **Formularios**: validación también en el cliente (RUT, PIN de 6 dígitos, horas de bloque), con mensajes de error claros. Es solo para comodidad del usuario; la validación que cuenta sigue en el backend.
- **Accesibilidad y diseño**: contraste de colores revisado al definir la paleta de Tailwind, texto alternativo en imágenes, diseño responsivo probado en celular y PC.
- **Seguridad del cliente**: sin `dangerouslySetInnerHTML` (el contenido generado por la IA se renderiza como texto; si alguna vez hace falta HTML, justificarlo y sanitizarlo).
- **Páginas y archivos estáticos**: política de privacidad, términos y condiciones, medio de contacto real del equipo, favicon con el logo de ClaseAIdia, `robots.txt` con `Disallow: /` y `<meta name="robots" content="noindex">` en la app.
- **Sin trackers externos**: nada de Google Analytics; si se miden cosas, analíticas propias guardadas en la base de datos.
- **CORS**: ya configurado en el backend para `http://localhost:5173` (Fase 1) — ampliar cuando exista el dominio real del túnel (Fase 6).

## Fuera de esta fase

- Pantalla de control de clase en vivo — es Fase 4, y tiene una restricción de red distinta (solo red local del colegio, no accesible remoto).
- Cola de procesamiento / estado de "clase prioritaria" visible al profesor — es Fase 5.

## Verificación esperada

- Cada vista de rol solo muestra lo que ese rol puede ver/hacer, pero el enforcement real ya está en el backend (Fase 2) — el frontend es una conveniencia, no la barrera de seguridad.
- Flujo completo probado a mano en navegador: crear curso como UTP → unirse como alumno con el código → ver horario → ver contenido aprobado por el profesor.
