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
import type { AlumnoDeCurso, CierreEstado, CierreVistaPrevia, Curso } from '@/lib/api'

vi.mock('@/lib/api', async (original) => ({ ...(await original<typeof import('@/lib/api')>()), api: vi.fn() }))

import { api } from '@/lib/api'
import { CerrarElAnio, PrepararAnioNuevo, sugerido } from '@/components/CierreDeAnio'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const curso = (id: number, nombre: string): Curso => ({ id, nombre, colegio_id: 1, cupo: 45 })
const cursos: Curso[] = [curso(1, '7°A'), curso(2, '8°A'), curso(3, '4°M'), curso(4, '1°B')] // 1°B no tiene alumnos: no entra
const al = (id: number, nombre: string): AlumnoDeCurso => ({ id, nombre, rut: `2100000${id}-1`, revisar_nombre: false })
const alumnos: Record<number, AlumnoDeCurso[]> = { 1: [al(11, 'Sofía'), al(12, 'Tomás')], 2: [al(21, 'Valentina'), al(22, 'Matías')], 3: [al(31, 'Diego')], 4: [] }
const resumen = { pasan: 3, repiten: 1, se_van: 0, egresan: 1, cuentas_a_borrar: 1, cursos_nuevos: ['9°A'], codigos_nuevos: 5 }
let problemas: string[]
let estado: CierreEstado
let raices: Root[] = []
const llamadas = () => (api as unknown as ReturnType<typeof vi.fn>).mock.calls as [string, { metodo?: string; cuerpo?: Record<string, unknown> }?][]
const post = (ruta: string) => llamadas().filter((c) => c[0] === ruta).map((c) => c[1]?.cuerpo)

beforeEach(() => {
  problemas = []
  estado = { anio_cerrado: false, clases_a_borrar: 20, problemas: [] }
  ;(api as unknown as ReturnType<typeof vi.fn>).mockReset().mockImplementation(async (ruta: string) => {
    const m = /^\/cursos\/(\d+)\/alumnos$/.exec(ruta)
    if (m) return alumnos[Number(m[1])]
    if (ruta === '/cierre-anio/estado') return estado
    if (ruta === '/cierre-anio/cerrar') return { clases_borradas: 20, respaldo: 'cierre-de-anio-2026-12-15-1200.db' }
    if (ruta === '/cierre-anio/anio-nuevo/vista-previa') {
      const r: CierreVistaPrevia = { problemas, resumen, cursos: cursos.map((c) => ({ curso_id: c.id, curso: c.nombre, alumnos: alumnos[c.id].length, destino: c.id === 3 ? 'Egresan' : '9°A' })) }
      return r
    }
    return { resumen, respaldo: 'cierre-de-anio-2027-02-20-0900.db', codigos: [{ curso: '7°A', codigo: 'AAA111' }, { curso: '9°A', codigo: 'BBB222' }] }
  })
})
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
})

const esperar = () => act(async () => void (await new Promise((r) => setTimeout(r, 30))))
async function montar(el: React.ReactElement) {
  const c = document.createElement('div')
  document.body.append(c)
  const raiz = createRoot(c)
  raices.push(raiz)
  await act(async () => raiz.render(el))
  await esperar()
  return c
}
const boton = (c: HTMLElement, texto: string) => [...c.querySelectorAll('button')].find((b) => b.textContent?.includes(texto)) as HTMLButtonElement
const pulsar = async (b: HTMLElement) => {
  await act(async () => b.click())
  await esperar()
}
const elegir = async (c: HTMLElement, id: string, valor: string) => {
  const s = c.querySelector(`#${id}`) as HTMLSelectElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(s, valor)
    s.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
async function escribir(c: HTMLElement, id: string, valor: string) {
  const el = c.querySelector(`#${id}`) as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, valor)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
const marcar = async (c: HTMLElement, alumnoId: number, etiqueta: string) => {
  const f = [...c.querySelectorAll(`input[name=suerte-${alumnoId}]`)].map((i) => i.closest('label') as HTMLLabelElement).find((l) => l.textContent === etiqueta)!
  await act(async () => (f.querySelector('input') as HTMLInputElement).click())
}
async function violaciones(c: HTMLElement) {
  const r = await axe.run(c, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] }, rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}
const anio = (salir = vi.fn(), terminado = vi.fn()) => <PrepararAnioNuevo cursos={cursos} onSalir={salir} onTerminado={terminado} />

describe('Primer tiempo: cerrar el año al terminar las clases (los alumnos siguen donde están)', () => {
  it('dice cuántas clases se borran, no pregunta nada de los alumnos y no cierra sin confirmar', async () => {
    const c = await montar(<CerrarElAnio onSalir={vi.fn()} onTerminado={vi.fn()} />)
    expect(c.textContent).toContain('Se borrará el material de 20 clases')
    expect(c.textContent).toContain('Los alumnos siguen en su curso')
    expect(c.querySelectorAll('select').length).toBe(0) // nada de a dónde pasa cada curso: eso es en febrero
    expect(boton(c, 'Cerrar el año escolar').disabled).toBe(true)
    expect(await violaciones(c)).toEqual([])
    await pulsar(c.querySelector('input[type=checkbox]') as HTMLElement)
    await pulsar(boton(c, 'Cerrar el año escolar'))
    expect(post('/cierre-anio/cerrar')).toEqual([{ confirmo: true }])
    expect(c.textContent).toContain('Se borró el material de 20 clases del año')
    expect(c.textContent).toContain('«Cursos» → «Preparar el año nuevo»')
    expect(c.textContent).toContain('cierre-de-anio-2026-12-15-1200.db')
    expect(await violaciones(c)).toEqual([])
  })

  it('si algo lo impide, lo muestra y no deja cerrar', async () => {
    estado = { anio_cerrado: false, clases_a_borrar: 20, problemas: ['Hay 1 clase grabándose o procesándose: espera a que terminen para cerrar el año.'] }
    const c = await montar(<CerrarElAnio onSalir={vi.fn()} onTerminado={vi.fn()} />)
    expect(c.querySelector('[role=alert]')?.textContent).toContain('espera a que terminen')
    await pulsar(c.querySelector('input[type=checkbox]') as HTMLElement)
    expect(boton(c, 'Cerrar el año escolar').disabled).toBe(true)
  })
})

describe('Segundo tiempo: preparar el año nuevo (febrero): el UTP decide a dónde pasa cada curso y quién no pasa', () => {
  it('lista solo los cursos con alumnos, sugiere un destino y no deja seguir sin decidir', async () => {
    const c = await montar(anio())
    expect(c.querySelectorAll('select').length).toBe(3) // 1°B no tiene alumnos
    expect((c.querySelector('#destino-1') as HTMLSelectElement).value).toBe('curso:2') // 7°A → 8°A, que existe
    expect((c.querySelector('#destino-2') as HTMLSelectElement).value).toBe('nuevo') // 9°A no existe: se propone crearlo
    expect((c.querySelector('#nuevo-2') as HTMLInputElement).value).toBe('9°A')
    expect((c.querySelector('#destino-3') as HTMLSelectElement).value).toBe('egresa') // 4.° medio: el último curso
    expect(boton(c, 'Continuar').disabled).toBe(false)
    await escribir(c, 'nuevo-2', '   ') // un curso nuevo sin nombre no sirve
    expect(boton(c, 'Continuar').disabled).toBe(true)
    await elegir(c, 'destino-2', '')
    expect(c.textContent).toContain('Falta elegir el destino de todos los cursos.')
    expect(await violaciones(c)).toEqual([])
  })

  it('recorre los tres pasos, manda el plan completo, reactiva y entrega los códigos nuevos', async () => {
    const c = await montar(anio())
    await escribir(c, 'nuevo-2', ' 9°A ')
    await pulsar(boton(c, 'Continuar'))
    expect(c.textContent).toContain('¿Quién no pasa con su curso?')
    await marcar(c, 22, 'Repite')
    await marcar(c, 12, 'Se fue del colegio')
    expect(await violaciones(c)).toEqual([])
    await pulsar(boton(c, 'Revisar y confirmar'))
    const plan = { cursos: [{ curso_id: 3, egresa: true }, { curso_id: 1, destino_id: 2 }, { curso_id: 2, destino_nuevo: '9°A' }], repiten: [22], se_van: [12] }
    expect(post('/cierre-anio/anio-nuevo/vista-previa')).toEqual([plan])
    expect(c.textContent).toContain('Revisa antes de empezar el año nuevo')
    expect(c.textContent).toContain('Se borran 1 cuenta')
    expect(c.textContent).toContain('las grabaciones se activan de nuevo')
    const empezar = boton(c, 'Empezar el año nuevo')
    expect(empezar.disabled).toBe(true) // sin marcar «Entiendo…» no se puede
    expect(post('/cierre-anio/anio-nuevo')).toEqual([])
    expect(await violaciones(c)).toEqual([])
    await pulsar(c.querySelector('input[type=checkbox]') as HTMLElement)
    await pulsar(empezar)
    expect(post('/cierre-anio/anio-nuevo')).toEqual([{ ...plan, confirmo: true }])
    expect(c.textContent).toContain('Año nuevo listo')
    expect(c.textContent).toContain('Las grabaciones están activadas de nuevo')
    expect([...c.querySelectorAll('code')].map((x) => x.textContent)).toEqual(['AAA111', 'BBB222']) // los códigos nuevos, a la vista
    expect(await violaciones(c)).toEqual([])
  })

  it('si el servidor dice que hay problemas, los muestra y no deja continuar', async () => {
    problemas = ['El curso 8°A quedaría con 50 alumnos y su máximo es 45.']
    const c = await montar(anio())
    await pulsar(boton(c, 'Continuar'))
    await pulsar(boton(c, 'Revisar y confirmar'))
    expect(c.querySelector('[role=alert]')?.textContent).toContain('quedaría con 50 alumnos')
    await pulsar(c.querySelector('input[type=checkbox]') as HTMLElement)
    expect(boton(c, 'Empezar el año nuevo').disabled).toBe(true)
    expect(post('/cierre-anio/anio-nuevo')).toEqual([])
  })

  it('se puede volver atrás sin perder lo elegido y salir sin cambiar nada', async () => {
    const salir = vi.fn()
    const c = await montar(anio(salir))
    await elegir(c, 'destino-2', 'egresa')
    await pulsar(boton(c, 'Continuar'))
    await marcar(c, 21, 'Repite')
    await pulsar(boton(c, 'Atrás'))
    expect((c.querySelector('#destino-2') as HTMLSelectElement).value).toBe('egresa')
    await pulsar(boton(c, 'Cursos'))
    expect(salir).toHaveBeenCalledOnce()
    expect(post('/cierre-anio/anio-nuevo')).toEqual([])
    expect(post('/cierre-anio/anio-nuevo/vista-previa')).toEqual([])
  })
})

describe('un colegio sin alumnos igual puede reactivar las grabaciones', () => {
  it('Continuar lleva directo a la revisión y, al confirmar, empieza el año nuevo', async () => {
    const vacios = cursos.map((c) => ({ ...c }))
    ;(api as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (ruta: string) => {
      if (/^\/cursos\/\d+\/alumnos$/.test(ruta)) return []
      if (ruta === '/cierre-anio/anio-nuevo/vista-previa') return { problemas: [], resumen: { pasan: 0, repiten: 0, se_van: 0, egresan: 0, cuentas_a_borrar: 0, cursos_nuevos: [], codigos_nuevos: 4 }, cursos: [] }
      return { resumen: { pasan: 0, repiten: 0, se_van: 0, egresan: 0, cuentas_a_borrar: 0, cursos_nuevos: [], codigos_nuevos: 4 }, respaldo: null, codigos: [{ curso: '7°A', codigo: 'AAA111' }] }
    })
    const c = await montar(<PrepararAnioNuevo cursos={vacios} onSalir={vi.fn()} onTerminado={vi.fn()} />)
    expect(c.textContent).toContain('Ningún curso tiene alumnos todavía')
    expect(boton(c, 'Continuar').disabled).toBe(false)
    await pulsar(boton(c, 'Continuar'))
    expect(c.textContent).toContain('Revisa antes de empezar el año nuevo')
    await pulsar(boton(c, 'Atrás')) // desde la revisión se vuelve al paso 1: el 2 no tiene nada que mostrar
    expect(c.textContent).toContain('¿A dónde pasa cada curso?')
    await pulsar(boton(c, 'Continuar'))
    await pulsar(c.querySelector('input[type=checkbox]') as HTMLElement)
    await pulsar(boton(c, 'Empezar el año nuevo'))
    expect(c.textContent).toContain('Año nuevo listo')
  })
})

describe('la sugerencia de a dónde pasa un curso (solo un punto de partida)', () => {
  const todos = [curso(1, '7°A'), curso(2, '8°A'), curso(3, '4°M'), curso(4, '4° Medio B'), curso(5, 'IV Medio C'), curso(6, '4°A'), curso(7, 'Taller')]
  it.each([
    ['7°A', { tipo: 'curso', destinoId: 2 }],
    ['8°A', { tipo: 'nuevo', nombre: '9°A' }],
    ['4°M', { tipo: 'egresa' }],
    ['4° Medio B', { tipo: 'egresa' }],
    ['IV Medio C', { tipo: 'egresa' }],
    ['4°A', { tipo: 'nuevo', nombre: '5°A' }], // 4.° básico: pasa a 5.°
    ['Taller', { tipo: '' }],
  ])('%s', (nombre, esperado) => {
    expect(sugerido(todos.find((c) => c.nombre === nombre)!, todos)).toEqual(esperado)
  })
})
