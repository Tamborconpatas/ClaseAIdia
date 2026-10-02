// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { aMermaid, type Relacion } from './mapa'

describe('aMermaid', () => {
  it('arma los nodos una sola vez y las flechas con su rótulo', () => {
    const codigo = aMermaid([
      { de: 'Idea', relacion: 'busca', a: 'Solución' },
      { de: 'idea', relacion: '', a: 'Proyecto' }, // el mismo concepto, escrito distinto: un solo nodo
    ])
    expect(codigo).toBe(
      ['flowchart TD', '  N1["Idea"]', '  N2["Solución"]', '  N3["Proyecto"]', '  N1 -->|"busca"| N2', '  N1 --> N3'].join('\n'),
    )
  })

  it('ignora relaciones sin origen o sin destino', () => {
    expect(aMermaid([{ de: ' ', relacion: 'x', a: 'B' }, { de: 'A', relacion: 'x', a: '' }])).toBe('flowchart TD')
  })

  it('sin relaciones no hay nada que dibujar', () => {
    expect(aMermaid([])).toBe('flowchart TD')
  })

  it('un texto no puede salirse de sus comillas ni abrir sintaxis', () => {
    const codigo = aMermaid([{ de: 'A"]\nB --> C', relacion: 'x"| D', a: '<img src=x onerror=alert(1)>' }])
    expect(codigo.split('\n').length).toBe(4) // título, 2 nodos, 1 flecha: ningún salto de línea se coló
    expect(codigo).not.toContain('<img')
    expect(codigo).not.toContain('<')
    expect(codigo).toContain("A'] B --#gt; C") // la comilla y la flecha quedaron como texto, no como sintaxis
  })

  it('quita los caracteres de control', () => {
    const codigo = aMermaid([{ de: 'A' + String.fromCharCode(1, 27, 0) + 'B', relacion: 'x', a: 'C' }])
    expect([...codigo].some((c) => c.charCodeAt(0) < 32 && c !== String.fromCharCode(10))).toBe(false)
    expect(codigo).toContain('N1["A B"]')
  })

  it('el código que arma lo acepta el analizador real de Mermaid, aun con textos difíciles', async () => {
    const mermaid = (await import('mermaid')).default
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' })
    const dificiles: Relacion[][] = [
      [{ de: 'Aprendizaje supervisado', relacion: 'usa', a: 'Etiquetas' }],
      [{ de: 'A "con comillas"', relacion: 'dice "x"', a: 'B [corchetes] (paréntesis) {llaves}' }],
      [{ de: 'end', relacion: 'graph', a: 'subgraph' }], // palabras reservadas como texto
      [{ de: 'a --> b', relacion: 'x | y', a: 'c; d' }],
      [{ de: 'Ñandú & café <b>', relacion: '>>', a: 'ü #1 %%' }],
      [{ de: '𝑥² + 1', relacion: '→', a: '😀' }],
      [{ de: 'Uno', relacion: '', a: 'Dos' }, { de: 'Dos', relacion: 'vuelve a', a: 'Uno' }], // ciclo
      Array.from({ length: 30 }, (_, i) => ({ de: `Concepto ${i}`, relacion: 'lleva a', a: `Concepto ${i + 1}` })),
    ]
    for (const rel of dificiles) {
      const codigo = aMermaid(rel)
      await expect(mermaid.parse(codigo), codigo).resolves.toBeTruthy()
    }
  })
})
