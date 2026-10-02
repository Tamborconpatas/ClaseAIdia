import { describe, expect, it } from 'vitest'
import { partir } from './formulas'
import { aMermaid, type Relacion } from './mapa'
import { aSegmentos, deMermaid, deSegmentos, segmentoNuevo } from './pizarra'

const BS = String.fromCharCode(92)
const tex = (s: string) => s.replaceAll('@', BS)

describe('deMermaid', () => {
  it('lee de vuelta lo que arma aMermaid, aun con textos difíciles', () => {
    const rel: Relacion[] = [
      { de: 'Idea', relacion: 'busca', a: 'Solución' },
      { de: 'Idea', relacion: '', a: "x < 3 y 'comillas'" },
      { de: "x < 3 y 'comillas'", relacion: 'vuelve a', a: 'Idea' },
    ]
    expect(deMermaid(aMermaid(rel))).toEqual(rel)
  })

  it('lee un diagrama de flechas escrito a mano', () => {
    expect(deMermaid('flowchart TD\n  A[Idea] --> B[Proyecto]\n  B -->|"evalúa"| C[Costos]\n  C --- A')).toEqual([
      { de: 'Idea', relacion: '', a: 'Proyecto' },
      { de: 'Proyecto', relacion: 'evalúa', a: 'Costos' },
      { de: 'Costos', relacion: '', a: 'Idea' },
    ])
    expect(deMermaid('graph LR\n  A -->|sí| B')).toEqual([{ de: 'A', relacion: 'sí', a: 'B' }])
  })

  it('devuelve null si hay algo que la tabla no puede mostrar', () => {
    expect(deMermaid('flowchart TD\n  subgraph uno\n  A --> B\n  end')).toBeNull()
    expect(deMermaid('flowchart TD\n  A[Idea]')).toBeNull() // solo nodos, sin flechas
    expect(deMermaid('sequenceDiagram\n  A->>B: hola')).toBeNull()
    expect(deMermaid('flowchart TD\n  A --> B\n  style A fill:#f9f')).toBeNull()
    expect(deMermaid('')).toBeNull()
  })
})

describe('aSegmentos / deSegmentos', () => {
  const ida = (texto: string) => deSegmentos(aSegmentos(texto))

  it('un texto con fórmulas vuelve igual (salvo espacios sobrantes)', () => {
    const texto = tex('Sea $x = 1$ y\n$$@frac{4620}{420} = 11$$\nfin')
    expect(ida(texto)).toBe(texto)
    expect(ida('Hw.:\nStudent Book 3A,\np. 44')).toBe('Hw.:\nStudent Book 3A,\np. 44')
  })

  it('el signo de pesos del texto no se vuelve fórmula al guardar', () => {
    const texto = 'Cuesta $5.920 y otro $1.300 más'
    expect(ida(texto)).toBe(tex('Cuesta @$5.920 y otro @$1.300 más'))
    expect(partir(ida(texto))).toEqual([{ tipo: 'texto', valor: texto }]) // y al leerlo otra vez sigue siendo texto
  })

  it('una fórmula o un diagrama agregados quedan en su propia línea', () => {
    const f = { ...segmentoNuevo.formula(), tex: tex('@sqrt{x}') }
    const t1 = { ...segmentoNuevo.texto(), valor: 'antes' }
    const t2 = { ...segmentoNuevo.texto(), valor: 'después' }
    expect(deSegmentos([t1, f, t2])).toBe(tex('antes\n$$@sqrt{x}$$\ndespués'))
    const g = { ...segmentoNuevo.diagrama(), relaciones: [{ de: 'A', relacion: 'r', a: 'B' }] }
    expect(deSegmentos([t1, g, t2])).toBe('antes\n```mermaid\n' + aMermaid(g.relaciones) + '\n```\ndespués')
    expect(deSegmentos([t1, { ...f, bloque: false }, t2])).toBe(tex('antes$@sqrt{x}$después')) // en línea no se separa
  })

  it('el salto de línea entre dos bloques no se vuelve un texto vacío que editar', () => {
    const NL = String.fromCharCode(10)
    const segmentos = aSegmentos(tex(['Hola', '$$@sqrt{x}$$', '```mermaid', 'flowchart TD', '  A --> B', '```', '$$y$$'].join(NL)))
    expect(segmentos.map((s) => s.tipo)).toEqual(['texto', 'formula', 'diagrama', 'formula'])
    expect(aSegmentos('$a$ $b$').map((s) => s.tipo)).toEqual(['formula', 'texto', 'formula']) // el espacio entre dos fórmulas en línea sí cuenta
  })

  it('lo que quedó vacío se descarta', () => {
    expect(deSegmentos([segmentoNuevo.texto(), segmentoNuevo.formula(), segmentoNuevo.diagrama()])).toBe('')
    const t = { ...segmentoNuevo.texto(), valor: 'hola' }
    const d = { ...segmentoNuevo.diagrama(), relaciones: [{ de: 'A', relacion: '', a: '' }] } // media flecha
    expect(deSegmentos([t, d])).toBe('hola')
  })

  it('un diagrama que se puede mostrar como tabla se edita como tabla, y vuelve a ser un diagrama', () => {
    const texto = 'Mapa:\n```mermaid\nflowchart TD\n  A[Idea] --> B[Proyecto]\n```'
    const segmentos = aSegmentos(texto)
    expect(segmentos.map((s) => s.tipo)).toEqual(['texto', 'diagrama'])
    const d = segmentos[1]
    if (d.tipo !== 'diagrama') throw new Error('debía ser un diagrama')
    expect(d.relaciones).toEqual([{ de: 'Idea', relacion: '', a: 'Proyecto' }])
    expect(deSegmentos(segmentos)).toContain('N1["Idea"]')
  })

  it('un diagrama que la tabla no entiende se conserva tal cual (solo se puede quitar)', () => {
    const codigo = 'flowchart TD\n  subgraph uno\n  A --> B\n  end'
    const segmentos = aSegmentos('```mermaid\n' + codigo + '\n```')
    expect(segmentos.map((s) => s.tipo)).toEqual(['codigo'])
    expect(deSegmentos(segmentos)).toBe('```mermaid\n' + codigo + '\n```')
    expect(deSegmentos([])).toBe('')
  })
})
