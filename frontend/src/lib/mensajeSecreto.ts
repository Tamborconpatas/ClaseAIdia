/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useSyncExternalStore } from 'react'

/**
 * Mensaje escondido: se abre tocando 5 veces el logo, con el código Konami o desde el pie de las páginas legales.
 * El texto vive solo en public/humans.txt (el archivo que se sirve en /humans.txt) y se lee al abrirlo.
 */
export const extraerMensaje = (humans: string) => humans.split(/\n\s*\n/).slice(1).join('\n\n').trim() // sin el saludo de la primera línea

let mensaje: Promise<string> | null = null
export function cargarMensaje(): Promise<string> {
  mensaje ??= fetch('/humans.txt')
    .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
    .then(extraerMensaje)
    .catch(() => {
      mensaje = null // se reintenta la próxima vez que se abra
      return 'No se pudo cargar el mensaje ahora. Está en /humans.txt.'
    })
  return mensaje
}

const TOQUES = 5
const VENTANA_MS = 3000
const KONAMI = ['arrowup', 'arrowup', 'arrowdown', 'arrowdown', 'arrowleft', 'arrowright', 'arrowleft', 'arrowright', 'b', 'a']

let abierto = false
const oyentes = new Set<() => void>()
const fijar = (valor: boolean) => {
  if (abierto === valor) return
  abierto = valor
  oyentes.forEach((o) => o())
}

export const abrirMensaje = () => fijar(true)
export const cerrarMensaje = () => fijar(false)
export const useMensajeAbierto = () =>
  useSyncExternalStore(
    (o) => {
      oyentes.add(o)
      return () => oyentes.delete(o)
    },
    () => abierto,
  )

let toques: number[] = []
/** Cuenta un toque al logo; al quinto dentro de 3 segundos abre el mensaje. */
export function registrarToque(ahora = Date.now()) {
  toques = [...toques.filter((t) => ahora - t < VENTANA_MS), ahora]
  if (toques.length >= TOQUES) {
    toques = []
    abrirMensaje()
  }
}

let avance = 0
/** Alimenta el código Konami (↑↑↓↓←→←→BA) tecla a tecla; al completarlo abre el mensaje. */
export function registrarTecla(tecla: string) {
  const t = tecla.toLowerCase()
  avance = t === KONAMI[avance] ? avance + 1 : t === KONAMI[0] ? 1 : 0
  if (avance === KONAMI.length) {
    avance = 0
    abrirMensaje()
  }
}
