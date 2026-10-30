/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/** Guarda un archivo generado en el navegador (en el teléfono se abre o se guarda según el sistema). */
export function descargar(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombre
  enlace.rel = 'noopener'
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  setTimeout(() => URL.revokeObjectURL(url), 60_000) // da tiempo a que el navegador empiece a guardarlo
}
