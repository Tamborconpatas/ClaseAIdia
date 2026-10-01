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
- [ ] Límites de seguridad conocidos que hay que cerrar antes de exponer el servidor (ver Fase 2, "Endurecimiento"; decidido el 2026-10-01 dejarlos para esta fase):
  - **Revocación de tokens**: hoy un token robado vale hasta 12 h aunque se resetee el PIN o se bloquee la cuenta. Requiere una columna de "sesiones válidas desde" en `Usuario` + migración, y que `usuario_actual` compare con el `iat` del token.
  - Límite de intentos por IP/global (mejor en el túnel/proxy) y bloqueo que no delate qué cuentas existen.
  - Deshabilitar `/docs` y `/openapi.json` en producción.
  - `pip-audit` y `npm audit`.
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
