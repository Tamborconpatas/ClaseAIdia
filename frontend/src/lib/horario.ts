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
  'bg-indigo-50 text-indigo-950 border-indigo-400',
  'bg-emerald-50 text-emerald-950 border-emerald-400',
  'bg-amber-50 text-amber-950 border-amber-400',
  'bg-rose-50 text-rose-950 border-rose-400',
  'bg-sky-50 text-sky-950 border-sky-400',
  'bg-violet-50 text-violet-950 border-violet-400',
  'bg-teal-50 text-teal-950 border-teal-400',
  'bg-orange-50 text-orange-950 border-orange-400',
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
