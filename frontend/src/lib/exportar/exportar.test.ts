/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import JSZip from 'jszip'
import { describe, expect, it } from 'vitest'
import type { ClaseDetalle } from '@/lib/api'
import { aOmml, generarDocx, type OpcionesDocx } from './docx'
import { construirModelo, nombreDeArchivo, type Bloque } from './modelo'

const BS = String.fromCharCode(92) // una barra invertida, para escribir LaTeX sin dobles escapes
const tex = (s: string) => s.replaceAll('@', BS)

function clase(extra: Partial<NonNullable<ClaseDetalle['contenido']>> = {}, cambios: Partial<ClaseDetalle> = {}): ClaseDetalle {
  return {
    id: 1, bloque_id: 1, asignatura: 'Matemática', curso_nombre: '8°A', sala: 'S1', fecha: '2026-09-28', hora_inicio: '08:00:00', hora_fin: '08:45:00',
    estado: 'publicada', revision_vence: null, prioritaria: false, profesor_nombre: null,
    contenido: { resumen: 'Primer párrafo.\n\nSegundo párrafo.', puntos_clave: '- uno\n- dos', hoja_repaso: 'Repaso', tarjetas: [{ pregunta: '¿P?', respuesta: 'R' }], transcripcion_texto: 'TRANSCRIPCIÓN LARGA', pizarra: [], mapa: [], ...extra },
    ...cambios,
  } as unknown as ClaseDetalle
}

const tipos = (bs: Bloque[]) => bs.map((b) => b.t)

describe('construirModelo', () => {
  it('lleva el material en orden, sin la transcripción', () => {
    const m = construirModelo(clase())
    expect(tipos(m)).toEqual(['titulo', 'subtitulo', 'seccion', 'parrafo', 'parrafo', 'seccion', 'vinetas', 'seccion', 'parrafo', 'seccion', 'tarjeta'])
    expect(JSON.stringify(m)).not.toContain('TRANSCRIPCIÓN')
    expect(m.filter((b) => b.t === 'vinetas')[0]).toEqual({ t: 'vinetas', items: ['uno', 'dos'] })
  })

  it('omite lo que no hay y avisa si el material no se revisó', () => {
    const m = construirModelo(clase({ resumen: '  ', puntos_clave: null, hoja_repaso: null, tarjetas: [] }, { estado: 'provisoria' }))
    expect(tipos(m)).toEqual(['titulo', 'subtitulo', 'aviso'])
    expect(construirModelo(clase({}, { contenido: null }))).toHaveLength(2) // aún sin material: solo el encabezado
  })

  it('el mapa va como diagrama más su lista de relaciones, y la pizarra separa fórmulas, diagramas y texto', () => {
    const m = construirModelo(
      clase({
        mapa: [{ de: 'Idea', relacion: 'busca', a: 'Solución' }],
        pizarra: [{ id: 1, segundo: 125, texto: tex('Sea $x=1$ y\n$$@frac{a}{b}$$\n```mermaid\nflowchart TD\n A-->B\n```') }],
      }),
    )
    const seccion = (nombre: string) => m.findIndex((b) => b.t === 'seccion' && b.texto === nombre)
    expect(m[seccion('Mapa conceptual') + 1]).toMatchObject({ t: 'diagrama' })
    expect(m[seccion('Mapa conceptual') + 2]).toEqual({ t: 'vinetas', items: ['Idea — busca → Solución'] })
    const pizarra = m.slice(seccion('De la pizarra') + 1)
    expect(tipos(pizarra)).toEqual(['nota', 'parrafo', 'formula', 'diagrama'])
    expect(pizarra[0]).toEqual({ t: 'nota', texto: 'Foto a los 2 min de la clase' })
    expect(pizarra[2]).toEqual({ t: 'formula', tex: tex('@frac{a}{b}') })
  })

  it('el nombre del archivo no lleva caracteres prohibidos', () => {
    expect(nombreDeArchivo(clase({}, { asignatura: 'Lenguaje: "texto" <1>/2' }), 'pdf')).toBe('Lenguaje texto 12 2026-09-28.pdf')
    expect(nombreDeArchivo(clase({}, { asignatura: null }), 'docx')).toBe('Clase 2026-09-28.docx')
  })
})

describe('aOmml', () => {
  it('convierte LaTeX en una ecuación de Word', async () => {
    const o = (await aOmml(tex('x = @frac{4620}{420}')))!
    expect(o).toContain('<m:oMath')
    expect(o).toContain('<m:f>') // fracción
    expect(o).not.toContain('annotation')
  })
  it('no ensucia la consola: el conversor se quejaba del <annotation> con el LaTeX original que deja KaTeX', async () => {
    const avisos: unknown[] = []
    const original = console.warn
    console.warn = (...a: unknown[]) => void avisos.push(a)
    try {
      await aOmml(tex('x^2'))
    } finally {
      console.warn = original
    }
    expect(avisos).toEqual([])
  })
  it('devuelve null con un LaTeX que no se entiende', async () => {
    expect(await aOmml(tex('@frac{1}{'))).toBeNull()
    expect(await aOmml(tex('@comandoquenoexiste{x}'))).toBeNull()
  })
})

const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='), (c) => c.charCodeAt(0))

async function documentoXml(bloques: Bloque[], opciones: OpcionesDocx = {}) {
  const blob = await generarDocx(bloques, {
    diagrama: async () => ({ datos: png, ancho: 200, alto: 100 }),
    formula: async (_tex, bloque) => ({ datos: png, ancho: 40, alto: 20, baja: bloque ? 0 : 3 }), // en Node no hay dónde dibujar la fórmula
    ...opciones,
  })
  const zip = await JSZip.loadAsync(await blob.arrayBuffer())
  return { xml: await zip.file('word/document.xml')!.async('string'), archivos: Object.keys(zip.files) }
}

describe('generarDocx', () => {
  const conFormulas = () => construirModelo(clase({ pizarra: [{ id: 1, segundo: 60, texto: tex('Sea $x^2$ y $$@sqrt{a+b}$$') }] }))

  it('arma un Word con títulos, viñetas, tarjetas y, si se pide, las fórmulas como ecuaciones editables', async () => {
    const { xml } = await documentoXml(conFormulas(), { formulas: 'ecuacion' })
    expect(xml).toContain('Matemática')
    expect(xml).toContain('Primer párrafo.')
    expect(xml).toContain('Pregunta: ')
    expect(xml).toContain('<m:oMathPara') // la fórmula en bloque
    expect(xml).toContain('<m:rad>') // la raíz es una ecuación de Word, no una imagen
    expect(xml).toContain('<m:sSup>') // la fórmula en línea, dentro del párrafo
    expect(xml).toContain('w:numId') // las viñetas
  })

  it('por defecto las fórmulas van como imagen: se ven en cualquier programa y no dependen de las ecuaciones de Word', async () => {
    const { xml, archivos } = await documentoXml(conFormulas())
    expect(xml).not.toContain('<m:oMath')
    expect((xml.match(/<w:drawing>/g) ?? []).length).toBe(2) // una en línea y una en bloque
    expect(xml).toContain('<w:position w:val="-5"/>') // la fórmula en línea baja hasta la línea de base del texto (3 px = 2,25 pt = 4,5 → 5 medios puntos)
    expect(xml).not.toMatch(/<w:r>(?:(?!<\/w:r>).)*<w:r>/s) // una corrida dentro de otra corrida es XML inválido para Word
    expect(archivos.filter((a) => a.startsWith('word/media/')).length).toBeGreaterThan(0)
  })

  it('si una fórmula no se puede dibujar como imagen queda su LaTeX en el texto', async () => {
    const { xml } = await documentoXml(conFormulas(), { formula: async () => null })
    expect(xml).not.toContain('<w:drawing>')
    expect(xml).toContain('x^2')
    expect(xml).toContain('Consolas')
  })

  it('un diagrama va como imagen dentro del documento', async () => {
    const { xml, archivos } = await documentoXml([{ t: 'diagrama', codigo: 'flowchart TD\n A-->B', descripcion: 'Mapa' }])
    expect(xml).toContain('<w:drawing>')
    expect(archivos.some((a) => a.startsWith('word/media/'))).toBe(true)
  })

  it('si una fórmula no se puede convertir queda su LaTeX; si un diagrama no se puede dibujar, su código', async () => {
    const blob = await generarDocx(
      [{ t: 'formula', tex: tex('@frac{1}{') }, { t: 'diagrama', codigo: 'flowchart TD\n  A --> B', descripcion: 'x' }, { t: 'parrafo', trozos: [{ tipo: 'formula', valor: tex('@roto{'), bloque: false }] }],
      { diagrama: async () => { throw new Error('no se pudo') } },
    )
    const xml = await (await JSZip.loadAsync(await blob.arrayBuffer())).file('word/document.xml')!.async('string')
    expect(xml).toContain(tex('@frac{1}{'))
    expect(xml).toContain('flowchart TD')
    expect(xml).toContain('No se pudo dibujar este diagrama')
    expect(xml).toContain('Consolas')
    expect(xml).not.toContain('<w:drawing>')
  })

  it('conserva los saltos de línea de un párrafo', async () => {
    const { xml } = await documentoXml([{ t: 'parrafo', trozos: [{ tipo: 'texto', valor: 'a\nb' }] }])
    expect(xml).toMatch(/a<\/w:t>.*<w:br\/>.*b/s)
  })
})
