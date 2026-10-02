import { Formula } from '@/components/TextoConFormulas'
import { Mermaid } from '@/components/Mermaid'
import type { Bloque } from '@/lib/exportar/modelo'

/**
 * La clase como hoja para imprimir o guardar como PDF: todo abierto (las respuestas de las tarjetas también), sin botones
 * ni menús, con las fórmulas y los diagramas ya dibujados. Está oculta en pantalla y es lo único que se ve al imprimir
 * (ver `#impresion` en index.css). Usa el mismo modelo que el Word, así los dos archivos llevan lo mismo.
 */
export function VistaImpresion({ bloques }: { bloques: Bloque[] }) {
  return (
    <main className="mx-auto max-w-[170mm] space-y-2 text-[11pt] leading-relaxed text-black">
      {bloques.map((b, i) => {
        switch (b.t) {
          case 'titulo':
            return <h1 key={i} className="text-3xl font-semibold">{b.texto}</h1>
          case 'subtitulo':
            return <p key={i} className="pb-2 text-sm text-neutral-600">{b.texto}</p>
          case 'aviso':
            return <p key={i} className="rounded bg-amber-100 p-3 font-semibold" style={{ printColorAdjust: 'exact', WebkitPrintColorAdjust: 'exact' }}>{b.texto}</p>
          case 'seccion':
            return (
              <div key={i} className="break-after-avoid pt-4">
                <h2 className="text-lg font-semibold text-blue-800">{b.texto}</h2>
                {b.nota && <p className="text-xs italic text-neutral-600">{b.nota}</p>}
              </div>
            )
          case 'nota':
            return <p key={i} className="break-after-avoid pt-2 text-xs italic text-neutral-600">{b.texto}</p>
          case 'parrafo':
            return (
              <p key={i} className="whitespace-pre-line">
                {b.trozos.map((t, j) => (t.tipo === 'texto' ? <span key={j}>{t.valor}</span> : t.tipo === 'formula' ? <Formula key={j} tex={t.valor} bloque={false} /> : null))}
              </p>
            )
          case 'vinetas':
            return (
              <ul key={i} className="list-disc space-y-1 pl-6">
                {b.items.map((item, j) => <li key={j}>{item}</li>)}
              </ul>
            )
          case 'formula':
            return <div key={i} className="break-inside-avoid overflow-hidden py-1"><Formula tex={b.tex} bloque /></div>
          case 'diagrama':
            return <div key={i} className="break-inside-avoid"><Mermaid codigo={b.codigo} descripcion={b.descripcion} /></div>
          case 'tarjeta':
            return (
              <div key={i} className="break-inside-avoid pt-2">
                <p className="font-semibold">Pregunta: <span className="font-normal">{b.pregunta}</span></p>
                <p className="pl-5"><span className="font-semibold">Respuesta: </span>{b.respuesta}</p>
              </div>
            )
        }
      })}
    </main>
  )
}
