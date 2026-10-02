import { useEffect, useRef, useState } from 'react'
import type { MathfieldElement } from 'mathlive'

// MathLive (el editor de matemática visual) y sus tipografías se bajan solo cuando se abre una fórmula para corregir.
let mathlive: Promise<void> | undefined
const cargarMathlive = () =>
  (mathlive ??= Promise.all([import('mathlive'), import('mathlive/fonts.css')]).then(([m]) => {
    m.MathfieldElement.fontsDirectory = null // las tipografías ya van en el paquete (fonts.css): no se piden a ninguna dirección
    m.MathfieldElement.soundsDirectory = null // sin sonidos de teclas
  }))

/**
 * Una fórmula que se edita como se ve (fracciones, raíces, potencias), con teclado de matemática en pantalla en el
 * teléfono: el profesor no escribe ni ve LaTeX. `valor` y `onCambio` hablan en LaTeX porque es lo que guarda la app.
 */
export function CampoFormula({ valor, onCambio, etiqueta, enfocar = false }: { valor: string; onCambio: (tex: string) => void; etiqueta: string; enfocar?: boolean }) {
  const ref = useRef<MathfieldElement>(null)
  const [listo, setListo] = useState(false)

  useEffect(() => {
    let vivo = true
    void cargarMathlive().then(() => vivo && setListo(true))
    return () => {
      vivo = false
    }
  }, [])

  useEffect(() => {
    const campo = ref.current
    if (campo && listo && campo.value !== valor) campo.value = valor
  }, [valor, listo])

  // Una fórmula recién agregada recibe el foco apenas el editor termina de cargar.
  useEffect(() => {
    if (listo && enfocar) ref.current?.focus()
  }, [listo, enfocar])

  useEffect(() => {
    const campo = ref.current
    if (!campo || !listo) return
    const alEscribir = () => onCambio(campo.value)
    campo.addEventListener('input', alEscribir)
    return () => campo.removeEventListener('input', alEscribir)
  }, [listo, onCambio])

  if (!listo) return <p className="text-sm text-muted-foreground">Preparando el editor de fórmulas…</p>
  return (
    <math-field
      ref={ref}
      aria-label={etiqueta}
      math-virtual-keyboard-policy="auto"
      className="block w-full rounded-lg border border-input bg-background px-3 py-2 text-xl"
    >
      {valor}
    </math-field>
  )
}
