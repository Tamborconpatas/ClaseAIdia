/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import type { MathfieldElement } from 'mathlive'
import type { DetailedHTMLProps, HTMLAttributes } from 'react'

// `<math-field>` es un elemento propio del navegador (MathLive): se declara para poder usarlo en JSX.
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'math-field': DetailedHTMLProps<HTMLAttributes<MathfieldElement>, MathfieldElement> & { 'math-virtual-keyboard-policy'?: string }
    }
  }
}
