// @vitest-environment jsdom
import axe from 'axe-core'
import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ClaseDetalle } from '@/lib/api'

// MathLive y Mermaid dibujan con el navegador de verdad (tamaños, teclado en pantalla): aquí se reemplazan por piezas simples
// para revisar lo que es nuestro (nombres, roles, foco, avisos); lo de ellos se revisó en el navegador.
vi.mock('@/components/CampoFormula', () => ({
  CampoFormula: ({ etiqueta, valor }: { etiqueta: string; valor: string }) => <input aria-label={etiqueta} defaultValue={valor} />,
}))
vi.mock('@/lib/mermaid', () => ({ dibujarDiagrama: () => Promise.reject(new Error('sin navegador')), svgAPng: vi.fn() }))

import { DescargarClase } from '@/components/DescargarClase'
import { EditorMapa, MapaDibujado } from '@/components/MapaConceptual'
import { EditorPizarra } from '@/components/EditorPizarra'
import { FotoLeida } from '@/components/FotoLeida'
import { SelectorTema } from '@/components/SelectorTema'
import { TextoConFormulas } from '@/components/TextoConFormulas'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const raices: Root[] = []
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
})

async function montar(elemento: ReactElement) {
  const contenedor = document.createElement('div')
  document.body.append(contenedor)
  const raiz = createRoot(contenedor)
  raices.push(raiz)
  await act(async () => {
    raiz.render(elemento)
  })
  await act(async () => {
    await new Promise((r) => setTimeout(r, 150)) // fórmulas y diagramas se dibujan en segundo plano
  })
  return contenedor
}

/** Reglas de WCAG 2.0/2.1/2.2 nivel A y AA y buenas prácticas; sin las que necesitan el diseño real (contraste) o la página entera. */
async function violaciones(contenedor: HTMLElement): Promise<string[]> {
  const r = await axe.run(contenedor, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] },
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false }, 'landmark-one-main': { enabled: false }, 'page-has-heading-one': { enabled: false } },
  })
  return r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`)
}

const BS = String.fromCharCode(92)
const clase = {
  id: 1, asignatura: 'Matemática', curso_nombre: '8°A', sala: 'S1', fecha: '2026-09-28', hora_inicio: '08:00:00', hora_fin: '08:45:00', estado: 'publicada',
  contenido: { resumen: 'Resumen', puntos_clave: '- uno', hoja_repaso: 'Repaso', tarjetas: [], transcripcion_texto: '', pizarra: [], mapa: [] },
} as unknown as ClaseDetalle

describe('accesibilidad de lo nuevo', () => {
  it('texto con fórmulas, fórmula en bloque y diagrama: sin violaciones, y la fórmula en bloque es un grupo con nombre', async () => {
    const c = await montar(<TextoConFormulas texto={`Sea $x = 1$ y${'\n'}$$${BS}frac{a}{b}$$${'\n'}${'```'}mermaid${'\n'}flowchart TD${'\n'}  A[Idea] --> B[Proyecto]${'\n'}${'```'}`} />)
    expect(await violaciones(c)).toEqual([])
    const bloque = c.querySelector('[role=group][aria-label=Fórmula]')
    expect(bloque).not.toBeNull()
    expect(bloque!.getAttribute('tabindex')).toBe('0') // una fórmula ancha se desplaza con el teclado
    expect(c.textContent).toContain('Ver como lista') // el diagrama de flechas también va en texto
    expect(c.textContent).toContain('Idea')
  })

  it('el selector de tema: grupo con nombre, cada opción con su texto y su estado, y cambia la página', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))
    for (const conTexto of [false, true]) {
      const c = await montar(<SelectorTema conTexto={conTexto} />)
      expect(await violaciones(c)).toEqual([])
      expect(c.querySelector('[role=group]')?.getAttribute('aria-label')).toBe('Tema de color')
      const botones = [...c.querySelectorAll('button')]
      expect(botones.map((b) => b.textContent)).toEqual(['Sistema', 'Claro', 'Oscuro']) // con texto visible o solo para el lector de pantalla
      await act(async () => botones[2].click())
      expect(botones.map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'false', 'true'])
      expect(document.documentElement.classList.contains('dark')).toBe(true)
      await act(async () => botones[1].click())
      expect(document.documentElement.classList.contains('dark')).toBe(false)
      raices.splice(0).forEach((r) => act(() => r.unmount()))
      document.body.innerHTML = ''
    }
    vi.unstubAllGlobals()
  })

  it('el mapa conceptual: dibujo con descripción y lista de relaciones, sin violaciones', async () => {
    const c = await montar(<MapaDibujado relaciones={[{ de: 'Idea', relacion: 'busca', a: 'Solución' }]} />)
    expect(await violaciones(c)).toEqual([])
    expect(c.querySelectorAll('li')).toHaveLength(1)
  })

  it('el editor del mapa: cada campo tiene su nombre', async () => {
    const c = await montar(<EditorMapa claseId={1} inicial={[{ de: 'A', relacion: 'r', a: 'B' }]} onGuardado={() => {}} onCancelar={() => {}} />)
    expect(await violaciones(c)).toEqual([])
    expect(c.querySelector('input[aria-label="Concepto de origen de la relación 1"]')).not.toBeNull()
  })

  it('descargar: botones con texto, aviso para lector de pantalla, y la nota sobre las fórmulas solo para el profesor', async () => {
    for (const esProfesor of [false, true]) {
      const c = await montar(<DescargarClase clase={clase} esProfesor={esProfesor} />)
      expect(await violaciones(c)).toEqual([])
      expect(c.querySelector('[role=status][aria-live=polite]')).not.toBeNull()
      expect(/Sobre las fórmulas en el Word/.test(c.textContent ?? '')).toBe(esProfesor)
      raices.splice(0).forEach((r) => act(() => r.unmount()))
      document.body.innerHTML = ''
    }
  })

  it('lo leído de una foto, con las acciones del profesor, sin violaciones', async () => {
    const c = await montar(<ul><FotoLeida claseId={1} foto={{ id: 1, segundo: 600, texto: 'Hola' }} editable onCambio={() => {}} /></ul>)
    expect(await violaciones(c)).toEqual([])
  })

  it('el editor de la foto: cada parte es un grupo con nombre y posición, sin violaciones', async () => {
    const texto = `Hola${'\n'}$$${BS}sqrt{x}$$${'\n'}${'```'}mermaid${'\n'}flowchart TD${'\n'}  A[Idea] --> B[Proyecto]${'\n'}${'```'}`
    const c = await montar(<EditorPizarra texto={texto} onCambio={() => {}} />)
    expect(await violaciones(c)).toEqual([])
    const grupos = [...c.querySelectorAll('[data-segmento]')].map((g) => g.getAttribute('aria-label'))
    expect(grupos).toEqual(['Parte 1 de 3: Texto', 'Parte 2 de 3: Fórmula', 'Parte 3 de 3: Diagrama'])
  })

  it('el foco acompaña a quien edita: tras agregar va a la parte nueva, tras mover se queda en el botón, tras quitar va a «Agregar texto»', async () => {
    const c = await montar(<EditorPizarra texto={`Uno${'\n'}$$x$$${'\n'}Dos`} onCambio={() => {}} />)
    const clic = async (e: Element | null | undefined) => act(async () => (e as HTMLElement).click())
    const botones = (i: number) => c.querySelectorAll('[data-segmento]')[i].querySelectorAll<HTMLButtonElement>('[data-mover]')

    await clic([...c.querySelectorAll('button')].find((b) => b.textContent?.includes('Agregar texto')))
    expect(document.activeElement?.tagName).toBe('TEXTAREA') // el texto nuevo
    expect(document.activeElement?.closest('[data-segmento]')?.getAttribute('aria-label')).toBe('Parte 4 de 4: Texto')

    const bajar = botones(0)[1]
    bajar.focus()
    await clic(bajar)
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Bajar esta parte') // sigue donde estaba
    expect(c.querySelector('[role=status]')?.textContent).toContain('Parte movida')

    // Al llegar al final, «Bajar» se desactiva: el foco no se pierde, pasa a «Subir» de la misma parte.
    const penultimo = botones(2)[1]
    penultimo.focus()
    await clic(penultimo)
    expect(document.activeElement?.getAttribute('aria-label')).toBe('Subir esta parte')
    expect(document.activeElement).not.toBe(document.body)

    await clic(c.querySelectorAll('[data-segmento]')[3].querySelector('button[aria-label="Quitar esta parte"]'))
    expect(document.activeElement?.tagName).toBe('BUTTON') // y no el cuerpo de la página, cuyo texto también incluye ese botón
    expect(document.activeElement?.textContent?.trim()).toBe('Agregar texto')
    expect(c.querySelector('[role=status]')?.textContent).toBe('Parte quitada.')
    expect(await violaciones(c)).toEqual([])
  })
})
