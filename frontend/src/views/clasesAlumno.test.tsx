/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Clases } from '@/views/Clases'

vi.mock('@/lib/sesion', () => ({ useSesion: () => ({ rol: 'ALUMNO' }) }))
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const clase = (id: number, asignatura: string | null, fecha: string) => ({
  id, bloque_id: id, fecha, curso_id: 1, curso_nombre: '8°A', asignatura, sala: null, hora_inicio: '08:00:00', hora_fin: '09:30:00',
  profesor_id: 1, estado: 'publicada', revision_vence: null, prioritaria: false,
})
const raices: Root[] = []
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

async function montar(clases: unknown[]) {
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify(clases), { status: 200, headers: { 'Content-Type': 'application/json' } }))
  const div = document.createElement('div')
  document.body.append(div)
  const raiz = createRoot(div)
  raices.push(raiz)
  await act(async () => raiz.render(<Clases cursoInicial={null} claseInicial={null} />))
  await act(async () => void (await new Promise((r) => setTimeout(r, 50))))
  return div
}

const botones = (d: HTMLElement, selector: string) => [...d.querySelectorAll<HTMLButtonElement>(selector)]
const tarjetas = (d: HTMLElement) => botones(d, 'ul.grid button')
const filas = (d: HTMLElement) => botones(d, 'section ul button')

describe('clases del alumno: primero la materia, después sus clases', () => {
  const varias = [clase(1, 'Matemática', '2026-11-25'), clase(2, 'Lenguaje', '2026-11-24'), clase(3, 'Matemática', '2026-11-20'), clase(4, null, '2026-11-19')]

  it('con varias materias parte en una pantalla de materias, en orden alfabético y con su cantidad', async () => {
    const d = await montar(varias)
    expect(filas(d).length).toBe(0)
    expect(tarjetas(d).map((t) => t.textContent)).toEqual([
      expect.stringMatching(/^Lenguaje1 claseÚltima: .+/),
      expect.stringMatching(/^Matemática2 clasesÚltima: .+/),
      expect.stringMatching(/^Sin materia1 claseÚltima: .+/),
    ])
  })

  it('al tocar una materia quedan solo sus clases, con la más nueva primero, y se puede volver', async () => {
    const d = await montar(varias)
    await act(async () => tarjetas(d)[1].click())
    expect(d.querySelector('h2')?.textContent).toBe('Matemática')
    expect(filas(d).map((f) => f.textContent)).toEqual([expect.stringContaining('25 nov'), expect.stringContaining('20 nov')])
    const volver = botones(d, 'button').find((b) => b.textContent?.includes('Materias'))!
    await act(async () => volver.click())
    await act(async () => void (await new Promise((r) => setTimeout(r, 50)))) // «atrás» del historial es asíncrono
    expect(tarjetas(d).length).toBe(3)
  })

  it('los nombres vacíos, con espacios sobrantes o repetidos se juntan en un solo botón', async () => {
    const d = await montar([clase(1, '', '2026-11-25'), clase(2, '   ', '2026-11-24'), clase(3, null, '2026-11-23'), clase(4, 'Matemática ', '2026-11-22'), clase(5, 'Matemática', '2026-11-21')])
    expect(tarjetas(d).map((t) => t.textContent)).toEqual([expect.stringMatching(/^Matemática2 clases/), expect.stringMatching(/^Sin materia3 clases/)])
  })

  it('ordena de la más nueva a la más antigua aunque el servidor las mande al revés, y muestra el año si no es el actual', async () => {
    const d = await montar([clase(1, 'Matemática', '2025-03-04'), clase(2, 'Matemática', '2026-11-25'), clase(3, 'Matemática', '2026-11-20'), clase(4, 'Lenguaje', '2026-11-01')])
    await act(async () => tarjetas(d)[1].click())
    expect(filas(d).map((f) => f.textContent)).toEqual([expect.stringContaining('25 nov'), expect.stringContaining('20 nov'), expect.stringContaining('2025')])
  })

  it('con una sola materia va directo a la lista, sin pantalla de materias', async () => {
    const d = await montar([clase(1, 'Matemática', '2026-11-25'), clase(2, 'Matemática', '2026-11-20')])
    expect(tarjetas(d).length).toBe(0)
    expect(filas(d).length).toBe(2)
    expect(d.textContent).toContain('Matemática')
  })
})
