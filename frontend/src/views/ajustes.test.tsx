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
import type { AjusteFotos } from '@/lib/api'

vi.mock('@/lib/api', async (original) => ({ ...(await original<typeof import('@/lib/api')>()), api: vi.fn() }))

import { api } from '@/lib/api'
import { Ajustes } from '@/views/Ajustes'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const base: AjusteFotos = {
  activada: false, modelo: 'qwen2.5vl:3b', ollama_responde: true, modelo_instalado: false, memoria_total_gb: 15.6, memoria_recomendada_gb: 16, descarga: null,
}
let estado: AjusteFotos
let raices: Root[] = []
const llamadas = () => (api as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => `${c[1]?.metodo ?? 'GET'} ${c[0]}`)

beforeEach(() => {
  estado = { ...base }
  ;(api as unknown as ReturnType<typeof vi.fn>).mockReset().mockImplementation(async (_ruta: string, opciones?: { metodo?: string; cuerpo?: { activada?: boolean } }) => {
    if (opciones?.metodo === 'PUT') estado = { ...estado, activada: opciones.cuerpo!.activada! }
    if (opciones?.metodo === 'POST') estado = { ...estado, descarga: { estado: 'descargando', porcentaje: 0, mensaje: 'Preparando la descarga…' } }
    return estado
  })
})
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
})

async function montar() {
  const contenedor = document.createElement('div')
  document.body.append(contenedor)
  const raiz = createRoot(contenedor)
  raices.push(raiz)
  await act(async () => raiz.render(<Ajustes />))
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30))
  })
  return contenedor
}

async function violaciones(c: HTMLElement) {
  const r = await axe.run(c, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false }, 'landmark-one-main': { enabled: false }, 'page-has-heading-one': { enabled: false } },
  })
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const boton = (c: HTMLElement, texto: string) => [...c.querySelectorAll('button')].find((b) => b.textContent?.includes(texto)) as HTMLButtonElement | undefined
const interruptor = (c: HTMLElement) => c.querySelector('[role=switch]') as HTMLButtonElement

describe('Ajustes del colegio (el UTP decide en la aplicación, sin archivos ni comandos)', () => {
  it('muestra el estado y lo que hace falta para decidir, sin violaciones de accesibilidad', async () => {
    const c = await montar()
    expect(await violaciones(c)).toEqual([])
    expect(interruptor(c).getAttribute('aria-checked')).toBe('false')
    expect(interruptor(c).getAttribute('aria-labelledby')).toBe('etiqueta-fotos')
    expect(c.textContent).toContain('Apagadas: el botón no aparece.')
    expect(c.textContent).toContain('Este equipo tiene 15,6 GB de memoria: alcanza para leer fotos.')
    expect(c.textContent).toContain('Falta descargarlo (3,2 GB). Hace falta internet, y solo una vez.')
    expect(c.textContent).not.toMatch(/\.env|ollama pull|consola/i) // nada que obligue a tocar archivos o comandos
  })

  it('el interruptor activa las fotos para el colegio y lo anuncia', async () => {
    const c = await montar()
    await act(async () => interruptor(c).click())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(llamadas()).toContain('PUT /ajustes/fotos-pizarra')
    expect(interruptor(c).getAttribute('aria-checked')).toBe('true')
    expect(c.querySelector('[role=status].sr-only')?.textContent).toBe('Fotos de la pizarra activadas.')
    expect(c.textContent).toContain('Activadas: los profesores ven el botón')
  })

  it('al pulsar «Descargar el modelo» la barra aparece de inmediato, sin esperar la respuesta del servidor', async () => {
    const c = await montar()
    let terminar!: () => void
    const mock = api as unknown as ReturnType<typeof vi.fn>
    const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
    mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) =>
      opciones?.metodo === 'POST' ? new Promise((r) => (terminar = () => r(estado))) : anterior(ruta, opciones),
    )
    await act(async () => boton(c, 'Descargar el modelo')!.click())
    const barra = c.querySelector('[role=progressbar]')
    expect(barra).not.toBeNull() // el servidor todavía no contestó
    expect(barra!.getAttribute('aria-valuenow')).toBe('0')
    expect(c.textContent).toContain('Preparando la descarga… 0 %')
    expect(boton(c, 'Descargar el modelo')).toBeUndefined()
    await act(async () => terminar())
    expect(await violaciones(c)).toEqual([])
  })

  it('entre la respuesta del servidor y la siguiente consulta no reaparece el botón (la barra sigue)', async () => {
    const c = await montar()
    const mock = api as unknown as ReturnType<typeof vi.fn>
    const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
    let despuesDelPost = false
    mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) => {
      if (opciones?.metodo === 'POST') {
        despuesDelPost = true
        return Promise.resolve({ ...estado, descarga: { estado: 'descargando', porcentaje: 3, mensaje: 'Descargando…' } })
      }
      return despuesDelPost ? new Promise(() => {}) : anterior(ruta, opciones) // la consulta que sigue todavía no contesta
    })
    await act(async () => boton(c, 'Descargar el modelo')!.click())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(c.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('3') // salió de la respuesta del POST
    expect(boton(c, 'Descargar el modelo')).toBeUndefined()
  })

  it('el mismo interruptor las apaga si estaban activadas', async () => {
    estado = { ...base, activada: true }
    const c = await montar()
    expect(interruptor(c).getAttribute('aria-checked')).toBe('true')
    await act(async () => interruptor(c).click())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    const put = (api as unknown as ReturnType<typeof vi.fn>).mock.calls.find((k) => k[1]?.metodo === 'PUT')!
    expect(put[1].cuerpo).toEqual({ activada: false })
    expect(interruptor(c).getAttribute('aria-checked')).toBe('false')
    expect(c.querySelector('[role=status].sr-only')?.textContent).toBe('Fotos de la pizarra apagadas.')
  })

  it('con poca memoria avisa que las fotos se saltarán, y con Ollama cerrado igual deja descargar (la app lo abre sola)', async () => {
    estado = { ...base, memoria_total_gb: 7.8, ollama_responde: false }
    const c = await montar()
    expect(await violaciones(c)).toEqual([])
    expect(c.textContent).toContain('Es poca: lo normal es que las fotos se salten solas')
    expect(c.textContent).toContain('Se recomiendan 16 GB')
    expect(c.textContent).toContain('No responde por ahora. Al descargar el modelo la aplicación intenta abrirlo')
    expect(boton(c, 'Descargar el modelo')!.disabled).toBe(false)
  })

  it('si no se puede medir la memoria no inventa un número', async () => {
    estado = { ...base, memoria_total_gb: null }
    const c = await montar()
    expect(c.textContent).toContain('No se pudo medir la memoria de este equipo')
  })

  it('descargar el modelo desde la app: botón, barra de avance con su valor y aviso', async () => {
    const c = await montar()
    await act(async () => boton(c, 'Descargar el modelo')!.click())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(llamadas()).toContain('POST /ajustes/fotos-pizarra/modelo')
    estado = { ...estado, descarga: { estado: 'descargando', porcentaje: 41.6, mensaje: 'Descargando…' } }
    await act(async () => {
      await new Promise((r) => setTimeout(r, 3100)) // el sondeo de la pantalla lo recoge
    })
    const barra = c.querySelector('[role=progressbar]')!
    expect(barra.getAttribute('aria-valuenow')).toBe('42')
    expect(barra.getAttribute('aria-label')).toBe('Descarga del modelo')
    expect(c.textContent).toContain('Descargando… 42 %')
    expect(boton(c, 'Descargar el modelo')).toBeUndefined() // mientras baja no se puede pedir otra vez
    expect(await violaciones(c)).toEqual([])
  }, 10_000)

  it('si la descarga falla lo dice en palabras claras y deja reintentar; instalado ya no ofrece descargar', async () => {
    estado = { ...base, descarga: { estado: 'error', porcentaje: 30, mensaje: 'No se pudo descargar el modelo: el equipo no parece tener internet. Revisa la conexión y vuelve a intentarlo.' } }
    const c = await montar()
    expect(c.querySelector('[role=alert]')?.textContent).toContain('no parece tener internet')
    expect(boton(c, 'Reintentar la descarga')).toBeDefined()
    expect(await violaciones(c)).toEqual([])
    for (const r of raices.splice(0)) act(() => r.unmount())
    document.body.innerHTML = ''

    estado = { ...base, modelo_instalado: true }
    const c2 = await montar()
    expect(c2.textContent).toContain('Instalado.')
    expect(boton(c2, 'Descargar')).toBeUndefined()
    expect(await violaciones(c2)).toEqual([])
  })

  it('si el servidor no responde lo dice en vez de quedarse cargando', async () => {
    ;(api as unknown as ReturnType<typeof vi.fn>).mockReset().mockRejectedValue(new Error('sin red'))
    const c = await montar()
    expect(c.querySelector('[role=alert]')?.textContent).toContain('No se pudo conectar con el servidor')
  })
})
