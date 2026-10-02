import { useEffect, useRef, useState } from 'react'

// Mermaid pesa bastante: se baja solo cuando una pantalla tiene un diagrama, y se configura una sola vez.
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

/**
 * Dibuja un diagrama Mermaid. El SVG que devuelve Mermaid pasa por DOMPurify (perfil SVG) y se agrega al DOM como nodos,
 * sin `innerHTML` ni `dangerouslySetInnerHTML`. Si el código no se entiende (un diagrama que escribió la IA a mano
 * alzada) se muestra el código tal cual en vez de dejar un hueco o el ícono de error de Mermaid.
 */
export function Mermaid({ codigo, descripcion }: { codigo: string; descripcion: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [fallo, setFallo] = useState(false)

  useEffect(() => {
    let vivo = true
    const id = `mermaid-${++contador}`
    void Promise.all([cargarMermaid(), import('dompurify')])
      .then(async ([m, purify]) => {
        const { svg } = await m.render(id, codigo)
        if (!vivo || !ref.current) return
        const limpio = purify.default.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, RETURN_DOM_FRAGMENT: true })
        ref.current.replaceChildren(limpio)
        setFallo(false)
      })
      .catch(() => {
        document.getElementById(`d${id}`)?.remove() // Mermaid deja ahí su dibujo de error
        if (vivo) setFallo(true)
      })
    return () => {
      vivo = false
    }
  }, [codigo])

  if (fallo) {
    return (
      <div className="space-y-1">
        <p className="text-xs text-muted-foreground">No se pudo dibujar este diagrama; este es su código:</p>
        <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">{codigo}</pre>
      </div>
    )
  }
  return <div ref={ref} role="img" aria-label={descripcion} className="flex justify-center overflow-x-auto py-2 [&_svg]:h-auto [&_svg]:max-w-full" />
}
