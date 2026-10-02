import { describe, expect, it } from 'vitest'
import { partir } from './formulas'

const f = (valor: string, bloque = false) => ({ tipo: 'formula', valor, bloque })
const t = (valor: string) => ({ tipo: 'texto', valor })

describe('partir', () => {
  it('deja el texto normal como está', () => {
    expect(partir('Hw: Student Book 3A, p. 44')).toEqual([t('Hw: Student Book 3A, p. 44')])
    expect(partir('')).toEqual([])
  })

  it('reconoce fórmulas en línea y en bloque', () => {
    expect(partir('Sea $x = 11$ el valor.')).toEqual([t('Sea '), f('x = 11'), t(' el valor.')])
    expect(partir('$$U(x) = 9920x$$')).toEqual([f('U(x) = 9920x', true)])
    expect(partir('\\[\\frac{4620}{420}\\]')).toEqual([f('\\frac{4620}{420}', true)])
    expect(partir('vale \\(x^2\\) aquí')).toEqual([t('vale '), f('x^2'), t(' aquí')])
  })

  it('un bloque puede ocupar varias líneas', () => {
    expect(partir('antes\n$$\na = b\n$$\ndespués')).toEqual([t('antes\n'), f('a = b', true), t('\ndespués')])
  })

  it('el signo de pesos no se confunde con una fórmula', () => {
    expect(partir('Cuesta $5.920 y otro $1.300 más')).toEqual([t('Cuesta $5.920 y otro $1.300 más')])
    expect(partir('Pagó \\$500 hoy')).toEqual([t('Pagó $500 hoy')])
    expect(partir('un $ suelto')).toEqual([t('un $ suelto')])
  })

  it('un $ sin cerrar queda como texto y no se pierde nada', () => {
    expect(partir('abre $x + 1 y no cierra')).toEqual([t('abre $x + 1 y no cierra')])
  })

  it('un entorno suelto (sin $) se toma como fórmula en bloque, y tabular pasa a array', () => {
    expect(partir('\\begin{aligned} a &= b \\end{aligned}')).toEqual([f('\\begin{aligned} a &= b \\end{aligned}', true)])
    expect(partir('\\begin{tabular}{c|l} 1 & 2 \\end{tabular}')).toEqual([f('\\begin{array}{c|l} 1 & 2 \\end{array}', true)])
  })

  it('quita la cerca ``` con que el modelo envuelve la respuesta, y conserva lo de adentro', () => {
    expect(partir('```latex\n$$x = 1$$\n```')).toEqual([f('x = 1', true)])
    expect(partir('```\nHola $a$\n```')).toEqual([t('Hola '), f('a')])
  })

  it('reconoce un diagrama mermaid', () => {
    expect(partir('Mapa:\n```mermaid\nflowchart TD\n  A --> B\n```\nfin')).toEqual([
      t('Mapa:\n'),
      { tipo: 'mermaid', valor: 'flowchart TD\n  A --> B' },
      t('\nfin'),
    ])
  })

  it('mezcla todo en orden', () => {
    expect(partir('1) $a$\n2) $$b$$ y \\$3')).toEqual([t('1) '), f('a'), t('\n2) '), f('b', true), t(' y $3')])
  })
})
