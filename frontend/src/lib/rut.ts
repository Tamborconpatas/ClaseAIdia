/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
export const limpiarRut = (v: string) => v.replace(/[^0-9kK]/g, '').toUpperCase()

/** "123456785" -> "12.345.678-5" mientras se escribe. */
export function formatearRut(v: string): string {
  const l = limpiarRut(v).slice(0, 9)
  if (l.length < 2) return l
  const cuerpo = l.slice(0, -1).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return `${cuerpo}-${l.slice(-1)}`
}

/** Mismo dígito verificador que valida el backend (que es quien manda). */
export function rutValido(v: string): boolean {
  const l = limpiarRut(v)
  if (!/^\d{7,8}[0-9K]$/.test(l)) return false
  let suma = 0
  let mult = 2
  for (const d of l.slice(0, -1).split('').reverse()) {
    suma += Number(d) * mult
    mult = mult < 7 ? mult + 1 : 2
  }
  const resto = 11 - (suma % 11)
  return l.slice(-1) === (resto === 11 ? '0' : resto === 10 ? 'K' : String(resto))
}

/** Lo que se manda al backend: sin puntos, con guion. */
export function rutParaApi(v: string): string {
  const l = limpiarRut(v)
  return `${l.slice(0, -1)}-${l.slice(-1)}`
}
