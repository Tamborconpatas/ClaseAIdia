/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { formulaEnImagen, type FormulaPng } from './formulaImagen'
import type { Trozo } from '@/lib/formulas'
import { dibujarDiagrama, svgAPng } from '@/lib/mermaid'
import type { Bloque } from './modelo'

/**
 * Word. Las fórmulas pueden ir de dos maneras:
 * - **como imagen** (por defecto): se ven en cualquier programa que abra un .docx (Word, Google Docs, el celular, Pages),
 *   pero no se pueden editar ahí; si una fórmula está mal, se corrige en la app y se vuelve a descargar;
 * - **como ecuación de Word** (editables): KaTeX las pasa a MathML y `mathml2omml` a OMML. Se ven en Word y LibreOffice;
 *   otros programas pueden no entenderlas.
 * Los diagramas Mermaid, que Word no sabe dibujar, van siempre como imagen. Todo se arma en el navegador de quien descarga:
 * el servidor no hace nada. Si una fórmula o un diagrama no se pueden convertir, se deja su texto (el LaTeX o el código)
 * para que el documento nunca salga con huecos.
 */
export interface Imagen {
  datos: Uint8Array
  ancho: number
  alto: number
}
export interface OpcionesDocx {
  /** Cómo se convierte un diagrama en imagen (los tests lo reemplazan: en Node no hay dónde dibujarlo). */
  diagrama?: (codigo: string) => Promise<Imagen>
  /** `imagen` (por defecto, se ve en cualquier programa) o `ecuacion` (editable, solo Word y LibreOffice). */
  formulas?: 'imagen' | 'ecuacion'
  /** Cómo se convierte una fórmula en imagen (los tests lo reemplazan). */
  formula?: (tex: string, bloque: boolean) => Promise<FormulaPng | null>
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

  const comoImagen = (opciones.formulas ?? 'imagen') === 'imagen'
  const aFormulaPng = opciones.formula ?? formulaEnImagen
  const imagenDe = (f: FormulaPng, descripcion: string) =>
    new d.ImageRun({ type: 'png', data: f.datos, transformation: { width: f.ancho, height: f.alto }, altText: { name: 'Fórmula', title: 'Fórmula', description: descripcion } })

  /** Una imagen en línea más abajo que la línea de base del texto (`w:position` en medios puntos, que es lo que entiende todo programa). */
  class ImagenBajada extends d.ImageRun {
    private mediosPuntos = 0
    bajar(mediosPuntos: number) {
      this.mediosPuntos = mediosPuntos
      return this
    }
    prepForXml(context: Parameters<InstanceType<typeof d.ImageRun>['prepForXml']>[0]) {
      const xml = super.prepForXml(context) as { 'w:r'?: unknown[] } | undefined
      if (xml?.['w:r'] && this.mediosPuntos > 0) xml['w:r'].unshift({ 'w:rPr': [{ 'w:position': { _attr: { 'w:val': String(-this.mediosPuntos) } } }] })
      return xml as ReturnType<InstanceType<typeof d.ImageRun>['prepForXml']>
    }
  }

  /** La fórmula en línea (o null si hay que dejar su texto): imagen bajada hasta la línea de base del texto, o ecuación de Word. */
  async function formulaEnLinea(tex: string): Promise<InstanceType<typeof d.TextRun> | null> {
    if (comoImagen) {
      const f = await aFormulaPng(tex, false)
      if (!f) return null
      const imagen = new ImagenBajada({ type: 'png', data: f.datos, transformation: { width: f.ancho, height: f.alto }, altText: { name: 'Fórmula', title: 'Fórmula', description: tex } })
      return imagen.bajar(Math.round(f.baja * 1.5)) as unknown as InstanceType<typeof d.TextRun> // px → pt (×0,75) → medios puntos (×2)
    }
    const omml = await aOmml(tex)
    return omml ? enOmml(omml) : null
  }

  async function hijosDeParrafo(trozos: Trozo[]) {
    const hijos: InstanceType<typeof d.TextRun>[] = []
    for (const t of trozos) {
      if (t.tipo === 'texto') hijos.push(...lineas(t.valor))
      else if (t.tipo === 'formula') hijos.push((await formulaEnLinea(t.valor)) ?? new d.TextRun({ text: t.valor, font: MONO }))
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
        let contenido: InstanceType<typeof d.TextRun> | null = null
        if (comoImagen) {
          const f = await aFormulaPng(b.tex, true)
          if (f) contenido = imagenDe(f, b.tex) as unknown as InstanceType<typeof d.TextRun>
        } else {
          const omml = await aOmml(b.tex)
          if (omml) contenido = enOmml(`<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">${omml}</m:oMathPara>`)
        }
        contenido ??= new d.TextRun({ text: b.tex, font: MONO })
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
    styles: { default: { document: { run: { font: 'Calibri', size: 22, language: { value: 'es-CL' } } } } }, // el lector de pantalla necesita saber el idioma
    sections: [{ children: hijos }],
  })
  return d.Packer.toBlob(doc)
}
