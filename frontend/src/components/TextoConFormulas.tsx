import { useEffect, useMemo, useRef, useState } from 'react'
import { Mermaid } from '@/components/Mermaid'
import { partir, type Trozo } from '@/lib/formulas'
import { cn } from '@/lib/utils'

// KaTeX (y sus tipografías) se baja solo cuando una pantalla tiene una fórmula: el resto de la app no lo carga.
let katex: Promise<typeof import('katex').default> | undefined
const cargarKatex = () =>
  (katex ??= Promise.all([import('katex'), import('katex/dist/katex.min.css')]).then(([m]) => m.default))

/**
 * Una fórmula en LaTeX. No usa `dangerouslySetInnerHTML`: `katex.render` arma el DOM él mismo, con `trust: false`
 * (sin enlaces ni imágenes) y con topes de tamaño y de expansión de macros. Si el LaTeX no se entiende (la IA lo
 * escribe a mano alzada), se muestra tal cual en vez de una pantalla en blanco.
 */
export function Formula({ tex, bloque }: { tex: string; bloque: boolean }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [fallo, setFallo] = useState(false)

  useEffect(() => {
    let vivo = true
    void cargarKatex().then((k) => {
      if (!vivo || !ref.current) return
      try {
        k.render(tex, ref.current, { displayMode: bloque, throwOnError: true, trust: false, strict: 'ignore', maxSize: 30, maxExpand: 1000 })
        setFallo(false)
      } catch {
        setFallo(true)
      }
    })
    return () => {
      vivo = false
    }
  }, [tex, bloque])

  if (fallo) {
    return (
      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]" title="No se pudo dibujar esta fórmula; se muestra su texto">
        {tex}
      </code>
    )
  }
  // Mientras carga KaTeX se ve el LaTeX en bruto; `render` lo reemplaza.
  return <span ref={ref}>{tex}</span>
}

/** Texto con fórmulas (`$...$`, `$$...$$`, `\[...\]`) y diagramas Mermaid ya partidos y dibujados, en el mismo orden del original. */
export function TextoConFormulas({ texto, className }: { texto: string; className?: string }) {
  const trozos = useMemo(() => partir(texto), [texto])
  // Lo que va en línea (texto y fórmulas chicas) se junta en un párrafo; las fórmulas en bloque y los diagramas cortan el párrafo.
  const grupos: Trozo[][] = []
  for (const t of trozos) {
    const enLinea = t.tipo === 'texto' || (t.tipo === 'formula' && !t.bloque)
    if (enLinea && grupos.length > 0 && grupos[grupos.length - 1][0].tipo !== 'mermaid' && !esBloque(grupos[grupos.length - 1][0])) grupos[grupos.length - 1].push(t)
    else grupos.push([t])
  }
  return (
    <div className={cn('space-y-2 leading-relaxed', className)}>
      {grupos.map((grupo, i) => {
        const t = grupo[0]
        if (t.tipo === 'mermaid') return <Mermaid key={i} codigo={t.valor} descripcion="Diagrama de la pizarra" />
        if (esBloque(t) && t.tipo === 'formula') {
          return (
            <div key={i} className="overflow-x-auto py-1" tabIndex={0} aria-label="Fórmula">
              <Formula tex={t.valor} bloque />
            </div>
          )
        }
        return (
          <p key={i} className="whitespace-pre-line">
            {grupo.map((g, j) => (g.tipo === 'texto' ? <span key={j}>{g.valor}</span> : g.tipo === 'formula' ? <Formula key={j} tex={g.valor} bloque={false} /> : null))}
          </p>
        )
      })}
    </div>
  )
}

const esBloque = (t: Trozo) => t.tipo === 'formula' && t.bloque
