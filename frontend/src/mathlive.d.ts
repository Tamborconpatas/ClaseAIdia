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
