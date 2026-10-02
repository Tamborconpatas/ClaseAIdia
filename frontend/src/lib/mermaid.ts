// Mermaid pesa bastante: se baja solo cuando hay un diagrama, y se configura una sola vez.
let mermaid: Promise<typeof import('mermaid').default> | undefined
const cargarMermaid = () =>
  (mermaid ??= import('mermaid').then((m) => {
    // `strict`: Mermaid no ejecuta HTML ni enlaces dentro del diagrama. `htmlLabels: false` va en la raíz (no dentro de
    // `flowchart`, que deja los nodos como <foreignObject>): los textos salen como SVG puro, que es lo único que deja pasar
    // DOMPurify. Con la opción mal puesta los nodos se veían vacíos (medido en el navegador).
    m.default.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral', htmlLabels: false, flowchart: { useMaxWidth: true } })
    return m.default
  }))

let contador = 0

/** SVG del diagrama, ya pasado por DOMPurify (perfil SVG). Lanza si el código no se entiende. */
export async function dibujarDiagrama(codigo: string): Promise<string> {
  const id = `mermaid-${++contador}`
  try {
    const [m, purify] = await Promise.all([cargarMermaid(), import('dompurify')])
    const { svg } = await m.render(id, codigo)
    return purify.default.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })
  } catch (e) {
    document.getElementById(`d${id}`)?.remove() // Mermaid deja ahí su dibujo de error
    throw e
  }
}

/** Convierte el SVG de un diagrama en una imagen PNG (Word no dibuja Mermaid, pero sí imágenes). */
export async function svgAPng(svg: string, anchoMaximo = 640): Promise<{ datos: Uint8Array; ancho: number; alto: number }> {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const raiz = doc.documentElement
  const [, , vw, vh] = (raiz.getAttribute('viewBox') ?? '').split(/[\s,]+/).map(Number)
  if (!(vw > 0 && vh > 0)) throw new Error('El diagrama no trae su tamaño')
  raiz.setAttribute('width', String(vw))
  raiz.setAttribute('height', String(vh))
  raiz.removeAttribute('style')
  const escala = 2 // el doble de píxeles que de tamaño en la página: se ve nítido al imprimir o ampliar
  const lienzo = document.createElement('canvas')
  lienzo.width = Math.round(vw * escala)
  lienzo.height = Math.round(vh * escala)
  const imagen = new Image()
  await new Promise<void>((ok, mal) => {
    imagen.onload = () => ok()
    imagen.onerror = () => mal(new Error('No se pudo convertir el diagrama en imagen'))
    imagen.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(raiz))}`
  })
  const ctx = lienzo.getContext('2d')!
  ctx.fillStyle = '#ffffff' // Word muestra el PNG sobre la página: fondo blanco, no transparente
  ctx.fillRect(0, 0, lienzo.width, lienzo.height)
  ctx.drawImage(imagen, 0, 0, lienzo.width, lienzo.height)
  const png = await new Promise<Blob | null>((r) => lienzo.toBlob(r, 'image/png'))
  if (!png) throw new Error('No se pudo convertir el diagrama en imagen')
  const ancho = Math.min(vw, anchoMaximo)
  return { datos: new Uint8Array(await png.arrayBuffer()), ancho, alto: Math.round((vh * ancho) / vw) }
}
