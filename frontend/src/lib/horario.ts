/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import type { Bloque } from './api'

export const DIAS_CORTO = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
export const DIAS_LARGO = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

export const hhmm = (h: string) => h.slice(0, 5)

/** Día de hoy con la convención del backend (0 = lunes). */
export const diaHoy = () => (new Date().getDay() + 6) % 7

export const aMinutos = (h: string) => Number(h.slice(0, 2)) * 60 + Number(h.slice(3, 5))

function minutosAhora() {
  const d = new Date()
  return d.getHours() * 60 + d.getMinutes()
}

export const esAhora = (b: Bloque) =>
  b.dia_semana === diaHoy() && aMinutos(b.hora_inicio) <= minutosAhora() && minutosAhora() < aMinutos(b.hora_fin)

// Un color estable por asignatura. Clases literales para que Tailwind las detecte.
const PALETAS = [
  'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-950 dark:text-indigo-100 border-indigo-400 dark:border-indigo-500',
  'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-950 dark:text-emerald-100 border-emerald-400 dark:border-emerald-500',
  'bg-amber-50 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100 border-amber-400 dark:border-amber-500',
  'bg-rose-50 dark:bg-rose-950/40 text-rose-950 dark:text-rose-100 border-rose-400 dark:border-rose-500',
  'bg-sky-50 dark:bg-sky-950/40 text-sky-950 dark:text-sky-100 border-sky-400 dark:border-sky-500',
  'bg-violet-50 dark:bg-violet-950/40 text-violet-950 dark:text-violet-100 border-violet-400 dark:border-violet-500',
  'bg-teal-50 dark:bg-teal-950/40 text-teal-950 dark:text-teal-100 border-teal-400 dark:border-teal-500',
  'bg-orange-50 dark:bg-orange-950/40 text-orange-950 dark:text-orange-100 border-orange-400 dark:border-orange-500',
]
export function colorAsignatura(nombre: string | null): string {
  let h = 0
  for (const c of nombre ?? '') h = (h * 31 + c.charCodeAt(0)) >>> 0
  return PALETAS[h % PALETAS.length]
}

export const ordenar = (bs: Bloque[]) =>
  [...bs].sort((a, b) => a.hora_inicio.localeCompare(b.hora_inicio) || a.dia_semana - b.dia_semana)

/** "2026-09-28" -> "lun, 28 sep" (sin pasar por UTC: la fecha es de calendario, no un instante). */
export const fechaCorta = (fecha: string) =>
  new Date(`${fecha}T00:00:00`).toLocaleDateString('es-CL', { weekday: 'short', day: 'numeric', month: 'short' })
