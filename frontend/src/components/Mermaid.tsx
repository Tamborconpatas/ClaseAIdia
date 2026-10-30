/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useEffect, useRef, useState } from 'react'
import { empezarDibujo } from '@/lib/dibujos'
import { dibujarDiagrama } from '@/lib/mermaid'
import { useTema } from '@/lib/tema'

/**
 * Dibuja un diagrama Mermaid. El SVG ya viene pasado por DOMPurify y se agrega al DOM como nodos, sin `innerHTML` ni
 * `dangerouslySetInnerHTML`. Si el código no se entiende (un diagrama que escribió la IA a mano alzada) se muestra el
 * código tal cual en vez de dejar un hueco o el ícono de error de Mermaid.
 */
export function Mermaid({ codigo, descripcion, tema }: { codigo: string; descripcion: string; tema?: 'claro' | 'oscuro' }) {
  const { oscuro: temaOscuro } = useTema()
  const oscuro = tema ? tema === 'oscuro' : temaOscuro // la hoja del PDF pide siempre «claro»
  const ref = useRef<HTMLDivElement>(null)
  const [fallo, setFallo] = useState(false)

  useEffect(() => {
    let vivo = true
    const terminar = empezarDibujo()
    dibujarDiagrama(codigo, oscuro)
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
  }, [codigo, oscuro])

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
