/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/** Huella de autoría del frontend: aviso discreto en la consola del navegador y crédito para pies de página. */
export const CREDITO = 'Desarrollado por Tamborconpatas bajo Licencia Apache+Commons'

const ID = 'ClaseAIdia Frontend v1.0 - (c) Tamborconpatas'

let anunciada = false

/** Escribe la huella una sola vez por carga de la página. */
export function huellaEnConsola(): void {
  if (anunciada) return
  anunciada = true
  console.log(`%c${ID}`, 'color:#9ca3af;font-size:10px')
  console.log('%cSi estás mirando por dentro, hay un mensaje para ti en /humans.txt', 'color:#9ca3af;font-size:10px')
}
