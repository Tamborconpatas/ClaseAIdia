/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

type Oyente = () => void
let sistemaOscuro = false
let oyentes: Oyente[] = []

function falsoMatchMedia() {
  vi.stubGlobal('matchMedia', (consulta: string) => ({
    get matches() {
      return consulta.includes('dark') && sistemaOscuro
    },
    addEventListener: (_: string, o: Oyente) => void oyentes.push(o),
    removeEventListener: () => {},
  }))
}

/** La app guarda el estado del tema en el módulo: cada prueba lo carga de nuevo, como una página recién abierta. */
async function paginaNueva() {
  vi.resetModules()
  return import('./tema')
}

const clases = () => document.documentElement.classList

beforeEach(() => {
  localStorage.clear()
  clases().remove('dark')
  document.documentElement.style.colorScheme = ''
  sistemaOscuro = false
  oyentes = []
  falsoMatchMedia()
})
afterEach(() => vi.unstubAllGlobals())

describe('tema de color', () => {
  it('por defecto sigue al sistema: claro si el sistema es claro, oscuro si es oscuro', async () => {
    let t = await paginaNueva()
    t.iniciarTema()
    expect(clases().contains('dark')).toBe(false)

    sistemaOscuro = true
    t = await paginaNueva()
    t.iniciarTema()
    expect(clases().contains('dark')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('se puede fijar claro u oscuro sin importar el sistema, y se recuerda al volver', async () => {
    sistemaOscuro = true
    let t = await paginaNueva()
    t.iniciarTema()
    t.cambiarTema('claro')
    expect(clases().contains('dark')).toBe(false)
    expect(document.documentElement.style.colorScheme).toBe('light')
    expect(localStorage.getItem('claseaidia.tema')).toBe('claro')

    sistemaOscuro = false
    t = await paginaNueva() // «otra visita»
    clases().remove('dark')
    t.iniciarTema()
    t.cambiarTema('oscuro')
    t = await paginaNueva()
    t.iniciarTema()
    expect(clases().contains('dark')).toBe(true) // recordó «oscuro» aunque el sistema sea claro
  })

  it('mientras esté en «Sistema» sigue los cambios del sistema; fijado en claro u oscuro, no', async () => {
    const t = await paginaNueva()
    t.iniciarTema()
    sistemaOscuro = true
    oyentes.forEach((o) => o())
    expect(clases().contains('dark')).toBe(true)

    t.cambiarTema('claro')
    sistemaOscuro = false
    oyentes.forEach((o) => o())
    sistemaOscuro = true
    oyentes.forEach((o) => o())
    expect(clases().contains('dark')).toBe(false) // el sistema pasó a oscuro pero la persona eligió claro
  })

  it('un valor guardado que no es un tema se ignora, y sin almacenamiento todo funciona igual', async () => {
    localStorage.setItem('claseaidia.tema', 'rosado')
    sistemaOscuro = true
    let t = await paginaNueva()
    t.iniciarTema()
    expect(clases().contains('dark')).toBe(true) // se trató como «Sistema» (y el sistema es oscuro), no como un tema raro
    sistemaOscuro = false

    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('bloqueado')
      },
      setItem: () => {
        throw new Error('bloqueado')
      },
    })
    t = await paginaNueva()
    t.iniciarTema()
    expect(() => t.cambiarTema('oscuro')).not.toThrow()
    expect(clases().contains('dark')).toBe(true) // vale mientras la página siga abierta
  })

  it('el control para la interfaz refleja el tema y si está oscuro', async () => {
    const { act, createElement } = await import('react')
    const { createRoot } = await import('react-dom/client')
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
    const t = await paginaNueva()
    t.iniciarTema()
    const visto: string[] = []
    function Sonda() {
      const { tema, oscuro } = t.useTema()
      visto.push(`${tema}:${oscuro}`)
      return null
    }
    const raiz = createRoot(document.createElement('div'))
    await act(async () => raiz.render(createElement(Sonda)))
    await act(async () => t.cambiarTema('oscuro'))
    await act(async () => t.cambiarTema('claro'))
    expect(visto.at(0)).toBe('sistema:false')
    expect(visto).toContain('oscuro:true')
    expect(visto.at(-1)).toBe('claro:false')
    await act(async () => raiz.unmount())
  })
})
