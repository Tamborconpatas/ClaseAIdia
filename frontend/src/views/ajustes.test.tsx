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
import type { AjusteClases, AjusteConservacion, AjusteFotos, AjusteGrabaciones, AjusteModeloTexto, AjusteRespaldos, OpcionModelo } from '@/lib/api'

vi.mock('@/lib/api', async (original) => ({ ...(await original<typeof import('@/lib/api')>()), api: vi.fn() }))

import { api } from '@/lib/api'
import { Ajustes } from '@/views/Ajustes'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const base: AjusteFotos = {
  activada: false, modelo: 'qwen2.5vl:3b', ollama_responde: true, modelo_instalado: false, memoria_total_gb: 15.6, memoria_recomendada_gb: 16, descarga: null,
}
// El modelo de resúmenes empieza instalado: así las pruebas de las fotos no ven barras ni botones de la otra sección.
const opcion = (modelo: string, etiqueta: string, tamano: number): OpcionModelo => ({ modelo, etiqueta, nota: `Nota de ${etiqueta}.`, tamano_gb: tamano, instalado: true, descarga: null })
const baseTexto: AjusteModeloTexto = {
  modelo: 'gemma4:e2b', ollama_responde: true, modelo_instalado: true, memoria_total_gb: 15.6, memoria_minima_gb: 12, tamano_gb: 4.6, descarga: null, eleccion: 'auto',
  opciones: [opcion('gemma4:e2b', 'Gemma 4 E2B', 4.6), opcion('llama3.2:3b', 'Llama 3.2 3B', 2), opcion('llama3.2:1b', 'Llama 3.2 1B', 1.3)],
}
const baseClases: AjusteClases = { horas_revision: 24, minutos_corte: 15, horas_revision_por_defecto: 24, minutos_corte_por_defecto: 15, rango_horas_revision: [1, 168], rango_minutos_corte: [0, 120] }
const baseRespaldos: AjusteRespaldos = { carpeta: '/datos/respaldos', carpeta_por_defecto: '/datos/respaldos', dias: 14, dias_por_defecto: 14, rango_dias: [1, 365] }
let estado: AjusteFotos
let texto: AjusteModeloTexto
let clases: AjusteClases
let respaldos: AjusteRespaldos
let receso: AjusteGrabaciones
let conservacion: AjusteConservacion
let borrarian = 0 // lo que la vista previa dice que se borraría
let raices: Root[] = []
const llamadas = () => (api as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => `${c[1]?.metodo ?? 'GET'} ${c[0]}`)

beforeEach(() => {
  estado = { ...base }
  texto = { ...baseTexto }
  clases = { ...baseClases }
  respaldos = { ...baseRespaldos }
  receso = { activas: true, hasta: null, anio_cerrado: false }
  conservacion = { dias: 365, dias_por_defecto: 365, rango_dias: [90, 730], se_borrarian: 0 }
  borrarian = 0
  ;(api as unknown as ReturnType<typeof vi.fn>).mockReset().mockImplementation(async (ruta: string, opciones?: { metodo?: string; cuerpo?: Record<string, unknown> & { activada?: boolean } }) => {
    if (ruta === '/ajustes/clases') {
      if (opciones?.metodo === 'PUT') {
        const c = opciones.cuerpo as { horas_revision: number | null; minutos_corte: number | null }
        clases = { ...clases, horas_revision: c.horas_revision ?? clases.horas_revision_por_defecto, minutos_corte: c.minutos_corte ?? clases.minutos_corte_por_defecto }
      }
      return clases
    }
    if (ruta === '/ajustes/grabaciones') {
      if (opciones?.metodo === 'PUT') {
        const c = opciones.cuerpo as { activas: boolean; hasta: string | null }
        receso = { ...receso, activas: c.activas, hasta: c.activas ? null : c.hasta }
      }
      return receso
    }
    if (ruta.startsWith('/ajustes/conservacion')) {
      if (opciones?.metodo === 'PUT') conservacion = { ...conservacion, dias: (opciones.cuerpo as { dias: number | null }).dias ?? conservacion.dias_por_defecto }
      return { ...conservacion, se_borrarian: opciones?.metodo === 'PUT' ? 0 : borrarian, borradas: opciones?.metodo === 'PUT' ? borrarian : undefined }
    }
    if (ruta === '/ajustes/respaldos') {
      if (opciones?.metodo === 'PUT') {
        const c = opciones.cuerpo as { carpeta: string | null; dias: number | null }
        respaldos = { ...respaldos, carpeta: c.carpeta ?? respaldos.carpeta_por_defecto, dias: c.dias ?? respaldos.dias_por_defecto }
      }
      return respaldos
    }
    if (ruta.startsWith('/ajustes/modelo-texto')) {
      const cuerpo = opciones?.cuerpo as { modelo?: string } | undefined
      const bajando = { estado: 'descargando' as const, porcentaje: 0, mensaje: 'Preparando la descarga…' }
      if (opciones?.metodo === 'PUT') texto = { ...texto, eleccion: cuerpo!.modelo!, modelo: cuerpo!.modelo === 'auto' ? 'gemma4:e2b' : cuerpo!.modelo! }
      if (opciones?.metodo === 'POST') {
        texto = cuerpo?.modelo
          ? { ...texto, opciones: texto.opciones.map((o) => (o.modelo === cuerpo.modelo ? { ...o, descarga: bajando } : o)) }
          : { ...texto, descarga: bajando }
      }
      return texto
    }
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
const campo = (c: HTMLElement, id: string) => c.querySelector(`#${id}`) as HTMLInputElement
async function escribir(c: HTMLElement, id: string, valor: string) {
  const el = campo(c, id)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, valor) // así React se entera, como si se hubiera tecleado
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const pulsar = async (b: HTMLButtonElement | undefined) => {
  await act(async () => b!.click())
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30))
  })
}
const put = (ruta: string) => (api as unknown as ReturnType<typeof vi.fn>).mock.calls.filter((k) => k[0] === ruta && k[1]?.metodo === 'PUT').map((k) => k[1].cuerpo)

async function escribirFecha(c: HTMLElement, id: string, valor: string) {
  const el = campo(c, id)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, valor)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const interruptorReceso = (c: HTMLElement) => c.querySelector('[aria-labelledby=etiqueta-receso]') as HTMLButtonElement

describe('Fin de clases y vacaciones: el UTP apaga las grabaciones sin archivos ni comandos', () => {
  it('parte activado y el interruptor las pone en pausa y las reactiva, anunciándolo', async () => {
    const c = await montar()
    expect(c.textContent).toContain('Fin de clases y vacaciones')
    expect(interruptorReceso(c).getAttribute('aria-checked')).toBe('true')
    expect(c.textContent).toContain('Activadas: los profesores pueden grabar sus clases.')
    await pulsar(interruptorReceso(c))
    expect(put('/ajustes/grabaciones')).toEqual([{ activas: false, hasta: null }])
    expect(interruptorReceso(c).getAttribute('aria-checked')).toBe('false')
    expect(c.textContent).toContain('En pausa: nadie puede empezar a grabar.')
    expect([...c.querySelectorAll('[role=status].sr-only')].map((x) => x.textContent)).toContain('Grabaciones en pausa.')
    await pulsar(interruptorReceso(c))
    expect(put('/ajustes/grabaciones')).toEqual([{ activas: false, hasta: null }, { activas: true, hasta: null }])
    expect(interruptorReceso(c).getAttribute('aria-checked')).toBe('true')
  })

  it('con una fecha de regreso, la pausa la lleva y dice cuándo se reactiva sola', async () => {
    const c = await montar()
    await escribirFecha(c, 'fecha-regreso', '2027-03-04')
    await pulsar(interruptorReceso(c))
    expect(put('/ajustes/grabaciones')).toEqual([{ activas: false, hasta: '2027-03-04' }])
    expect(c.textContent).toContain('En pausa: se reactivan solas el 4 de marzo de 2027.')
    await pulsar(interruptorReceso(c)) // al reactivar a mano la fecha se olvida
    expect(put('/ajustes/grabaciones')[1]).toEqual({ activas: true, hasta: null })
    expect((c.querySelector('#fecha-regreso') as HTMLInputElement).value).toBe('')
  })

  it('en pausa se puede poner, cambiar o quitar la fecha de regreso sin reactivar', async () => {
    const c = await montar()
    await pulsar(interruptorReceso(c))
    expect(boton(c, 'Guardar la fecha')).toBeUndefined()
    await escribirFecha(c, 'fecha-regreso', '2027-03-04')
    await pulsar(boton(c, 'Guardar la fecha'))
    expect(put('/ajustes/grabaciones')[1]).toEqual({ activas: false, hasta: '2027-03-04' })
    await escribirFecha(c, 'fecha-regreso', '')
    await pulsar(boton(c, 'Quitar la fecha'))
    expect(put('/ajustes/grabaciones')[2]).toEqual({ activas: false, hasta: null })
    expect(c.textContent).toContain('En pausa: nadie puede empezar a grabar.')
  })

  it('con el año cerrado el interruptor no se puede activar a mano: pide preparar el año nuevo', async () => {
    receso = { activas: false, hasta: null, anio_cerrado: true }
    const c = await montar()
    expect(interruptorReceso(c).disabled).toBe(true)
    expect(c.querySelector('[role=note]')?.textContent).toContain('«Cursos» → «Preparar el año nuevo»')
    await pulsar(interruptorReceso(c))
    expect(put('/ajustes/grabaciones')).toEqual([])
  })

  it('si no se puede guardar, lo dice y el interruptor queda como estaba', async () => {
    const c = await montar()
    const antes = (api as unknown as ReturnType<typeof vi.fn>).getMockImplementation()! as (ruta: string, o?: unknown) => Promise<unknown>
    ;(api as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (ruta: string, o?: { metodo?: string }) => {
      if (ruta === '/ajustes/grabaciones' && o?.metodo === 'PUT') throw new Error('No se pudo guardar')
      return antes(ruta, o)
    })
    await pulsar(interruptorReceso(c))
    expect(c.textContent).toContain('No se pudo guardar')
    expect(interruptorReceso(c).getAttribute('aria-checked')).toBe('true')
  })
})

const sec = (c: HTMLElement) => c.querySelector('section[aria-labelledby=titulo-conservacion]') as HTMLElement

describe('Cuánto tiempo se guardan las clases: el plazo se cambia con aviso antes de borrar', () => {
  it('muestra el plazo y cambiarlo sin nada por borrar guarda directo', async () => {
    const c = await montar()
    expect(c.textContent).toContain('Cuánto tiempo se guardan las clases')
    expect(campo(c, 'dias-conservacion').value).toBe('365')
    await escribir(c, 'dias-conservacion', '500')
    await pulsar(boton(sec(c), 'Guardar'))
    expect(put('/ajustes/conservacion')).toEqual([{ dias: 500 }])
    expect(sec(c).textContent).toContain('Guardado.')
    expect(sec(c).textContent).not.toContain('Guardar y borrar')
  })

  it('si el plazo nuevo borraría clases, dice cuántas y no guarda hasta que se confirma', async () => {
    borrarian = 12
    const c = await montar()
    await escribir(c, 'dias-conservacion', '180')
    await pulsar(boton(sec(c), 'Guardar'))
    expect(put('/ajustes/conservacion')).toEqual([])
    expect(c.querySelector('[role=alert]')?.textContent).toContain('se borrarán ahora 12 clases')
    await pulsar(boton(sec(c), 'Cancelar'))
    expect(put('/ajustes/conservacion')).toEqual([])
    await pulsar(boton(sec(c), 'Guardar'))
    await pulsar(boton(sec(c), 'Guardar y borrar'))
    expect(put('/ajustes/conservacion')).toEqual([{ dias: 180 }])
    expect(sec(c).textContent).toContain('Guardado. Se borraron 12 clases que ya pasaron el plazo.')
  })

  it('no deja guardar un plazo fuera de rango y puede volver al predeterminado', async () => {
    const c = await montar()
    await escribir(c, 'dias-conservacion', '30')
    expect(boton(sec(c), 'Guardar')!.disabled).toBe(true)
    expect(sec(c).textContent).toContain('Escribe un número entero de 90 a 730.')
    await escribir(c, 'dias-conservacion', '200')
    await pulsar(boton(sec(c), 'Guardar'))
    await pulsar(boton(sec(c), 'Volver a 365 días'))
    expect(put('/ajustes/conservacion')).toEqual([{ dias: 200 }, { dias: null }])
    expect(campo(c, 'dias-conservacion').value).toBe('365')
  })
})

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
    await act(async () => boton(c, 'Descargar el modelo de imágenes')!.click())
    const barra = c.querySelector('[role=progressbar]')
    expect(barra).not.toBeNull() // el servidor todavía no contestó
    expect(barra!.getAttribute('aria-valuenow')).toBe('0')
    expect(c.textContent).toContain('Preparando la descarga… 0 %')
    expect(boton(c, 'Descargar el modelo de imágenes')).toBeUndefined()
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
    await act(async () => boton(c, 'Descargar el modelo de imágenes')!.click())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(c.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('3') // salió de la respuesta del POST
    expect(boton(c, 'Descargar el modelo de imágenes')).toBeUndefined()
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
    expect(boton(c, 'Descargar el modelo de imágenes')!.disabled).toBe(false)
  })

  it('si no se puede medir la memoria no inventa un número', async () => {
    estado = { ...base, memoria_total_gb: null }
    const c = await montar()
    expect(c.textContent).toContain('No se pudo medir la memoria de este equipo')
  })

  it('descargar el modelo desde la app: botón, barra de avance con su valor y aviso', async () => {
    const c = await montar()
    await act(async () => boton(c, 'Descargar el modelo de imágenes')!.click())
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
    expect(boton(c, 'Descargar el modelo de imágenes')).toBeUndefined() // mientras baja no se puede pedir otra vez
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
  describe('modelo que escribe los resúmenes (necesario: se baja desde la app, no con una consola)', () => {
    it('si falta, el UTP ve cuánto pesa y lo baja con un botón; la barra aparece de inmediato', async () => {
      texto = { ...baseTexto, modelo_instalado: false }
      const c = await montar()
      expect(c.textContent).toContain('Modelo que escribe los resúmenes')
      expect(c.textContent).toContain('(gemma4:e2b)')
      expect(c.textContent).toContain('Falta descargarlo (4,6 GB). Hace falta internet, y solo una vez.')
      expect(c.textContent).toContain('Este equipo tiene 15,6 GB de memoria: alcanza.')
      expect(c.textContent).not.toMatch(/\.env|ollama pull|consola/i)
      expect(await violaciones(c)).toEqual([])
      await act(async () => boton(c, 'Descargar el modelo de resúmenes')!.click())
      await act(async () => {
        await new Promise((r) => setTimeout(r, 30))
      })
      expect(llamadas()).toContain('POST /ajustes/modelo-texto/descargar')
      expect(llamadas()).not.toContain('POST /ajustes/fotos-pizarra/modelo') // no se confunde con el de las fotos
      expect(c.querySelector('[role=progressbar]')).not.toBeNull()
      expect(boton(c, 'Descargar el modelo de resúmenes')).toBeUndefined() // mientras baja no se puede pedir otra vez
      expect(await violaciones(c)).toEqual([])
    })

    it('instalado, solo lo dice; y de un modelo que fijó quien administra el servidor no inventa un tamaño', async () => {
      const c = await montar()
      expect(c.textContent).toContain('Instalado.')
      expect(boton(c, 'resúmenes')).toBeUndefined()
      for (const r of raices.splice(0)) act(() => r.unmount())
      document.body.innerHTML = ''
      texto = { ...baseTexto, modelo: 'qwen2.5:7b', modelo_instalado: false, tamano_gb: null }
      const c2 = await montar()
      expect(c2.textContent).toContain('Falta descargarlo. Hace falta internet')
    })

    it('con poca memoria avisa que se usará un modelo más liviano, sin trabar la descarga', async () => {
      texto = { ...baseTexto, modelo_instalado: false, memoria_total_gb: 7.8 }
      const c = await montar()
      expect(c.textContent).toContain('Es poca: si el modelo no cabe, la aplicación usa uno más liviano')
      expect(c.textContent).toContain('Se recomiendan 12 GB')
      expect(boton(c, 'Descargar el modelo de resúmenes')!.disabled).toBe(false)
      expect(await violaciones(c)).toEqual([])
    })

    it('si el servidor rechaza el pedido lo dice en la pantalla', async () => {
      texto = { ...baseTexto, modelo_instalado: false }
      const mock = api as unknown as ReturnType<typeof vi.fn>
      const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
      mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) =>
        ruta === '/ajustes/modelo-texto/descargar' ? Promise.reject(new Error('Ya se está descargando')) : anterior(ruta, opciones),
      )
      const c = await montar()
      await act(async () => boton(c, 'Descargar el modelo de resúmenes')!.click())
      await act(async () => {
        await new Promise((r) => setTimeout(r, 30))
      })
      expect(c.querySelector('[role=alert]')?.textContent).toContain('Ya se está descargando')
    })
  })
  describe('cómo se tratan las clases (plazo de revisión y corte automático) y el respaldo diario', () => {
    it('muestra lo que vale hoy y lo predeterminado; no deja guardar mientras no cambie nada', async () => {
      const c = await montar()
      expect(c.textContent).toContain('Revisión y corte de las clases')
      expect(campo(c, 'horas-revision').value).toBe('24')
      expect(campo(c, 'minutos-corte').value).toBe('15')
      expect(c.textContent).toContain('Lo predeterminado es 24 horas.')
      expect(c.textContent).toContain('Lo predeterminado es 15 minutos.')
      expect(boton(c, 'Volver a lo predeterminado')).toBeUndefined() // ya vale lo predeterminado
      expect(await violaciones(c)).toEqual([])
    })

    it('el UTP cambia el plazo: se manda con el corte, se avisa y aparece «Volver a lo predeterminado»', async () => {
      const c = await montar()
      await escribir(c, 'horas-revision', '48')
      const guardar = [...c.querySelectorAll('form')][0].querySelector('button[type=submit]') as HTMLButtonElement
      expect(guardar.disabled).toBe(false)
      await pulsar(guardar)
      expect(put('/ajustes/clases')).toEqual([{ horas_revision: 48, minutos_corte: 15 }])
      expect(c.textContent).toContain('Guardado. Vale desde ahora.')
      expect(campo(c, 'horas-revision').value).toBe('48')
      await pulsar(boton(c, 'Volver a lo predeterminado'))
      expect(put('/ajustes/clases')[1]).toEqual({ horas_revision: null, minutos_corte: null })
      expect(campo(c, 'horas-revision').value).toBe('24')
      expect(boton(c, 'Volver a lo predeterminado')).toBeUndefined()
      expect(await violaciones(c)).toEqual([])
    })

    it('un valor fuera de rango se marca y no se puede guardar', async () => {
      const c = await montar()
      await escribir(c, 'horas-revision', '0')
      expect(c.textContent).toContain('Escribe un número entero de 1 a 168.')
      expect(campo(c, 'horas-revision').getAttribute('aria-invalid')).toBe('true')
      expect(([...c.querySelectorAll('form')][0].querySelector('button[type=submit]') as HTMLButtonElement).disabled).toBe(true)
      await escribir(c, 'minutos-corte', '0') // cero minutos sí vale: el corte es justo al terminar el bloque
      expect(campo(c, 'minutos-corte').getAttribute('aria-invalid')).toBe('false')
      expect(await violaciones(c)).toEqual([])
    })

    it('si el servidor rechaza el valor, lo dice y no cambia lo que se ve guardado', async () => {
      const c = await montar()
      const mock = api as unknown as ReturnType<typeof vi.fn>
      const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
      mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) =>
        ruta === '/ajustes/clases' && opciones?.metodo === 'PUT' ? Promise.reject(new Error('Plazo de revisión: escribe un número entero de 1 a 168 horas.')) : anterior(ruta, opciones),
      )
      await escribir(c, 'horas-revision', '30')
      await pulsar([...c.querySelectorAll('form')][0].querySelector('button[type=submit]') as HTMLButtonElement)
      expect(c.querySelector('[role=alert]')?.textContent).toContain('Plazo de revisión')
      expect(c.textContent).not.toContain('Guardado. Vale desde ahora.')
    })

    it('el respaldo: carpeta y días se mandan juntos; lo que es igual a lo predeterminado se manda como null', async () => {
      const c = await montar()
      expect(c.textContent).toContain('Respaldo diario')
      expect(campo(c, 'carpeta-respaldos').value).toBe('/datos/respaldos')
      expect(c.textContent).toContain('Esto vale para todo el servidor.')
      await escribir(c, 'carpeta-respaldos', '/discoB/respaldos')
      const guardar = [...c.querySelectorAll('form')][1].querySelector('button[type=submit]') as HTMLButtonElement
      await pulsar(guardar)
      expect(put('/ajustes/respaldos')).toEqual([{ carpeta: '/discoB/respaldos', dias: null }])
      expect(c.textContent).toContain('Guardado. Vale desde el próximo respaldo')
      await escribir(c, 'dias-respaldo', '30')
      await pulsar([...c.querySelectorAll('form')][1].querySelector('button[type=submit]') as HTMLButtonElement)
      expect(put('/ajustes/respaldos')[1]).toEqual({ carpeta: '/discoB/respaldos', dias: 30 })
      await pulsar(boton(c, 'Volver a lo predeterminado'))
      expect(campo(c, 'carpeta-respaldos').value).toBe('/datos/respaldos')
      expect(await violaciones(c)).toEqual([])
    })

    it('si la carpeta no sirve, el servidor dice por qué y la pantalla lo muestra', async () => {
      const c = await montar()
      const mock = api as unknown as ReturnType<typeof vi.fn>
      const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
      mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) =>
        ruta === '/ajustes/respaldos' && opciones?.metodo === 'PUT' ? Promise.reject(new Error('No se puede guardar nada en esa carpeta. Elige otra o revisa los permisos.')) : anterior(ruta, opciones),
      )
      await escribir(c, 'carpeta-respaldos', '/solo/lectura')
      await pulsar([...c.querySelectorAll('form')][1].querySelector('button[type=submit]') as HTMLButtonElement)
      expect(c.querySelector('[role=alert]')?.textContent).toContain('No se puede guardar nada en esa carpeta')
      expect(c.textContent).not.toContain('Guardado. Vale desde el próximo respaldo')
    })
  })
  describe('elegir otro modelo de resumen (opcional, solo entre los que la aplicación ofrece y ya están descargados)', () => {
    const fila = (c: HTMLElement, etiqueta: string) => [...c.querySelectorAll('details li')].find((li) => li.querySelector('p')?.textContent?.startsWith(etiqueta)) as HTMLElement  // por el nombre de la fila, no por su nota

    it('el desplegable lista «Automático» y las opciones, con cuál está en uso y qué falta', async () => {
      texto = { ...baseTexto, opciones: baseTexto.opciones.map((o) => (o.modelo === 'llama3.2:3b' ? { ...o, instalado: false } : o)) }
      const c = await montar()
      const d = c.querySelector('details') as HTMLDetailsElement
      expect(d.textContent).toContain('Usar otro modelo (opcional)')
      expect(d.open).toBe(false) // la vista normal sigue siendo simple
      d.open = true
      expect(fila(c, 'Automático (recomendado)').textContent).toContain('En uso')
      expect(fila(c, 'Gemma 4 E2B').textContent).toContain('Nota de Gemma 4 E2B.')
      expect(fila(c, 'Llama 3.2 3B').textContent).toContain('No está descargado en este equipo.')
      expect(fila(c, 'Llama 3.2 3B').querySelector('button')!.textContent).toContain('Descargar (2 GB)')
      expect(fila(c, 'Llama 3.2 1B').querySelector('button')!.getAttribute('aria-label')).toBe('Usar Llama 3.2 1B')
      expect(c.textContent).not.toMatch(/\.env|ollama pull|consola/i)
      expect(await violaciones(c)).toEqual([])
    })

    it('un modelo instalado se pone en uso con un botón, se avisa cuándo vale, y «Automático» lo deshace', async () => {
      const c = await montar()
      await pulsar(c.querySelector('button[aria-label="Usar Llama 3.2 1B"]') as HTMLButtonElement)
      expect(put('/ajustes/modelo-texto')).toEqual([{ modelo: 'llama3.2:1b' }])
      expect(c.textContent).toContain('Listo: se usará Llama 3.2 1B desde la próxima clase.')
      expect(fila(c, 'Llama 3.2 1B').textContent).toContain('En uso')
      expect(fila(c, 'Automático (recomendado)').textContent).not.toContain('En uso')
      await pulsar(c.querySelector('button[aria-label="Usar Automático (recomendado)"]') as HTMLButtonElement)
      expect(put('/ajustes/modelo-texto')[1]).toEqual({ modelo: 'auto' })
      expect(fila(c, 'Automático (recomendado)').textContent).toContain('En uso')
      expect(await violaciones(c)).toEqual([])
    })

    it('un modelo que falta se descarga desde su fila, con su propia barra de avance', async () => {
      texto = { ...baseTexto, opciones: baseTexto.opciones.map((o) => (o.modelo === 'llama3.2:3b' ? { ...o, instalado: false } : o)) }
      const c = await montar()
      await pulsar(c.querySelector('button[aria-label="Descargar Llama 3.2 3B"]') as HTMLButtonElement)
      const k = (api as unknown as ReturnType<typeof vi.fn>).mock.calls.find((x) => x[0] === '/ajustes/modelo-texto/descargar')!
      expect(k[1]).toEqual({ metodo: 'POST', cuerpo: { modelo: 'llama3.2:3b' } })
      expect(fila(c, 'Llama 3.2 3B').querySelector('[role=progressbar]')).not.toBeNull()
      expect(fila(c, 'Gemma 4 E2B').querySelector('[role=progressbar]')).toBeNull() // cada modelo, su propio avance
      expect(c.querySelector('button[aria-label="Descargar Llama 3.2 3B"]')).toBeNull() // mientras baja no se pide otra vez
    })

    it('si el servidor rechaza la elección lo dice, y con Ollama cerrado solo queda «Automático»', async () => {
      const mock = api as unknown as ReturnType<typeof vi.fn>
      const anterior = mock.getMockImplementation() as (...a: unknown[]) => unknown
      mock.mockImplementation((ruta: string, opciones?: { metodo?: string }) =>
        ruta === '/ajustes/modelo-texto' && opciones?.metodo === 'PUT' ? Promise.reject(new Error('Ese modelo todavía no está descargado en este equipo. Descárgalo primero y después úsalo.')) : anterior(ruta, opciones),
      )
      const c = await montar()
      await pulsar(c.querySelector('button[aria-label="Usar Llama 3.2 1B"]') as HTMLButtonElement)
      expect(c.querySelector('[role=alert]')?.textContent).toContain('todavía no está descargado')
      for (const r of raices.splice(0)) act(() => r.unmount())
      document.body.innerHTML = ''
      texto = { ...baseTexto, eleccion: 'llama3.2:1b', modelo: 'llama3.2:1b', ollama_responde: false, modelo_instalado: false, opciones: baseTexto.opciones.map((o) => ({ ...o, instalado: null })) }
      const c2 = await montar()
      expect(c2.querySelectorAll('details button[aria-label^="Usar "]').length).toBe(1) // solo «Automático»: lo demás no se puede comprobar
      expect(c2.textContent).toContain('Ollama no responde: no se sabe si está descargado.')
    })
  })
})
