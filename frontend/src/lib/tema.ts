/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useSyncExternalStore } from 'react'

/**
 * Tema de color. Es opcional: por defecto sigue al sistema (quien usa el teléfono en modo oscuro lo ve oscuro sin tocar
 * nada) y cada persona puede fijar claro u oscuro. Se recuerda en este navegador; no se manda al servidor.
 */
export type Tema = 'sistema' | 'claro' | 'oscuro'

const CLAVE = 'claseaidia.tema'
const TEMAS: readonly Tema[] = ['sistema', 'claro', 'oscuro']
const CONSULTA = '(prefers-color-scheme: dark)'

function leer(): Tema {
  try {
    const t = localStorage.getItem(CLAVE)
    return TEMAS.includes(t as Tema) ? (t as Tema) : 'sistema'
  } catch {
    return 'sistema' // navegación privada o almacenamiento bloqueado: funciona igual, solo que no se recuerda
  }
}

const sistemaOscuro = () => typeof matchMedia === 'function' && matchMedia(CONSULTA).matches

let tema: Tema = leer()
let oscuro = tema === 'oscuro' || (tema === 'sistema' && sistemaOscuro())
const oyentes = new Set<() => void>()

/** Pone o quita la clase `dark` de la página (de ahí salen todos los colores) y avisa a los controles nativos. */
function aplicar() {
  oscuro = tema === 'oscuro' || (tema === 'sistema' && sistemaOscuro())
  document.documentElement.classList.toggle('dark', oscuro)
  document.documentElement.style.colorScheme = oscuro ? 'dark' : 'light'
  oyentes.forEach((o) => o())
}

export function cambiarTema(nuevo: Tema) {
  tema = nuevo
  try {
    localStorage.setItem(CLAVE, nuevo)
  } catch {
    /* sin almacenamiento: el cambio vale mientras la página siga abierta */
  }
  aplicar()
}

let escuchando = false
/** Se llama una vez antes de dibujar la app: aplica el tema guardado y sigue los cambios del sistema mientras se use «Sistema». */
export function iniciarTema() {
  aplicar()
  if (escuchando || typeof matchMedia !== 'function') return
  escuchando = true
  matchMedia(CONSULTA).addEventListener('change', aplicar) // `aplicar` ya respeta una elección fija: solo «Sistema» depende del sistema
}

const suscribir = (o: () => void) => {
  oyentes.add(o)
  return () => void oyentes.delete(o)
}

export function useTema(): { tema: Tema; oscuro: boolean; cambiar: (t: Tema) => void } {
  const t = useSyncExternalStore(suscribir, () => tema)
  const o = useSyncExternalStore(suscribir, () => oscuro)
  return { tema: t, oscuro: o, cambiar: cambiarTema }
}

/** Solo para las pruebas: vuelve al estado de una página recién abierta. */
export function reiniciarTemaParaPruebas() {
  tema = leer()
  aplicar()
}
