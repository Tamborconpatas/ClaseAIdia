/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import axe from 'axe-core'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MensajeSecreto } from '@/components/MensajeSecreto'
import { Logo } from '@/components/comunes'
import { cerrarMensaje, extraerMensaje, registrarToque } from '@/lib/mensajeSecreto'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a']
let raiz: Root | null = null

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('Para quien llegó:\n\nCargar con el peso de todo.\nSegunda línea.')))
})
afterEach(() => {
  vi.unstubAllGlobals()
  act(() => cerrarMensaje())
  if (raiz) act(() => raiz!.unmount())
  raiz = null
  document.body.innerHTML = ''
})

function montar() {
  const c = document.createElement('div')
  document.body.append(c)
  raiz = createRoot(c)
  act(() => raiz!.render(<><Logo /><input aria-label="campo" /><MensajeSecreto /></>))
  return c
}
const dialogo = () => document.querySelector('dialog') as HTMLDialogElement
const teclear = (teclas: string[], destino: EventTarget = document.body) =>
  act(() => teclas.forEach((key) => destino.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))))

describe('mensaje secreto', () => {
  it('del texto de humans.txt se quita el saludo', () => {
    expect(extraerMensaje('Saludo:\n\nUno.\n\nDos.\n')).toBe('Uno.\n\nDos.')
  })

  it('cinco toques seguidos al logo lo abren; cuatro no', async () => {
    montar()
    const logo = document.querySelector('img')!.parentElement!
    act(() => { for (let i = 0; i < 4; i++) logo.click() })
    expect(dialogo().open).toBe(false)
    await act(async () => logo.click())
    expect(dialogo().open).toBe(true)
    expect(dialogo().textContent).toContain('Cargar con el peso de todo.')
  })

  it('cinco toques repartidos en más de 3 segundos no lo abren', () => {
    montar()
    act(() => { for (let i = 0; i < 5; i++) registrarToque(i * 1000) })
    expect(dialogo().open).toBe(false)
  })

  it('el código Konami lo abre, y una tecla de más a mitad lo reinicia', () => {
    montar()
    teclear([...KONAMI.slice(0, 5), 'x', ...KONAMI.slice(5)])
    expect(dialogo().open).toBe(false)
    teclear(KONAMI)
    expect(dialogo().open).toBe(true)
  })

  it('el Konami no cuenta mientras se escribe en un campo', () => {
    montar()
    teclear(KONAMI, document.querySelector('input')!)
    expect(dialogo().open).toBe(false)
  })

  it('Cerrar lo cierra y no tiene fallas de accesibilidad', async () => {
    const c = montar()
    teclear(KONAMI)
    const r = await axe.run(c, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice'] },
      rules: { 'color-contrast': { enabled: false }, region: { enabled: false }, 'landmark-one-main': { enabled: false }, 'page-has-heading-one': { enabled: false } },
    })
    expect(r.violations.map((v) => v.id)).toEqual([])
    act(() => (dialogo().querySelector('button') as HTMLButtonElement).click())
    expect(dialogo().open).toBe(false)
  })
})
