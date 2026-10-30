/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useState, type ReactNode } from 'react'
import { Check, Copy, KeyRound, Loader2 } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { api, type ResetPin } from '@/lib/api'

const hora = (iso: string) => new Date(iso).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })

const TEXTOS = {
  pin: {
    ruta: 'reset-pin',
    boton: 'Resetear PIN',
    confirmar: (n: string) => `¿Resetear el PIN de ${n}? Dejará de entrar con el PIN actual hasta que elija uno nuevo con el código.`,
    como: 'con él elige su PIN nuevo en «Olvidé mi PIN»',
  },
  password: {
    ruta: 'reset-password',
    boton: 'Resetear contraseña',
    confirmar: (n: string) => `¿Resetear la contraseña de ${n}? Dejará de entrar con la actual hasta que elija una nueva con el código.`,
    como: 'con él elige su contraseña nueva en «Olvidé mi contraseña»',
  },
}

interface Props {
  usuarioId: number
  nombre: string
  /** Lo que se muestra a la izquierda (nombre, RUT, etiquetas). */
  info: ReactNode
  /** pin = alumnos; password = personal. */
  tipo: 'pin' | 'password'
  /** Falso para no ofrecer el reseteo (p. ej. en la propia cuenta). */
  puedeResetear?: boolean
  /** Otra acción de la fila (p. ej. desactivar), junto al botón de reseteo. */
  accion?: ReactNode
  /** Contenido bajo la fila (p. ej. la confirmación de esa acción). */
  bajo?: ReactNode
}

/**
 * Una fila con su botón de reseteo: pide confirmación, entrega un código de un solo uso con su vencimiento
 * y las instrucciones para dárselo en persona.
 */
export function FilaConReset({ usuarioId, nombre, info, tipo, puedeResetear = true, accion, bajo }: Props) {
  const t = TEXTOS[tipo]
  const [paso, setPaso] = useState<'inicio' | 'confirmando' | 'enviando'>('inicio')
  const [resultado, setResultado] = useState<ResetPin | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copiado, setCopiado] = useState(false)

  const resetear = async () => {
    setPaso('enviando')
    setError(null)
    try {
      setResultado(await api<ResetPin>(`/usuarios/${usuarioId}/${t.ruta}`, { metodo: 'POST' }))
    } catch (e) {
      setError((e as Error).message)
    }
    setPaso('inicio')
  }
  const copiar = async () => {
    if (!resultado) return
    try {
      await navigator.clipboard.writeText(resultado.codigo)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1800)
    } catch {
      /* sin permiso de portapapeles: el código está a la vista */
    }
  }

  return (
    <li className="space-y-2 p-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-40 flex-1">{info}</div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {puedeResetear && paso === 'inicio' && !resultado && (
            <Button variant="outline" className="h-10 desk:h-8" onClick={() => setPaso('confirmando')} aria-label={`${t.boton} de ${nombre}`}>
              <KeyRound /> {t.boton}
            </Button>
          )}
          {accion}
        </div>
      </div>
      {bajo}

      {paso !== 'inicio' && (
        <div className="space-y-2 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
          <p>{t.confirmar(nombre)}</p>
          <div className="flex gap-2">
            <Button className="h-10 flex-1 desk:h-8 desk:flex-none" disabled={paso === 'enviando'} onClick={resetear}>
              {paso === 'enviando' && <Loader2 className="animate-spin" />} Sí, resetear
            </Button>
            <Button variant="ghost" className="h-10 desk:h-8" onClick={() => setPaso('inicio')}>
              No
            </Button>
          </div>
        </div>
      )}

      {resultado && (
        <div className="space-y-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 p-3.5 text-emerald-950 dark:text-emerald-100 ring-1 ring-emerald-200 dark:ring-emerald-800" role="status">
          <p className="text-sm">
            Código para {nombre}: <strong className="font-mono text-xl tracking-[0.2em]">{resultado.codigo}</strong>
          </p>
          <p className="text-xs">
            Sirve una sola vez y vence a las <strong>{hora(resultado.vence)}</strong>. Entrégaselo en persona: {t.como}.
          </p>
          <div className="flex gap-2">
            <Button variant="outline" className="h-9 desk:h-8" onClick={copiar}>
              {copiado ? <Check /> : <Copy />} {copiado ? 'Copiado' : 'Copiar código'}
            </Button>
            <Button variant="ghost" className="h-9 desk:h-8" onClick={() => setResultado(null)}>
              Listo
            </Button>
          </div>
        </div>
      )}
      <ErrorForm mensaje={error} />
    </li>
  )
}
