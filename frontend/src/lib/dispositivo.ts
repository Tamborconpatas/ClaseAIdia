/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
const CLAVE = 'claseaidia:dispositivo'
let enMemoria = ''

/**
 * Un código aleatorio que este navegador se pone la primera vez y se manda en cada petición (`X-Dispositivo`). Sirve para que el
 * UTP sepa desde qué equipo se creó una cuenta con un nombre indebido y quién está conectado. No sale de nada del equipo: ni IP,
 * ni teléfono, ni identificadores del aparato; si se borran los datos del navegador, se genera otro. Si el almacenamiento está
 * bloqueado, vale solo mientras dure la pestaña.
 */
export function codigoDeDispositivo(): string {
  try {
    const guardado = localStorage.getItem(CLAVE)
    if (guardado && /^[0-9a-f]{16}$/.test(guardado)) return guardado
  } catch {
    /* almacenamiento bloqueado */
  }
  if (!enMemoria) enMemoria = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => b.toString(16).padStart(2, '0')).join('')
  try {
    localStorage.setItem(CLAVE, enMemoria)
  } catch {
    /* modo privado: queda en memoria */
  }
  return enMemoria
}
