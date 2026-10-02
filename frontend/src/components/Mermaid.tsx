import { useEffect, useRef, useState } from 'react'
import { empezarDibujo } from '@/lib/dibujos'
import { dibujarDiagrama } from '@/lib/mermaid'

/**
 * Dibuja un diagrama Mermaid. El SVG ya viene pasado por DOMPurify y se agrega al DOM como nodos, sin `innerHTML` ni
 * `dangerouslySetInnerHTML`. Si el código no se entiende (un diagrama que escribió la IA a mano alzada) se muestra el
 * código tal cual en vez de dejar un hueco o el ícono de error de Mermaid.
 */
export function Mermaid({ codigo, descripcion }: { codigo: string; descripcion: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [fallo, setFallo] = useState(false)

  useEffect(() => {
    let vivo = true
    const terminar = empezarDibujo()
    dibujarDiagrama(codigo)
      .then((svg) => {
        if (!vivo || !ref.current) return
        const dibujo = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement
        ref.current.replaceChildren(document.importNode(dibujo, true))
        setFallo(false)
      })
      .catch(() => vivo && setFallo(true))
      .finally(terminar)
    return () => {
      vivo = false
      terminar()
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
