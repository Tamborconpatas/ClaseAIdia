/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { formulaEnImagen, type FormulaPng } from './formulaImagen'
import type { Imagen } from './docx'
import { dibujarDiagrama, svgAPng } from '@/lib/mermaid'
import type { Bloque } from './modelo'

/**
 * PDF que se descarga directo, sin pasar por el diálogo de impresión. Se arma en el navegador de quien descarga (el servidor no
 * hace nada), con el mismo modelo, las mismas imágenes de fórmulas y los mismos diagramas que el Word. El texto queda como texto
 * (se puede seleccionar y buscar), no como una foto de la página. Si una fórmula o un diagrama no se pueden convertir, se deja
 * su texto (el LaTeX o el código) para que el documento nunca salga con huecos.
 *
 * shortcut: usa las tipografías estándar de PDF (Helvetica y Courier), que solo traen las letras del alfabeto latino occidental
 * (todo el español, comillas y guiones); un símbolo fuera de eso (→, ≥…) se cambia por su equivalente en ASCII (->, >=). Si hiciera
 * falta más, incrustar una tipografía con esos símbolos (pesa cientos de KB). Tampoco lleva etiquetas de accesibilidad de PDF
 * («PDF etiquetado»), que sí generaría la impresión del navegador: lleva título e idioma, y el LaTeX de cada fórmula y la descripción
 * de cada diagrama van como texto invisible bajo su imagen; el Word, además, tiene títulos de verdad y texto alternativo.
 */
export interface OpcionesPdf {
  /** Cómo se convierte un diagrama en imagen (los tests lo reemplazan: en Node no hay dónde dibujarlo). */
  diagrama?: (codigo: string) => Promise<Imagen>
  /** Cómo se convierte una fórmula en imagen (los tests lo reemplazan). */
  formula?: (tex: string, bloque: boolean) => Promise<FormulaPng | null>
}

const PT_POR_PX = 0.75 // las imágenes vienen en píxeles de documento (96 por pulgada)
const PAGINA = { ancho: 595.28, alto: 841.89 } // A4, en puntos
const MARGEN = 57 // 2 cm
const ANCHO = PAGINA.ancho - 2 * MARGEN
const CUERPO = 11
const INTERLINEA = 1.38
const GRIS: [number, number, number] = [102, 102, 102]
const NEGRO: [number, number, number] = [0, 0, 0]

const REEMPLAZOS: Record<string, string> = {
  '→': '->', '←': '<-', '↔': '<->', '⇒': '=>', '≥': '>=', '≤': '<=', '≠': '!=', '≈': '~', '−': '-', '‑': '-', '×': '×', '✓': 'v', '✔': 'v',
  ' ': ' ', ' ': ' ', '​': '',
}

/** El texto con solo lo que las tipografías estándar de PDF saben dibujar; lo demás pasa a su equivalente en ASCII o se omite. */
export function textoSeguro(t: string): string {
  // eslint-disable-next-line no-control-regex
  return t.normalize('NFC').replace(/[^\n\x20-\x7E -ÿ–—‘’“”•…€]/g, (c) => REEMPLAZOS[c] ?? '')
}

type Estilo = 'normal' | 'bold' | 'italic'
type Pieza =
  | { tipo: 'palabra'; texto: string; estilo: Estilo; espacio: boolean; ancho: number; mono?: boolean }
  | { tipo: 'formula'; png: FormulaPng; espacio: boolean; ancho: number; tex: string }
  | { tipo: 'salto' }

interface Colocada {
  pieza: Exclude<Pieza, { tipo: 'salto' }>
  x: number
}
interface Linea {
  items: Colocada[]
  arriba: number // cuánto sube sobre la línea de base
  abajo: number // cuánto baja
}

type Doc = InstanceType<(typeof import('jspdf'))['jsPDF']>

const diagramaEnImagen = async (codigo: string): Promise<Imagen> => svgAPng(await dibujarDiagrama(codigo))

export async function generarPdf(bloques: Bloque[], opciones: OpcionesPdf = {}): Promise<Blob> {
  const { jsPDF } = await import('jspdf') // la librería de PDF se baja solo al pedir el archivo
  const aImagen = opciones.diagrama ?? diagramaEnImagen
  const aFormulaPng = opciones.formula ?? formulaEnImagen
  const titulo = bloques.find((b) => b.t === 'titulo')
  const doc: Doc = new jsPDF({ unit: 'pt', format: 'a4', compress: true })
  doc.setProperties({ title: titulo && titulo.t === 'titulo' ? titulo.texto : 'Clase', creator: 'ClaseAIdia', author: 'ClaseAIdia' })
  try {
    doc.setLanguage('es-CL' as never) // los lectores de pantalla necesitan saber el idioma
  } catch {
    /* una versión sin ese código de idioma: el PDF sale igual */
  }

  let y = MARGEN
  const asegurar = (alto: number) => {
    if (y + alto > PAGINA.alto - MARGEN && y > MARGEN) {
      doc.addPage()
      y = MARGEN
    }
  }

  const fuente = (estilo: Estilo, tamaño: number, mono = false) => {
    doc.setFont(mono ? 'courier' : 'helvetica', mono ? 'normal' : estilo)
    doc.setFontSize(tamaño)
  }

  /** Las piezas (palabras y fórmulas) de un texto; los saltos de línea del original se conservan. */
  const palabras = (texto: string, estilo: Estilo, tamaño: number, mono = false): Pieza[] => {
    const piezas: Pieza[] = []
    fuente(estilo, tamaño, mono)
    let espacio = false
    for (const parte of textoSeguro(texto).split(/(\s+)/)) {
      if (parte === '') continue
      if (/^\s+$/.test(parte)) {
        for (let i = 0; i < (parte.match(/\n/g)?.length ?? 0); i++) piezas.push({ tipo: 'salto' })
        espacio = !parte.includes('\n')
      } else {
        piezas.push({ tipo: 'palabra', texto: parte, estilo, espacio, ancho: doc.getTextWidth(parte), mono })
        espacio = false
      }
    }
    return piezas
  }

  /** Reparte las piezas en líneas de ese ancho. */
  const distribuir = (piezas: Pieza[], x0: number, ancho: number, tamaño: number): Linea[] => {
    const lineas: Linea[] = []
    let actual: Linea = { items: [], arriba: tamaño * 0.8, abajo: tamaño * 0.22 }
    let x = x0
    const cerrar = () => {
      lineas.push(actual)
      actual = { items: [], arriba: tamaño * 0.8, abajo: tamaño * 0.22 }
      x = x0
    }
    fuente('normal', tamaño)
    const ancho_espacio = doc.getTextWidth(' ')
    for (const p of piezas) {
      if (p.tipo === 'salto') {
        cerrar()
        continue
      }
      const separacion = p.espacio && actual.items.length > 0 ? ancho_espacio : 0
      if (actual.items.length > 0 && x + separacion + p.ancho > x0 + ancho) cerrar()
      x += actual.items.length > 0 && p.espacio ? ancho_espacio : 0
      actual.items.push({ pieza: p, x })
      x += p.ancho
      if (p.tipo === 'formula') {
        const alto = p.png.alto * PT_POR_PX
        const baja = p.png.baja * PT_POR_PX
        actual.arriba = Math.max(actual.arriba, alto - baja)
        actual.abajo = Math.max(actual.abajo, baja)
      }
    }
    if (actual.items.length > 0 || lineas.length === 0) lineas.push(actual)
    return lineas
  }

  const altoDeLinea = (l: Linea, tamaño: number) => Math.max(tamaño * INTERLINEA, l.arriba + l.abajo + 3)

  /** Dibuja las líneas desde `y`, pasando de página cuando hace falta. */
  const dibujar = (lineas: Linea[], tamaño: number, color = NEGRO) => {
    for (const l of lineas) {
      const alto = altoDeLinea(l, tamaño)
      asegurar(alto)
      const base = y + (alto - (l.arriba + l.abajo)) / 2 + l.arriba
      for (const { pieza, x } of l.items) {
        if (pieza.tipo === 'palabra') {
          fuente(pieza.estilo, tamaño, pieza.mono)
          doc.setTextColor(...color)
          doc.text(pieza.texto, x, base)
        } else {
          const w = pieza.png.ancho * PT_POR_PX
          const h = pieza.png.alto * PT_POR_PX
          doc.addImage(pieza.png.datos, 'PNG', x, base + pieza.png.baja * PT_POR_PX - h, w, h)
          alternativo(pieza.tex, x, base)
        }
      }
      y += alto
    }
    doc.setTextColor(...NEGRO)
  }

  /** Un texto de un solo estilo, en un bloque. */
  const texto = (t: string, o: { estilo?: Estilo; tamaño?: number; color?: [number, number, number]; x?: number; despues?: number; antes?: number; mono?: boolean }) => {
    const tamaño = o.tamaño ?? CUERPO
    const x = o.x ?? MARGEN
    y += o.antes ?? 0
    dibujar(distribuir(palabras(t, o.estilo ?? 'normal', tamaño, o.mono), x, MARGEN + ANCHO - x, tamaño), tamaño, o.color)
    y += o.despues ?? 0
  }

  /** El texto de una imagen (el LaTeX de una fórmula, la descripción de un diagrama) como texto invisible debajo de ella: el visor de PDF lo
   *  puede buscar y copiar y un lector de pantalla lo puede leer. */
  const alternativo = (t: string, x: number, y0: number) => {
    fuente('normal', 8, true)
    doc.text(textoSeguro(t).replace(/\s+/g, ' ') + ' ', x, y0, { renderingMode: 'invisible' })
  }

  /** Una imagen centrada, reducida si no cabe a lo ancho o a lo alto de la página. */
  const imagenCentrada = (datos: Uint8Array, anchoPx: number, altoPx: number, alt: string) => {
    let w = anchoPx * PT_POR_PX
    let h = altoPx * PT_POR_PX
    const escala = Math.min(1, ANCHO / w, ((PAGINA.alto - 2 * MARGEN) * 0.8) / h)
    w *= escala
    h *= escala
    asegurar(h + 12)
    doc.addImage(datos, 'PNG', MARGEN + (ANCHO - w) / 2, y + 6, w, h)
    alternativo(alt, MARGEN + (ANCHO - w) / 2, y + 6 + h)
    y += h + 12
  }

  /** Los bloques de código o de texto plano (cuando una fórmula o un diagrama no se pudo convertir). */
  const codigo = (t: string) => {
    for (const l of t.split('\n')) texto(l, { tamaño: 9, mono: true, x: MARGEN + 12 })
    y += 4
  }

  for (const b of bloques) {
    switch (b.t) {
      case 'titulo':
        texto(b.texto, { estilo: 'bold', tamaño: 20, despues: 4 })
        break
      case 'subtitulo':
        texto(b.texto, { tamaño: 10.5, color: GRIS, despues: 10 })
        break
      case 'aviso': {
        const lineas = distribuir(palabras(b.texto, 'bold', 10.5), MARGEN + 8, ANCHO - 16, 10.5)
        const alto = lineas.reduce((s, l) => s + altoDeLinea(l, 10.5), 0) + 12
        asegurar(alto + 8)
        doc.setFillColor(253, 243, 215)
        doc.rect(MARGEN, y, ANCHO, alto, 'F')
        y += 6
        dibujar(lineas, 10.5)
        y += 6 + 8
        break
      }
      case 'seccion':
        // Un título no se queda solo al pie de la página: necesita sitio para el título y un par de líneas más.
        asegurar(14 * INTERLINEA + (b.nota ? 14 : 0) + 4 * CUERPO * INTERLINEA + 18)
        texto(b.texto, { estilo: 'bold', tamaño: 14, antes: 18, despues: 3 })
        if (b.nota) texto(b.nota, { estilo: 'italic', tamaño: 9, color: GRIS, despues: 4 })
        break
      case 'nota':
        asegurar(9 * INTERLINEA + 2 * CUERPO * INTERLINEA)
        texto(b.texto, { estilo: 'italic', tamaño: 9, color: GRIS, antes: 6 })
        break
      case 'parrafo': {
        const piezas: Pieza[] = []
        let espacio = false
        for (const t of b.trozos) {
          if (t.tipo === 'texto') {
            const ps = palabras(t.valor, 'normal', CUERPO)
            if (ps.length > 0 && ps[0].tipo === 'palabra' && espacio) ps[0] = { ...ps[0], espacio: true }
            piezas.push(...ps)
            espacio = /\s$/.test(t.valor) && !t.valor.endsWith('\n') // el espacio con el que termina este texto separa de lo que sigue
          } else if (t.tipo === 'formula') {
            const png = await aFormulaPng(t.valor, false)
            if (png) piezas.push({ tipo: 'formula', png, espacio, ancho: png.ancho * PT_POR_PX, tex: t.valor })
            else {
              const ps = palabras(t.valor, 'normal', CUERPO, true) // no se pudo convertir: queda su LaTeX, en letra de máquina
              if (ps[0]?.tipo === 'palabra') ps[0] = { ...ps[0], espacio }
              piezas.push(...ps)
            }
            espacio = false
          }
        }
        dibujar(distribuir(piezas, MARGEN, ANCHO, CUERPO), CUERPO)
        y += 5
        break
      }
      case 'vinetas':
        for (const item of b.items) {
          const lineas = distribuir(palabras(item, 'normal', CUERPO), MARGEN + 16, ANCHO - 16, CUERPO)
          const primera = lineas[0]
          const alto = altoDeLinea(primera, CUERPO)
          asegurar(alto)
          fuente('normal', CUERPO)
          doc.text('•', MARGEN + 4, y + (alto - (primera.arriba + primera.abajo)) / 2 + primera.arriba) // en la misma línea de base que el texto
          dibujar(lineas, CUERPO)
          y += 2
        }
        y += 3
        break
      case 'formula': {
        const png = await aFormulaPng(b.tex, true)
        if (png) imagenCentrada(png.datos, png.ancho, png.alto, b.tex)
        else texto(b.tex, { mono: true, tamaño: 10, x: MARGEN + 12, antes: 4, despues: 4 })
        break
      }
      case 'diagrama':
        try {
          const img = await aImagen(b.codigo)
          imagenCentrada(img.datos, img.ancho, img.alto, b.descripcion)
        } catch {
          texto('No se pudo dibujar este diagrama; este es su código:', { estilo: 'italic', tamaño: 9, color: GRIS })
          codigo(b.codigo)
        }
        break
      case 'tarjeta': {
        const conEspacio = (ps: Pieza[]): Pieza[] => (ps[0]?.tipo === 'palabra' ? [{ ...ps[0], espacio: true }, ...ps.slice(1)] : ps) // el texto sigue a la etiqueta con un espacio
        const pregunta = [...palabras('Pregunta:', 'bold', CUERPO), ...conEspacio(palabras(b.pregunta, 'normal', CUERPO))]
        const respuesta = [...palabras('Respuesta:', 'bold', CUERPO), ...conEspacio(palabras(b.respuesta, 'normal', CUERPO))]
        const lp = distribuir(pregunta, MARGEN, ANCHO, CUERPO)
        const lr = distribuir(respuesta, MARGEN + 18, ANCHO - 18, CUERPO)
        asegurar(altoDeLinea(lp[0], CUERPO) * (lp.length + Math.min(2, lr.length)) + 8) // la pregunta no se separa de su respuesta
        y += 5
        dibujar(lp, CUERPO)
        dibujar(lr, CUERPO)
        y += 3
        break
      }
    }
  }
  return doc.output('blob')
}
