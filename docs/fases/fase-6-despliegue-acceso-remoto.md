# Fase 6 — Despliegue y acceso remoto

Última fase antes del piloto. Requiere que las Fases 1-5 estén funcionando en dev/local — esta fase es sobre empaquetar y exponer lo ya construido, no sobre nueva funcionalidad de producto.

## Qué debe tener

- **Empaquetado portable (PyInstaller)**: ejecutable sin instalador y sin permisos de administrador — la vía principal de instalación. Docker (ya armado desde antes) queda como alternativa documentada para colegios con soporte técnico, no como reemplazo.
- **Túnel de acceso remoto (tipo Cloudflare Tunnel)**: expone el propio servidor del colegio directo a internet, sin servidor intermediario de terceros. Solo debe quedar expuesto lo que corresponde: vistas de alumno/UTP y revisión de clases pasadas del profesor (todo lo que es solo texto ya procesado) — **nunca** la pantalla de control de clase en vivo (Fase 4), que debe seguir restringida a la red local.
- **Turso/libSQL**: réplica en la nube de la SQLite local (`escuela.db`) — capa de acceso remoto para que las vistas de texto funcionen incluso si se consulta desde fuera del colegio.
- **CORS de producción**: reemplazar los orígenes de desarrollo (`http://localhost:5173`, configurados en la Fase 1) por el dominio real del túnel — nunca `*` en producción.
- **Configuración del PC del colegio**: debe permanecer encendido de forma permanente (sin suspensión) para que el túnel funcione — esto es una instrucción operativa para el piloto, no código, pero debe quedar documentada en las notas de instalación.

## Bloqueantes no técnicos a resolver antes o durante esta fase

- Consentimiento informado de apoderados.
- Respaldo simple y periódico de la base de datos (estructura/texto, no audio).

## Pendientes detectados antes (ver `QA.md`, 2026-09-29)

- [x] La API no arrancaba con la salida redirigida en Windows (`UnicodeEncodeError` por el emoji del aviso de `JWT_SECRET_KEY`) — corregido el 2026-10-01: el aviso es solo ASCII. Si se agregan otros `print` de arranque, mantenerlos ASCII hasta empaquetar el `.exe`.
- [x] Límites de seguridad conocidos (hecho 2026-10-08; ver Fase 2, «Límites conocidos», y `README.md`, «Seguridad del acceso»):
  - [x] **Revocación de sesiones**: `usuarios.version_sesion` dentro del token; se sube al cambiar o resetear la clave o el PIN, desactivar la cuenta o `POST /auth/cerrar-sesiones`.
  - [x] Límite de intentos por dirección (30 en 10 min) y bloqueo de RUT inexistentes igual al de los reales. Sin límite global, a propósito. Detrás de un proxy hace falta `CABECERA_IP_CLIENTE`; el nginx de Docker ya la fija.
  - [x] `/docs`, `/redoc` y `/openapi.json` apagados salvo `API_DOCS=1`.
  - [x] `pip-audit` (solo marcaba `pip`, el instalador del entorno, ya actualizado) y `npm audit` (producción en 0; quedan 7 «high» en `shadcn`, herramienta de desarrollo que no llega al navegador).
  - [ ] Falta cuando exista el túnel: que `cloudflared` entregue la dirección real (`CF-Connecting-IP`) al límite de intentos. Hoy, por el túnel, todos parecerían venir de la misma dirección y el límite por IP afectaría a todos juntos.
- [x] Agregar `.env` a `.dockerignore` (hecho 2026-09-29, junto con el `.env.example` de la Fase 2).

## Checklist antes de la demo

- `pip-audit` y `npm audit` sin vulnerabilidades pendientes.
- Revisar enlaces rotos y velocidad de carga en celular.
- Flujo completo de punta a punta: grabar → procesar → aprobar → ver como alumno.
- Probar en el hardware modesto de referencia (VM con pocos núcleos y poca RAM).
- Repo sin datos reales de alumnos ni audios de prueba commiteados, y privado mientras contenga cualquier dato del piloto.

## Fuera de esta fase

- Modo universidad con servidor centralizado multi-sala — fuera de alcance explícito.

## Verificación esperada

- Ejecutar el `.exe` generado por PyInstaller en una máquina limpia (sin Python instalado) y confirmar que arranca.
- Acceder a una vista de alumno/UTP desde fuera de la red del colegio a través del túnel, y confirmar que la pantalla de control de clase en vivo **no** es alcanzable desde ahí.
- Confirmar que un cambio hecho en `escuela.db` local se refleja en la réplica de Turso en un tiempo razonable.
