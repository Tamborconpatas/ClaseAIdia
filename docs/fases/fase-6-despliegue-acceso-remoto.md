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

## Fuera de esta fase

- Modo universidad con servidor centralizado multi-sala — fuera de alcance explícito.

## Verificación esperada

- Ejecutar el `.exe` generado por PyInstaller en una máquina limpia (sin Python instalado) y confirmar que arranca.
- Acceder a una vista de alumno/UTP desde fuera de la red del colegio a través del túnel, y confirmar que la pantalla de control de clase en vivo **no** es alcanzable desde ahí.
- Confirmar que un cambio hecho en `escuela.db` local se refleja en la réplica de Turso en un tiempo razonable.
