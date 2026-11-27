/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { generarPdf, textoSeguro, type OpcionesPdf } from './pdf'
import type { Bloque } from './modelo'

// Un PNG de 1×1 píxel, para no depender de un navegador que dibuje de verdad.
const PNG = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='), (c) => c.charCodeAt(0))
const opciones = (extra: OpcionesPdf = {}): OpcionesPdf => ({
  diagrama: async () => ({ datos: PNG, ancho: 400, alto: 200 }),
  formula: async () => ({ datos: PNG, ancho: 40, alto: 20, baja: 4 }),
  ...extra,
})

/** El PDF como texto binario: sirve para comprobar la cabecera y contar páginas sin leer su contenido comprimido. */
async function leer(b: Blob): Promise<string> {
  return new TextDecoder('latin1').decode(await b.arrayBuffer())
}
const paginas = (pdf: string) => (pdf.match(/\/Type\s*\/Page(?!s)/g) ?? []).length

const completo: Bloque[] = [
  { t: 'titulo', texto: 'Matemática' },
  { t: 'subtitulo', texto: '8°A · 28 sep · 08:00–08:45 · Sala 12' },
  { t: 'aviso', texto: 'Material sin revisar: se generó automáticamente y puede tener errores.' },
  { t: 'seccion', texto: 'Resumen' },
  { t: 'parrafo', trozos: [{ tipo: 'texto', valor: 'El área es ' }, { tipo: 'formula', valor: 'A=\\pi r^2', bloque: false }, { tipo: 'texto', valor: ' y se mide en metros². ¿Cómo? Así: «sin trucos».' }] },
  { t: 'vinetas', items: ['uno', 'dos → tres', 'x ≥ 2'] },
  { t: 'formula', tex: 'x=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}' },
  { t: 'diagrama', codigo: 'graph TD; A-->B', descripcion: 'Mapa' },
  { t: 'seccion', texto: 'Tarjetas de estudio', nota: 'Intenta responder antes de leer.' },
  { t: 'tarjeta', pregunta: '¿Qué es una ecuación?', respuesta: 'Una igualdad con una incógnita.' },
  { t: 'nota', texto: 'Foto a los 3 min de la clase' },
]

describe('textoSeguro', () => {
  it('cambia lo que las tipografías estándar de PDF no dibujan y deja intacto el español', () => {
    expect(textoSeguro('a → b ≥ c ≠ d ≈ e')).toBe('a -> b >= c != d ~ e')
    const espanol = '¿Qué? ¡Sí! mañana, camión, «hola» — “bien” • … ° ² ×'
    expect(textoSeguro(espanol)).toBe(espanol)
    expect(textoSeguro('ok 😀 fin')).toBe('ok  fin')
  })
})

describe('generarPdf', () => {
  it('arma un PDF de verdad con todo el modelo, una fórmula en línea y un diagrama', async () => {
    const formula = vi.fn(opciones().formula!)
    const diagrama = vi.fn(opciones().diagrama!)
    const blob = await generarPdf(completo, opciones({ formula, diagrama }))
    const pdf = await leer(blob)
    expect(blob.type).toBe('application/pdf')
    expect(pdf.startsWith('%PDF-')).toBe(true)
    expect(blob.size).toBeGreaterThan(2000)
    expect(pdf).toContain('/Title (Matem') // el título del documento
    expect(formula).toHaveBeenCalledWith('A=\\pi r^2', false) // la fórmula en línea
    expect(formula).toHaveBeenCalledWith('x=\\frac{-b\\pm\\sqrt{b^2-4ac}}{2a}', true) // la de bloque
    expect(diagrama).toHaveBeenCalledWith('graph TD; A-->B')
    expect(paginas(pdf)).toBe(1)
  })

  it('pasa a otra página cuando el texto no cabe, sin cortar nada', async () => {
    const largo: Bloque[] = [
      { t: 'titulo', texto: 'Clase larga' },
      { t: 'seccion', texto: 'Resumen' },
      ...Array.from({ length: 40 }, (_, i): Bloque => ({ t: 'parrafo', trozos: [{ tipo: 'texto', valor: `Párrafo ${i}. ` + 'palabra '.repeat(80) }] })),
    ]
    expect(paginas(await leer(await generarPdf(largo, opciones())))).toBeGreaterThan(3)
  })

  it('si una fórmula o un diagrama no se pueden convertir, deja su texto y el PDF sale igual', async () => {
    const blob = await generarPdf(completo, opciones({ formula: async () => null, diagrama: async () => Promise.reject(new Error('sin navegador')) }))
    expect((await leer(blob)).startsWith('%PDF-')).toBe(true)
  })

  it('una clase sin material (solo el encabezado) también se descarga', async () => {
    const pdf = await leer(await generarPdf(completo.slice(0, 2), opciones()))
    expect(pdf.startsWith('%PDF-')).toBe(true)
    expect(paginas(pdf)).toBe(1)
  })
})
