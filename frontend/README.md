# Frontend de ClaseAIdia

Interfaz web de la app: React + TypeScript + Vite, Tailwind CSS v4, `shadcn/ui` (componentes sobre Base UI) e íconos `lucide-react`. Decisiones de diseño y estado de la fase: [`docs/fases/fase-3-frontend.md`](../docs/fases/fase-3-frontend.md).

## Cómo correrlo

Requiere Node 20+ y el backend corriendo (ver el `README.md` de la raíz).

```bash
cd frontend
npm install
npm run dev -- --host      # http://localhost:5173 (--host: visible también desde un teléfono en la misma red)
```

El frontend llama a `/api/...` y Vite lo reenvía al backend en `http://127.0.0.1:8000` (sin CORS). Para apuntar a otro backend: `API_URL=http://127.0.0.1:8002 npm run dev`.

Con datos de prueba (desde la raíz del repo):

```bash
python -m scripts.sembrar_demo     # crea escuela_demo.db y muestra las cuentas
DATABASE_URL=sqlite:///./escuela_demo.db uvicorn api:app --port 8000
```

## Comandos

| Comando | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con recarga |
| `npm run build` | Revisa tipos (`tsc`) y genera el sitio estático en `dist/` |
| `npm run lint` | `oxlint` |

No hay tests automatizados del frontend todavía; el backend tiene los suyos (`pytest tests/` en la raíz).

## Estructura

```
src/
  App.tsx              Rutas por rol (pestañas) y sesión
  views/               Entrada (primer arranque, login, unirse, recuperar PIN), Horario, Cursos, Clases
  components/          AppShell (navegación PC / teléfono), EditorBloque, comunes, ui/ (shadcn)
  lib/                 api (fetch + sesión), sesion (contexto), horario (utilidades), rut y validar, usar (carga de datos)
```

## Cosas a saber

- **PC o teléfono** se decide por ancho *y* alto: `desk:` = al menos 768 × 480 px, `short:` = menos de 480 px de alto (variantes de Tailwind definidas en `src/index.css`). No usar `md:`: un teléfono en horizontal lo activaría.
- Sin `dangerouslySetInnerHTML`: el contenido generado por la IA se muestra como texto.
- La sesión (JWT) se guarda en `localStorage` y vence sola a las 12 h.
- Los componentes de `src/components/ui/` los genera `npx shadcn@latest add <componente>`; la utilidad `cn` viene del paquete `cn` (lo mantiene el propio shadcn).
