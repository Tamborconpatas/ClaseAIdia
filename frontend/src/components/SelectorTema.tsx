import { Monitor, Moon, Sun } from 'lucide-react'
import { cambiarTema, useTema, type Tema } from '@/lib/tema'
import { cn } from '@/lib/utils'

const OPCIONES: { tema: Tema; etiqueta: string; icono: typeof Sun }[] = [
  { tema: 'sistema', etiqueta: 'Sistema', icono: Monitor },
  { tema: 'claro', etiqueta: 'Claro', icono: Sun },
  { tema: 'oscuro', etiqueta: 'Oscuro', icono: Moon },
]

/** Elegir el tema de color: sigue al sistema, o claro, u oscuro. Cada opción lleva su nombre también para quien no ve los íconos. */
export function SelectorTema({ className, conTexto = false }: { className?: string; conTexto?: boolean }) {
  const { tema } = useTema()
  return (
    <div role="group" aria-label="Tema de color" className={cn('inline-flex rounded-lg border bg-card p-0.5', className)}>
      {OPCIONES.map(({ tema: t, etiqueta, icono: Icono }) => (
        <button
          key={t}
          type="button"
          aria-pressed={tema === t}
          title={etiqueta}
          onClick={() => cambiarTema(t)}
          className={cn(
            'flex min-h-9 min-w-9 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
            tema === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
            conTexto && 'flex-1',
          )}
        >
          <Icono className="size-4 shrink-0" aria-hidden />
          {conTexto ? etiqueta : <span className="sr-only">{etiqueta}</span>}
        </button>
      ))}
    </div>
  )
}
