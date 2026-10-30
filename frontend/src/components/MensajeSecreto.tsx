/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { cargarMensaje, cerrarMensaje, registrarTecla, useMensajeAbierto } from '@/lib/mensajeSecreto'

const esCampo = (el: EventTarget | null) => el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))

/** Ventana con el mensaje escondido. Va una sola vez en la raíz; escucha el código Konami en todo el sitio. */
export function MensajeSecreto() {
  const abierto = useMensajeAbierto()
  const ref = useRef<HTMLDialogElement>(null)
  const [texto, setTexto] = useState('')

  useEffect(() => {
    if (abierto) void cargarMensaje().then(setTexto)
  }, [abierto])

  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || esCampo(e.target)) return
      registrarTecla(e.key)
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [])

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (abierto && !d.open) {
      if (typeof d.showModal === 'function') d.showModal() // modal nativo: atrapa el foco, Esc cierra y el foco vuelve a donde estaba
      else d.setAttribute('open', '')
    } else if (!abierto && d.open) {
      if (typeof d.close === 'function') d.close()
      else d.removeAttribute('open')
    }
  }, [abierto])

  return (
    <dialog
      ref={ref}
      aria-labelledby="mensaje-titulo"
      onClose={cerrarMensaje}
      onClick={(e) => e.target === e.currentTarget && cerrarMensaje()}
      className="m-auto w-[min(92vw,34rem)] max-h-[85dvh] flex-col overflow-hidden rounded-2xl border bg-card p-6 text-card-foreground shadow-xl backdrop:bg-black/60 open:flex"
    >
      <h2 id="mensaje-titulo" className="text-lg font-semibold tracking-tight">
        Un mensaje para ti
      </h2>
      <p className="mt-3 min-h-0 overflow-y-auto text-sm leading-relaxed">{texto || 'Cargando…'}</p>
      <div className="mt-5 flex shrink-0 justify-end">
        <Button autoFocus onClick={cerrarMensaje}>
          Cerrar
        </Button>
      </div>
    </dialog>
  )
}
