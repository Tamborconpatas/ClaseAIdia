/**
 * Una fórmula LaTeX como imagen, para el Word que tiene que verse en cualquier programa (Google Docs, el celular, Pages...)
 * y no solo en los que entienden las ecuaciones de Word. Se usa MathJax en su salida SVG porque dibuja con trazados propios
 * (sin depender de tipografías del equipo ni de HTML, que es lo que falla al convertir a imagen en algunos teléfonos).
 * Solo se carga cuando se pide el Word.
 */
export interface FormulaSvg {
  svg: string
  /** Tamaño natural, en "ex" (la altura de una x del texto): MathJax no usa píxeles. */
  anchoEx: number
  altoEx: number
  /** Cuánto baja la fórmula respecto de la línea de base del texto (en ex, ≥ 0). */
  bajaEx: number
}

let motor: Promise<(tex: string, bloque: boolean) => FormulaSvg | null> | undefined

async function cargarMotor() {
  const [{ mathjax }, { TeX }, { SVG }, { browserAdaptor }, { RegisterHTMLHandler }] = await Promise.all([
    import('mathjax-full/js/mathjax.js'),
    import('mathjax-full/js/input/tex.js'),
    import('mathjax-full/js/output/svg.js'),
    import('mathjax-full/js/adaptors/browserAdaptor.js'),
    import('mathjax-full/js/handlers/html.js'),
    import('mathjax-full/js/input/tex/base/BaseConfiguration.js'), // registran sus paquetes en TeX
    import('mathjax-full/js/input/tex/ams/AmsConfiguration.js'),
  ])
  RegisterHTMLHandler(browserAdaptor())
  // Sin `noundefined`: un comando que no existe es un error (y el documento deja el LaTeX como texto) y no un trozo rojo.
  const html = mathjax.document(document, { InputJax: new TeX({ packages: ['base', 'ams'] }), OutputJax: new SVG({ fontCache: 'none' }) })
  return (tex: string, bloque: boolean): FormulaSvg | null => {
    const nodo = html.convert(tex, { display: bloque }) as HTMLElement
    const svg = nodo.querySelector('svg')
    if (!svg || nodo.querySelector('[data-mjx-error]')) return null
    const ex = (atributo: string | null) => parseFloat(atributo ?? '')
    const ancho = ex(svg.getAttribute('width'))
    const alto = ex(svg.getAttribute('height'))
    if (!(ancho > 0 && alto > 0)) return null
    const vertical = /vertical-align:\s*(-?[\d.]+)ex/.exec(svg.getAttribute('style') ?? '')
    svg.removeAttribute('style')
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    return { svg: svg.outerHTML.replaceAll('currentColor', '#000000'), anchoEx: ancho, altoEx: alto, bajaEx: Math.max(0, -parseFloat(vertical?.[1] ?? '0')) }
  }
}

/** El SVG de la fórmula, o null si MathJax no la entiende. */
export async function formulaASvg(tex: string, bloque: boolean): Promise<FormulaSvg | null> {
  motor ??= cargarMotor()
  try {
    return (await motor)(tex, bloque)
  } catch {
    return null
  }
}

export interface FormulaPng {
  datos: Uint8Array
  /** Tamaño en la página, en píxeles de documento (96 por pulgada). */
  ancho: number
  alto: number
  /** Cuánto debe bajar respecto de la línea de base del texto, en píxeles de documento. */
  baja: number
}

const PX_POR_EX = 6.5 // MathJax y el texto de 11 pt (Calibri, 14,7 px) quedan del mismo tamaño; con 7 salían un 8 % más grandes
const ESCALA = 4 // píxeles reales por píxel de página: nítido al ampliar o imprimir

/** Dibuja el SVG de una fórmula en un PNG con fondo transparente. Solo en un navegador. */
export async function formulaAPng(f: FormulaSvg): Promise<FormulaPng> {
  const ancho = f.anchoEx * PX_POR_EX
  const alto = f.altoEx * PX_POR_EX
  const lienzo = document.createElement('canvas')
  lienzo.width = Math.max(1, Math.round(ancho * ESCALA))
  lienzo.height = Math.max(1, Math.round(alto * ESCALA))
  const doc = new DOMParser().parseFromString(f.svg, 'image/svg+xml').documentElement
  doc.setAttribute('width', String(lienzo.width))
  doc.setAttribute('height', String(lienzo.height))
  const imagen = new Image()
  await new Promise<void>((ok, mal) => {
    imagen.onload = () => ok()
    imagen.onerror = () => mal(new Error('No se pudo convertir la fórmula en imagen'))
    imagen.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(doc))}`
  })
  lienzo.getContext('2d')!.drawImage(imagen, 0, 0, lienzo.width, lienzo.height)
  const png = await new Promise<Blob | null>((r) => lienzo.toBlob(r, 'image/png'))
  if (!png) throw new Error('No se pudo convertir la fórmula en imagen')
  return { datos: new Uint8Array(await png.arrayBuffer()), ancho: Math.round(ancho), alto: Math.round(alto), baja: f.bajaEx * PX_POR_EX }
}

export async function formulaEnImagen(tex: string, bloque: boolean): Promise<FormulaPng | null> {
  const svg = await formulaASvg(tex, bloque)
  if (!svg) return null
  try {
    return await formulaAPng(svg)
  } catch {
    return null
  }
}
