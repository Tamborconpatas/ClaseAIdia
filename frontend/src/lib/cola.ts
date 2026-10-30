/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/**
 * Lo que se le dice al profesor mientras su clase se procesa. `posicion` es su lugar en la cola (1 = la próxima) o null si
 * ya la están procesando. Las clases se procesan de a una, la de plazo más cercano primero (o la marcada como prioritaria).
 */
export function mensajeDeProcesamiento(posicion: number | null): string {
  if (posicion === null) return 'Procesando la clase: se transcribe y se genera el material. Puede tardar unos minutos y puedes cerrar esta pantalla.'
  if (posicion === 1) return 'Tu clase es la próxima en procesarse. Puedes cerrar esta pantalla.'
  const antes = posicion - 1
  return `Tu clase está en la cola: hay ${antes} ${antes === 1 ? 'clase' : 'clases'} antes que la tuya. Puedes cerrar esta pantalla.`
}
