import type { Trozo } from '@/lib/formulas'
import { dibujarDiagrama, svgAPng } from '@/lib/mermaid'
import type { Bloque } from './modelo'

/**
 * Word: las fórmulas van como **ecuaciones de Word** (editables), no como imágenes: KaTeX las pasa a MathML y
 * `mathml2omml` a OMML, el formato de ecuaciones de Word. Los diagramas Mermaid, que Word no sabe dibujar, van como imagen.
 * Todo se arma en el navegador de quien descarga: el servidor no hace nada. Si una fórmula o un diagrama no se pueden
 * convertir, se deja su texto (el LaTeX o el código) para que el documento nunca salga con huecos.
 */
export interface Imagen {
  datos: Uint8Array
  ancho: number
  alto: number
}
export interface OpcionesDocx {
  /** Cómo se convierte un diagrama en imagen (los tests lo reemplazan: en Node no hay dónde dibujarlo). */
  diagrama?: (codigo: string) => Promise<Imagen>
}

const diagramaEnImagen = async (codigo: string): Promise<Imagen> => svgAPng(await dibujarDiagrama(codigo))

/** LaTeX → OMML (el `<m:oMath>` de Word), o null si no se puede. */
export async function aOmml(tex: string): Promise<string | null> {
  const [{ default: katex }, { mml2omml }] = await Promise.all([import('katex'), import('mathml2omml')])
  try {
    const html = katex.renderToString(tex, { output: 'mathml', throwOnError: true, trust: false, strict: 'ignore', maxSize: 30, maxExpand: 1000 })
    const mathml = html.match(/<math[\s\S]*<\/math>/)?.[0]
    if (!mathml) return null
    // KaTeX deja el LaTeX original en <annotation>: Word no lo necesita y el conversor se queja de él.
    return mml2omml(mathml.replace(/<annotation[\s\S]*?<\/annotation>/g, ''))
  } catch {
    return null
  }
}

const MONO = 'Consolas'

export async function generarDocx(bloques: Bloque[], opciones: OpcionesDocx = {}): Promise<Blob> {
  const d = await import('docx')
  const aImagen = opciones.diagrama ?? diagramaEnImagen

  /** Una línea o varias de texto (los saltos de línea del original se conservan). */
  const lineas = (texto: string) => texto.split('\n').map((l, i) => new d.TextRun({ text: l, break: i > 0 ? 1 : 0 }))

  const enOmml = (omml: string) => d.ImportedXmlComponent.fromXmlString(omml) as unknown as InstanceType<typeof d.TextRun>

  async function hijosDeParrafo(trozos: Trozo[]) {
    const hijos: InstanceType<typeof d.TextRun>[] = []
    for (const t of trozos) {
      if (t.tipo === 'texto') hijos.push(...lineas(t.valor))
      else if (t.tipo === 'formula') {
        const omml = await aOmml(t.valor)
        hijos.push(omml ? enOmml(omml) : new d.TextRun({ text: t.valor, font: MONO }))
      }
    }
    return hijos
  }

  const hijos: InstanceType<typeof d.Paragraph>[] = []
  for (const b of bloques) {
    switch (b.t) {
      case 'titulo':
        hijos.push(new d.Paragraph({ heading: d.HeadingLevel.TITLE, children: [new d.TextRun(b.texto)] }))
        break
      case 'subtitulo':
        hijos.push(new d.Paragraph({ spacing: { after: 200 }, children: [new d.TextRun({ text: b.texto, color: '666666' })] }))
        break
      case 'aviso':
        hijos.push(new d.Paragraph({ spacing: { before: 120, after: 200 }, shading: { type: d.ShadingType.CLEAR, fill: 'FDF3D7' }, children: [new d.TextRun({ text: b.texto, bold: true })] }))
        break
      case 'seccion':
        hijos.push(new d.Paragraph({ heading: d.HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 280, after: 80 }, children: [new d.TextRun(b.texto)] }))
        if (b.nota) hijos.push(new d.Paragraph({ keepNext: true, spacing: { after: 100 }, children: [new d.TextRun({ text: b.nota, italics: true, color: '666666', size: 18 })] }))
        break
      case 'nota':
        hijos.push(new d.Paragraph({ keepNext: true, spacing: { before: 120 }, children: [new d.TextRun({ text: b.texto, italics: true, color: '666666', size: 18 })] }))
        break
      case 'parrafo':
        hijos.push(new d.Paragraph({ spacing: { after: 120 }, children: await hijosDeParrafo(b.trozos) }))
        break
      case 'vinetas':
        for (const item of b.items) hijos.push(new d.Paragraph({ bullet: { level: 0 }, children: [new d.TextRun(item)] }))
        break
      case 'formula': {
        const omml = await aOmml(b.tex)
        const contenido = omml
          ? enOmml(`<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">${omml}</m:oMathPara>`)
          : new d.TextRun({ text: b.tex, font: MONO })
        hijos.push(new d.Paragraph({ alignment: d.AlignmentType.CENTER, spacing: { before: 80, after: 80 }, children: [contenido] }))
        break
      }
      case 'diagrama':
        try {
          const img = await aImagen(b.codigo)
          hijos.push(
            new d.Paragraph({
              alignment: d.AlignmentType.CENTER,
              spacing: { before: 80, after: 80 },
              children: [new d.ImageRun({ type: 'png', data: img.datos, transformation: { width: img.ancho, height: img.alto }, altText: { name: 'Diagrama', title: 'Diagrama', description: b.descripcion } }) as unknown as InstanceType<typeof d.TextRun>],
            }),
          )
        } catch {
          hijos.push(new d.Paragraph({ children: [new d.TextRun({ text: 'No se pudo dibujar este diagrama; este es su código:', italics: true, color: '666666', size: 18 })] }))
          for (const l of b.codigo.split('\n')) hijos.push(new d.Paragraph({ children: [new d.TextRun({ text: l, font: MONO, size: 18 })] }))
        }
        break
      case 'tarjeta':
        hijos.push(
          new d.Paragraph({ keepNext: true, spacing: { before: 100 }, children: [new d.TextRun({ text: 'Pregunta: ', bold: true }), new d.TextRun(b.pregunta)] }),
          new d.Paragraph({ indent: { left: 360 }, spacing: { after: 80 }, children: [new d.TextRun({ text: 'Respuesta: ', bold: true }), new d.TextRun(b.respuesta)] }),
        )
        break
    }
  }

  const titulo = bloques.find((b) => b.t === 'titulo')
  const doc = new d.Document({
    creator: 'ClaseAIdia',
    title: titulo && titulo.t === 'titulo' ? titulo.texto : 'Clase',
    styles: { default: { document: { run: { font: 'Calibri', size: 22 } } } },
    sections: [{ children: hijos }],
  })
  return d.Packer.toBlob(doc)
}
