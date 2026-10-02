import type { ReactNode } from 'react'
import { LogOut, type LucideIcon } from 'lucide-react'
import { Logo } from '@/components/comunes'
import { PieLegal } from '@/views/Legal'
import { Button } from '@/components/ui/button'
import type { Usuario } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface ItemNav {
  id: string
  etiqueta: string
  icono: LucideIcon
}

const iniciales = (nombre: string) =>
  nombre
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase()

interface Props {
  items: ItemNav[]
  activo: string
  onCambiar: (id: string) => void
  usuario: Usuario | null
  /** Quién es, p. ej. "Profesor" o "Alumno · 8°A". */
  etiquetaRol: string
  onSalir: () => void
  children: ReactNode
}

/**
 * Dos diseños, no uno adaptado:
 *  - PC (md+): barra lateral fija a la izquierda, contenido a la derecha con título grande.
 *  - Teléfono: barra superior mínima y pestañas abajo (al alcance del pulgar).
 */
export function AppShell({ items, activo, onCambiar, usuario, etiquetaRol, onSalir, children }: Props) {
  const actual = items.find((i) => i.id === activo) ?? items[0]

  return (
    <div className="min-h-dvh">
      {/* Quien navega con teclado o lector de pantalla se salta el menú: solo aparece al recibir el foco. */}
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Saltar al contenido
      </a>
      {/* ---------- PC: barra lateral ---------- */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r bg-sidebar p-4 desk:flex">
        <Logo className="px-2 pb-6 pt-2" />
        <nav className="flex flex-1 flex-col gap-1" aria-label="Principal">
          {items.map((it) => (
            <button
              key={it.id}
              onClick={() => onCambiar(it.id)}
              aria-current={it.id === actual.id ? 'page' : undefined}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
                it.id === actual.id && 'bg-accent text-accent-foreground',
              )}
            >
              <it.icono className="size-[18px]" />
              {it.etiqueta}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3 rounded-xl border bg-card p-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
            {usuario ? iniciales(usuario.nombre) : '·'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{usuario?.nombre ?? '…'}</p>
            <p className="text-xs text-muted-foreground">{etiquetaRol}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onSalir} aria-label="Cerrar sesión" title="Cerrar sesión">
            <LogOut />
          </Button>
        </div>
      </aside>

      {/* ---------- Teléfono: barra superior ---------- */}
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/90 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] backdrop-blur short:h-11 desk:hidden">
        <h1 className="text-lg font-semibold">{actual.etiqueta}</h1>
        <div className="flex items-center gap-1">
          <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">
            {etiquetaRol}
          </span>
          <Button variant="ghost" size="icon-lg" onClick={onSalir} aria-label="Cerrar sesión">
            <LogOut />
          </Button>
        </div>
      </header>

      <main id="contenido" tabIndex={-1} className="outline-none pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] pb-28 pt-4 short:pb-20 desk:pb-10 desk:pl-[calc(16rem+2.5rem)] desk:pr-10 desk:pt-8">
        <div className="mx-auto max-w-3xl desk:max-w-6xl">
          <div className="mb-6 hidden desk:block">
            <h1 className="text-2xl font-semibold tracking-tight">{actual.etiqueta}</h1>
            {usuario && <p className="text-sm text-muted-foreground">Hola, {usuario.nombre.split(' ')[0]}</p>}
          </div>
          {children}
          <PieLegal className="mt-10" />
        </div>
      </main>

      {/* ---------- Teléfono: pestañas abajo ---------- */}
      <nav
        aria-label="Principal"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t bg-background/95 pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] pr-[env(safe-area-inset-right)] backdrop-blur desk:hidden"
      >
        {items.map((it) => {
          const sel = it.id === actual.id
          return (
            <button
              key={it.id}
              onClick={() => onCambiar(it.id)}
              aria-current={sel ? 'page' : undefined}
              className="flex min-h-16 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium short:min-h-12 short:flex-row short:gap-2 short:text-xs"
            >
              <span
                className={cn(
                  'flex h-8 w-14 items-center justify-center rounded-full transition-colors short:h-7 short:w-12',
                  sel ? 'bg-primary/12 text-primary' : 'text-muted-foreground',
                )}
              >
                <it.icono className="size-5" />
              </span>
              <span className={sel ? 'text-primary' : 'text-muted-foreground'}>{it.etiqueta}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
