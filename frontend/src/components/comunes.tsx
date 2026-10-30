/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import type { ComponentProps, ReactNode } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, type LucideIcon } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { registrarToque } from '@/lib/mensajeSecreto'
import { cn } from '@/lib/utils'

export function Logo({ className, claro = false }: { className?: string; claro?: boolean }) {
  return (
    <div className={cn('flex items-center gap-2.5', className)} onClick={() => registrarToque()}>
      <img src="/favicon.svg" alt="" className="size-9 rounded-xl" />
      <span className={cn('text-lg font-semibold tracking-tight', claro && 'text-white')}>ClaseAIdia</span>
    </div>
  )
}

interface CampoProps extends ComponentProps<typeof Input> {
  etiqueta: string
  error?: string | null
  ayuda?: string
}

/** Etiqueta + campo + error. En teléfono el campo mide 44 px (zona táctil cómoda); en PC, 36. */
export function Campo({ etiqueta, error, ayuda, id, className, ...props }: CampoProps) {
  const campoId = id ?? `campo-${etiqueta}`
  return (
    <div className="space-y-1.5">
      <Label htmlFor={campoId}>{etiqueta}</Label>
      <Input
        id={campoId}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${campoId}-e` : undefined}
        className={cn('h-11 text-base desk:h-9 desk:text-sm', className)}
        {...props}
      />
      {error ? (
        <p id={`${campoId}-e`} className="text-sm text-destructive">
          {error}
        </p>
      ) : ayuda ? (
        <p className="text-xs text-muted-foreground">{ayuda}</p>
      ) : null}
    </div>
  )
}

export function ErrorForm({ mensaje }: { mensaje?: string | null }) {
  if (!mensaje) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <span>{mensaje}</span>
    </div>
  )
}

/** Una fila de «lista de revisión»: ícono verde si está en orden, ámbar si falta algo (y se anuncia con texto, no solo con color). */
export function Requisito({ ok, titulo, children }: { ok: boolean | null; titulo: string; children: ReactNode }) {
  const Icono = ok ? CheckCircle2 : AlertTriangle
  return (
    <li className="flex items-start gap-2.5">
      <Icono className={cn('mt-0.5 size-4 shrink-0', ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400')} aria-hidden />
      <div className="min-w-0 flex-1 text-sm leading-relaxed">
        <p className="font-medium">
          {titulo}
          <span className="sr-only">: {ok ? 'en orden' : 'falta revisar'}</span>
        </p>
        <div className="text-muted-foreground [overflow-wrap:anywhere]">{children}</div>
      </div>
    </li>
  )
}

export function Cargando({ texto = 'Cargando…' }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground" role="status">
      <Loader2 className="size-4 animate-spin" /> {texto}
    </div>
  )
}

export function Vacio({
  icono: Icono,
  titulo,
  children,
  accion,
}: {
  icono: LucideIcon
  titulo: string
  children?: ReactNode
  accion?: ReactNode
}) {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-3 py-14 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground">
        <Icono className="size-7" />
      </div>
      <h2 className="text-lg font-semibold">{titulo}</h2>
      {children && <p className="text-sm text-muted-foreground">{children}</p>}
      {accion}
    </div>
  )
}
