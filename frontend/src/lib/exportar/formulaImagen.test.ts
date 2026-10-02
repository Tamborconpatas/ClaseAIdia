// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { formulaASvg } from './formulaImagen'

const BS = String.fromCharCode(92)
const tex = (s: string) => s.replaceAll('@', BS)

describe('formulaASvg', () => {
  it('dibuja una fórmula como SVG con tamaño propio, sin depender de tipografías ni del color del texto', async () => {
    const f = (await formulaASvg(tex('x = @frac{4620}{420}'), false))!
    expect(f.svg.startsWith('<svg')).toBe(true)
    expect(f.svg).toContain('xmlns="http://www.w3.org/2000/svg"')
    expect(f.svg).not.toContain('currentColor') // sobre un PNG el color tiene que ser negro de verdad
    expect(f.svg).not.toContain('<text') // trazados, no texto: no hace falta ninguna fuente
    expect(f.anchoEx).toBeGreaterThan(3)
    expect(f.altoEx).toBeGreaterThan(1)
  })

  it('una fracción es más alta que una letra, y se alinea con la línea de base del texto', async () => {
    const letra = (await formulaASvg('x', false))!
    const fraccion = (await formulaASvg(tex('@frac{a}{b}'), false))!
    expect(fraccion.altoEx).toBeGreaterThan(letra.altoEx)
    expect(fraccion.bajaEx).toBeGreaterThan(0) // el denominador cuelga por debajo de la línea de base
    expect(letra.bajaEx).toBeLessThan(0.1) // una letra casi no cuelga
  })

  it('acepta entornos como array y aligned', async () => {
    expect(await formulaASvg(tex('@begin{array}{c|l} X & Y @@ 3 & 4 @end{array}'), true)).not.toBeNull()
    expect(await formulaASvg(tex('@begin{aligned} a &= b @@ c &= d @end{aligned}'), true)).not.toBeNull()
  })

  it('devuelve null con un LaTeX roto o con un comando que no existe (el Word deja entonces su texto)', async () => {
    expect(await formulaASvg(tex('@frac{1}{'), false)).toBeNull()
    expect(await formulaASvg(tex('@comandoquenoexiste{x}'), false)).toBeNull()
  })
})
