// @vitest-environment jsdom
import axe from 'axe-core'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EstadoServidor } from '@/lib/api'

vi.mock('@/lib/api', async (original) => ({ ...(await original<typeof import('@/lib/api')>()), api: vi.fn() }))

import { api } from '@/lib/api'
import { Estado } from '@/views/Estado'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const sano: EstadoServidor = {
  generado_en: '2026-10-02T15:00:00Z',
  alertas: [],
  procesamiento: { en_vivo: [], procesando: [], con_reintento: [], con_error: [], terminadas_24h: 3 },
  ollama: { responde: true, modelo_texto: 'llama3.2:1b o llama3.2:3b', modelo_texto_instalado: true },
  disco: { libre_gb: 120.4, total_gb: 465.2, audio_temporal_mb: 0, fotos_temporales_mb: 0, base_de_datos_mb: 3.2 },
  respaldos: { carpeta: 'respaldos', cantidad: 5, mb: 16, ultimo: '2026-10-02', hace_dias: 0, en_el_mismo_disco: false },
  memoria: { total_gb: 15.6, libre_gb: 9.3 },
  vigilancia: { ultima_pasada: '2026-10-02T14:59:55Z', activa: true },
}
const mock = () => api as unknown as ReturnType<typeof vi.fn>
let raices: Root[] = []

beforeEach(() => {
  mock().mockReset().mockResolvedValue(sano)
})
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
  vi.useRealTimers()
})

async function montar(estado: EstadoServidor = sano) {
  mock().mockResolvedValue(estado)
  const contenedor = document.createElement('div')
  document.body.append(contenedor)
  const raiz = createRoot(contenedor)
  raices.push(raiz)
  await act(async () => raiz.render(<Estado />))
  await esperar(30)
  return contenedor
}

/** Deja pasar `ms` (con relojes falsos los adelanta; con los reales espera de verdad). */
const esperar = (ms: number) => act(async () => (vi.isFakeTimers() ? vi.advanceTimersByTimeAsync(ms) : new Promise((r) => setTimeout(r, ms))).then(() => undefined))

async function violaciones(c: HTMLElement) {
  const r = await axe.run(c, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false }, 'landmark-one-main': { enabled: false }, 'page-has-heading-one': { enabled: false } },
  })
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

/** Lo que dice la fila de la lista de revisión de ese título (incluido el «en orden / falta revisar» para el lector de pantalla). */
const fila = (c: HTMLElement, titulo: string) => [...c.querySelectorAll('li')].find((li) => li.querySelector('p.font-medium')?.textContent?.startsWith(titulo))?.textContent ?? ''
const clase = <const T extends object>(curso: string, asignatura: string | null, extra: T = {} as T) => ({ clase_id: 1, curso, asignatura, fecha: '2026-10-02', ...extra })

describe('Panel de estado del UTP', () => {
  it('con el servidor sano dice que todo está en orden, sin violaciones de accesibilidad', async () => {
    const c = await montar()
    expect(await violaciones(c)).toEqual([])
    expect(c.querySelector('h2')?.textContent).toBe('Todo en orden.')
    expect(c.querySelector('[role=status].sr-only')?.textContent).toBe('Todo en orden.')
    expect(c.textContent).toContain('No hay ninguna clase grabándose ni procesándose ahora.')
    expect(c.textContent).toContain('Terminadas en las últimas 24 horas: 3.')
    for (const t of ['Programa de IA', 'Espacio en disco', 'Respaldos', 'Memoria', 'Vigilancia']) expect(fila(c, t)).toContain('en orden')
    expect(c.querySelector('[role=alert]')).toBeNull()
    expect(c.querySelector('section')!.querySelector('ul')).toBeNull() // sin avisos no hay lista vacía
    expect(c.querySelector('section')!.className).toContain('bg-emerald-100')
  })

  it('muestra los datos del equipo en palabras de persona', async () => {
    const c = await montar()
    expect(fila(c, 'Programa de IA')).toContain('Funcionando, con el modelo de resúmenes instalado.')
    expect(fila(c, 'Espacio en disco')).toContain('120,4 GB libres de 465,2 GB. Audio temporal: 0 MB. Fotos temporales: 0 MB. Base de datos: 3,2 MB.')
    expect(fila(c, 'Respaldos')).toContain('Último: hoy. 5 copias (16 MB).')
    expect(fila(c, 'Respaldos')).toContain('Carpeta: respaldos')
    expect(fila(c, 'Respaldos')).not.toContain('mismo disco')
    expect(fila(c, 'Memoria')).toContain('9,3 GB libres de 15,6 GB.')
    expect(fila(c, 'Vigilancia')).toContain('Funcionando (última revisión hace 5 s).')
  })

  it('cada aviso se ve con su gravedad, el resumen los cuenta y marca solo la fila afectada', async () => {
    const c = await montar({
      ...sano,
      alertas: [
        { tema: 'disco', nivel: 'critico', texto: 'Quedan solo 1.2 GB libres en el disco.' },
        { tema: 'respaldos', nivel: 'aviso', texto: 'Los respaldos están en el mismo disco.' },
        { tema: 'ollama', nivel: 'critico', texto: 'Falta el modelo.' },
      ],
      disco: { ...sano.disco, libre_gb: 1.2 },
    })
    expect(await violaciones(c)).toEqual([])
    expect(c.querySelector('h2')?.textContent).toBe('2 problemas urgentes y 1 aviso.')
    expect(c.querySelector('[role=status].sr-only')?.textContent).toBe('2 problemas urgentes y 1 aviso.')
    const avisos = [...c.querySelectorAll('section')[0].querySelectorAll('li')].map((li) => li.textContent)
    expect(avisos).toEqual(['Urgente: Quedan solo 1.2 GB libres en el disco.', 'Aviso: Los respaldos están en el mismo disco.', 'Urgente: Falta el modelo.'])
    expect(fila(c, 'Espacio en disco')).toContain('falta revisar')
    expect(fila(c, 'Respaldos')).toContain('falta revisar')
    expect(fila(c, 'Programa de IA')).toContain('falta revisar')
    expect(fila(c, 'Memoria')).toContain('en orden')
    expect(fila(c, 'Vigilancia')).toContain('en orden')
  })

  it('la memoria y la vigilancia también marcan su fila cuando tienen un aviso', async () => {
    const c = await montar({
      ...sano,
      alertas: [
        { tema: 'memoria', nivel: 'aviso', texto: 'Poca memoria.' },
        { tema: 'vigilancia', nivel: 'critico', texto: 'La vigilancia no responde.' },
      ],
      memoria: { total_gb: 15.6, libre_gb: 1.2 },
      vigilancia: { ultima_pasada: null, activa: false },
    })
    expect(fila(c, 'Memoria')).toContain('falta revisar')
    expect(fila(c, 'Vigilancia')).toContain('falta revisar')
    for (const t of ['Programa de IA', 'Espacio en disco', 'Respaldos']) expect(fila(c, t)).toContain('en orden')
  })

  it('el color acompaña la gravedad: rojo si hay algo urgente, ámbar si solo hay avisos', async () => {
    let c = await montar({ ...sano, alertas: [{ tema: 'disco', nivel: 'critico', texto: 'Disco lleno.' }] })
    expect(c.querySelector('section')!.className).toContain('bg-red-100')
    expect(c.querySelector('section')!.className).not.toContain('bg-amber-100')
    for (const r of raices.splice(0)) act(() => r.unmount())
    document.body.innerHTML = ''
    c = await montar({ ...sano, alertas: [{ tema: 'disco', nivel: 'aviso', texto: 'Disco justo.' }] })
    expect(c.querySelector('section')!.className).toContain('bg-amber-100')
    expect(c.querySelector('section')!.className).not.toContain('bg-red-100')
  })

  it('solo urgentes: el resumen no deja un «y» colgando', async () => {
    const c = await montar({ ...sano, alertas: [{ tema: 'vigilancia', nivel: 'critico', texto: 'No responde.' }] })
    expect(c.querySelector('h2')?.textContent).toBe('1 problema urgente.')
    expect(fila(c, 'Vigilancia')).toContain('falta revisar') // solo la suya
    expect(fila(c, 'Memoria')).toContain('en orden')
  })

  it('el resumen usa el singular y no inventa urgentes cuando solo hay avisos', async () => {
    let c = await montar({ ...sano, alertas: [{ tema: 'memoria', nivel: 'aviso', texto: 'Poca memoria.' }] })
    expect(c.querySelector('h2')?.textContent).toBe('1 aviso.')
    for (const r of raices.splice(0)) act(() => r.unmount())
    document.body.innerHTML = ''
    c = await montar({ ...sano, alertas: [{ tema: 'vigilancia', nivel: 'critico', texto: 'No responde.' }, { tema: 'memoria', nivel: 'aviso', texto: 'a' }, { tema: 'disco', nivel: 'aviso', texto: 'b' }] })
    expect(c.querySelector('h2')?.textContent).toBe('1 problema urgente y 2 avisos.')
  })

  it('cada clase aparece en su grupo, con curso, asignatura, fecha y lo que le pasa; los grupos vacíos no se dibujan', async () => {
    const c = await montar({
      ...sano,
      procesamiento: {
        en_vivo: [clase('8A', 'Matemática', { clase_id: 1, estado: 'grabando' })],
        procesando: [clase('8B', 'Historia', { clase_id: 2, turno: 'ahora', minutos: 7 }), clase('7A', 'Lenguaje', { clase_id: 3, turno: 'espera', minutos: null })],
        con_reintento: [clase('1M', 'Física', { clase_id: 4, intentos: 2, reintento_en: '2026-10-02T15:15:00Z', error: 'Ollama apagado. Se reintentará sola.' })],
        con_error: [clase('2M', 'Química', { clase_id: 5, error: 'No se oyó voz.' })],
        terminadas_24h: 0,
      },
    })
    expect(await violaciones(c)).toEqual([])
    const texto = c.textContent!
    expect(texto).not.toContain('No hay ninguna clase')
    expect(texto).toContain('8A · Matemática')
    expect(texto).toContain('grabando.')
    expect(texto).toContain('8B · Historia')
    expect(texto).toContain('procesándose ahora (hace 7 min).')
    expect(texto).toContain('7A · Lenguaje')
    expect(texto).toContain('en espera de su turno.')
    expect(texto).toContain('reintento en unos 15 min (intento 2).')
    expect(texto).toContain('Ollama apagado. Se reintentará sola.')
    expect(texto).toContain('No se oyó voz.')
    expect(texto).toContain('el profesor puede reintentarla desde «Grabar».')
    expect(texto).toMatch(/oct/) // la fecha de la clase
    expect([...c.querySelectorAll('h3')].map((h) => h.textContent)).toEqual(['Grabándose', 'Procesándose', 'Fallaron y se reintentan solas', 'Con error y sin reintento'])
  })

  it('una clase procesándose ahora sin minutos conocidos no escribe «hace null min»', async () => {
    const c = await montar({ ...sano, procesamiento: { ...sano.procesamiento, procesando: [clase('8A', 'Matemática', { turno: 'ahora', minutos: null })] } })
    expect(c.textContent).toContain('procesándose ahora.')
    expect(c.textContent).not.toMatch(/null|hace \d+ min/)
  })

  it('sin clases con problemas, solo se dibujan los grupos que tienen algo', async () => {
    const c = await montar({ ...sano, procesamiento: { ...sano.procesamiento, procesando: [clase('8A', 'Matemática', { turno: 'espera', minutos: null })] } })
    expect([...c.querySelectorAll('h3')].map((h) => h.textContent)).toEqual(['Procesándose'])
  })

  it('el reintento nunca dice «0 min» aunque falte menos de un minuto', async () => {
    const c = await montar({
      ...sano,
      procesamiento: { ...sano.procesamiento, con_reintento: [clase('1M', 'Física', { intentos: 1, reintento_en: '2026-10-02T15:00:10Z', error: null })] },
    })
    expect(c.textContent).toContain('reintento en unos 1 min')
  })

  it('los respaldos: ninguno todavía, de ayer, de hace días y en el mismo disco que la base', async () => {
    const con = async (r: Partial<EstadoServidor['respaldos']>) => {
      for (const x of raices.splice(0)) act(() => x.unmount())
      document.body.innerHTML = ''
      return fila(await montar({ ...sano, respaldos: { ...sano.respaldos, ...r } }), 'Respaldos')
    }
    expect(await con({ cantidad: 0, ultimo: null, hace_dias: null, mb: 0 })).toContain('Todavía no hay ninguno.')
    expect(await con({ cantidad: 1, hace_dias: 1 })).toContain('Último: ayer. 1 copia (16 MB).')
    expect(await con({ hace_dias: 5 })).toContain('Último: hace 5 días.')
    expect(await con({ en_el_mismo_disco: true })).toContain('Están en el mismo disco que la base de datos.')
  })

  it('una ruta o un error sin espacios se parte en vez de ensanchar la pantalla del teléfono', async () => {
    const largo = String.raw`C:\Users\Colegio\Documentos\ClaseAIdia\respaldos_de_la_base_de_datos\copias`
    const c = await montar({
      ...sano,
      respaldos: { ...sano.respaldos, carpeta: largo },
      procesamiento: { ...sano.procesamiento, con_error: [clase('2M', 'Química', { error: largo })] },
    })
    const ruta = [...c.querySelectorAll('li div')].find((d) => d.textContent === `Último: hoy. 5 copias (16 MB). Carpeta: ${largo}`)
    expect(ruta?.className).toContain('overflow-wrap:anywhere')
    expect([...c.querySelectorAll('span.block')].find((s) => s.textContent === largo)?.className).toContain('overflow-wrap:anywhere')
  })

  it('si el programa de IA no responde o le falta el modelo, lo dice distinto', async () => {
    const c = await montar({ ...sano, ollama: { ...sano.ollama, responde: false, modelo_texto_instalado: false } })
    expect(fila(c, 'Programa de IA')).toContain('No responde por ahora.')
    for (const x of raices.splice(0)) act(() => x.unmount())
    document.body.innerHTML = ''
    const c2 = await montar({ ...sano, ollama: { ...sano.ollama, modelo_texto_instalado: false } })
    expect(fila(c2, 'Programa de IA')).toContain('falta el modelo de resúmenes (llama3.2:1b o llama3.2:3b)')
  })

  it('la vigilancia caída se dice; si está apagada en el servidor (pruebas) la fila no aparece; sin medir la memoria no inventa números', async () => {
    const c = await montar({ ...sano, vigilancia: { ultima_pasada: null, activa: false }, memoria: { total_gb: null, libre_gb: null } })
    expect(fila(c, 'Vigilancia')).toContain('No responde.')
    expect(fila(c, 'Memoria')).toContain('No se pudo medir.')
    for (const x of raices.splice(0)) act(() => x.unmount())
    document.body.innerHTML = ''
    const c2 = await montar({ ...sano, vigilancia: { ultima_pasada: null, activa: null } })
    expect(fila(c2, 'Vigilancia')).toBe('')
  })

  it('los tamaños pasan a GB desde los 1000 MB y los MB grandes van sin decimales', async () => {
    const c = await montar({ ...sano, disco: { ...sano.disco, audio_temporal_mb: 2500, fotos_temporales_mb: 48.6, base_de_datos_mb: null } })
    expect(fila(c, 'Espacio en disco')).toContain('Audio temporal: 2,5 GB. Fotos temporales: 49 MB.')
    expect(fila(c, 'Espacio en disco')).not.toContain('Base de datos')
  })

  it('con una sola clase en cualquiera de los cuatro grupos ya no dice que no hay nada', async () => {
    const una = clase('8A', 'Matemática')
    const grupos: Partial<EstadoServidor['procesamiento']>[] = [
      { en_vivo: [{ ...una, estado: 'grabando' }] },
      { procesando: [{ ...una, turno: 'espera', minutos: null }] },
      { con_reintento: [{ ...una, intentos: 1, reintento_en: '2026-10-02T15:05:00Z', error: null }] },
      { con_error: [{ ...una, error: null }] },
    ]
    for (const g of grupos) {
      for (const x of raices.splice(0)) act(() => x.unmount())
      document.body.innerHTML = ''
      const c = await montar({ ...sano, procesamiento: { ...sano.procesamiento, ...g } })
      expect(c.textContent, JSON.stringify(Object.keys(g))).not.toContain('No hay ninguna clase')
      expect(c.querySelectorAll('h3')).toHaveLength(1)
    }
  })

  it('cada estado de una clase en vivo se dice con sus palabras, y una clase sin asignatura no deja un hueco', async () => {
    const estados = { esperando: 'esperando que empiece.', grabando: 'grabando.', pausada: 'en pausa.', terminando: 'terminando de recibir el audio.' }
    const c = await montar({
      ...sano,
      procesamiento: { ...sano.procesamiento, en_vivo: Object.keys(estados).map((estado, i) => ({ ...clase('8A', 'X', { clase_id: i, asignatura: null }), estado })) },
    })
    const lineas = [...c.querySelectorAll('h3 + ul li')].map((li) => li.textContent!)
    expect(lineas).toHaveLength(4)
    Object.values(estados).forEach((texto, i) => {
      expect(lineas[i]).toContain(texto)
      expect(lineas[i]).toContain('8A · Clase')
    })
  })

  it('recién encendido (sin primera revisión) la vigilancia figura funcionando, sin inventar hace cuánto', async () => {
    const c = await montar({ ...sano, vigilancia: { ultima_pasada: null, activa: true } })
    expect(fila(c, 'Vigilancia')).toContain('Funcionando.')
    expect(fila(c, 'Vigilancia')).not.toContain('última revisión')
  })

  it('se actualiza solo cada 10 segundos y lo nuevo reemplaza a lo viejo', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const c = await montar()
    expect(c.querySelector('h2')?.textContent).toBe('Todo en orden.')
    mock().mockResolvedValue({ ...sano, generado_en: '2026-10-02T15:00:10Z', alertas: [{ tema: 'disco', nivel: 'aviso', texto: 'Poco disco.' }] })
    await esperar(9_000)
    expect(c.querySelector('h2')?.textContent).toBe('Todo en orden.') // todavía no toca
    await esperar(1_500)
    expect(c.querySelector('h2')?.textContent).toBe('1 aviso.')
  })

  it('si se corta la conexión conserva lo último que vio y lo avisa; al volver, el aviso se va', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const c = await montar()
    mock().mockRejectedValue(new Error('sin red'))
    await esperar(10_500)
    expect(c.querySelector('[role=alert]')?.textContent).toContain('Se perdió la conexión con el servidor. Lo que ves es de las')
    expect(c.querySelector('h2')?.textContent).toBe('Todo en orden.') // no se vacía la pantalla
    mock().mockResolvedValue(sano)
    await esperar(10_500)
    expect(c.querySelector('[role=alert]')).toBeNull()
  })

  it('si el servidor no responde desde el principio lo dice en vez de quedarse cargando', async () => {
    mock().mockReset().mockRejectedValue(new Error('sin red'))
    const contenedor = document.createElement('div')
    document.body.append(contenedor)
    const raiz = createRoot(contenedor)
    raices.push(raiz)
    await act(async () => raiz.render(<Estado />))
    await esperar(30)
    expect(contenedor.querySelector('[role=alert]')?.textContent).toContain('No se pudo conectar con el servidor')
  })
})
