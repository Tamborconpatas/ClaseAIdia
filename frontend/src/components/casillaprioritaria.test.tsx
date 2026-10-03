// @vitest-environment jsdom
import axe from 'axe-core'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CasillaPrioritaria } from '@/components/CasillaPrioritaria'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let raices: Root[] = []
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
})

async function montar(props: { marcada: boolean; deshabilitada: boolean; onCambiar: (m: boolean) => void }) {
  const c = document.createElement('div')
  document.body.append(c)
  const raiz = createRoot(c)
  raices.push(raiz)
  await act(async () => raiz.render(<CasillaPrioritaria {...props} />))
  return c
}

describe('Casilla «Clase prioritaria»', () => {
  it('tiene nombre, refleja si está marcada y no tiene violaciones de accesibilidad', async () => {
    const c = await montar({ marcada: true, deshabilitada: false, onCambiar: () => {} })
    const casilla = c.querySelector('input[type=checkbox]') as HTMLInputElement
    expect(casilla.checked).toBe(true)
    expect(c.querySelector('label')?.textContent).toContain('Clase prioritaria')
    const r = await axe.run(c, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
    expect(r.violations.map((v) => v.id)).toEqual([])
  })

  it('al tocarla avisa el valor nuevo (marcar y desmarcar)', async () => {
    const onCambiar = vi.fn()
    let c = await montar({ marcada: false, deshabilitada: false, onCambiar })
    await act(async () => (c.querySelector('input') as HTMLInputElement).click())
    expect(onCambiar).toHaveBeenLastCalledWith(true)
    for (const r of raices.splice(0)) act(() => r.unmount())
    document.body.innerHTML = ''
    c = await montar({ marcada: true, deshabilitada: false, onCambiar })
    await act(async () => (c.querySelector('input') as HTMLInputElement).click())
    expect(onCambiar).toHaveBeenLastCalledWith(false)
  })

  it('deshabilitada no responde', async () => {
    const onCambiar = vi.fn()
    const c = await montar({ marcada: false, deshabilitada: true, onCambiar })
    const casilla = c.querySelector('input') as HTMLInputElement
    expect(casilla.disabled).toBe(true)
    await act(async () => casilla.click())
    expect(onCambiar).not.toHaveBeenCalled()
  })
})
