/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
/**
 * Parte un texto que puede traer matemática en LaTeX (lo que lee la IA de la pizarra) en trozos: texto normal, fórmulas
 * y diagramas Mermaid. Solo reconoce, no dibuja (eso lo hacen los componentes).
 *
 * El signo `$` también es "pesos" ($5.920), así que el `$...$` en línea sigue la regla de pandoc: el de apertura no va
 * seguido de un espacio, el de cierre no va precedido de uno ni seguido de un dígito. `\$` es un signo de pesos literal.
 * Lo que no calza con nada se deja como texto: nunca se pierde contenido.
 */
export type Trozo =
  | { tipo: 'texto'; valor: string }
  | { tipo: 'formula'; valor: string; bloque: boolean }
  | { tipo: 'mermaid'; valor: string }

const PATRON = new RegExp(
  [
    String.raw`\x60\x60\x60mermaid[ \t]*\r?\n(?<mermaid>[\s\S]*?)\x60\x60\x60`, // ```mermaid ... ```
    String.raw`\x60\x60\x60(?:latex|tex|math)?[ \t]*\r?\n(?<cerca>[\s\S]*?)\x60\x60\x60`, // ``` ... ``` (el modelo a veces envuelve todo)
    String.raw`\$\$(?<doble>[\s\S]+?)\$\$`, // $$ ... $$
    String.raw`\\\[(?<corchete>[\s\S]+?)\\\]`, // \[ ... \]
    String.raw`\\\((?<parentesis>[\s\S]+?)\\\)`, // \( ... \)
    String.raw`(?<entorno>\\begin\{(?<nombre>[A-Za-z]+\*?)\}[\s\S]*?\\end\{\k<nombre>\})`, // \begin{aligned} ... \end{aligned} suelto
    String.raw`(?<![\\$])\$(?!\s)(?<simple>(?:\\.|[^$\\\n])+?)(?<!\s)\$(?!\d)`, // $ ... $ en línea
    String.raw`\\\$(?<peso>)`, // \$ = signo de pesos
  ].join('|'),
  'g',
)

/** KaTeX no tiene `tabular` (es de texto); `array` es lo equivalente dentro de una fórmula. */
function arreglarEntorno(tex: string): string {
  return tex.replace(/\\(begin|end)\{tabular\}/g, '\\$1{array}')
}

function agregarTexto(trozos: Trozo[], valor: string) {
  if (!valor) return
  const ultimo = trozos[trozos.length - 1]
  if (ultimo?.tipo === 'texto') ultimo.valor += valor
  else trozos.push({ tipo: 'texto', valor })
}

export function partir(texto: string): Trozo[] {
  const trozos: Trozo[] = []
  let desde = 0
  for (const m of texto.matchAll(PATRON)) {
    agregarTexto(trozos, texto.slice(desde, m.index))
    desde = m.index + m[0].length
    const g = m.groups!
    if (g.mermaid !== undefined) trozos.push({ tipo: 'mermaid', valor: g.mermaid.trim() })
    else if (g.cerca !== undefined) {
      for (const t of partir(g.cerca.trim())) {
        if (t.tipo === 'texto') agregarTexto(trozos, t.valor)
        else trozos.push(t)
      }
    }
    else if (g.doble !== undefined || g.corchete !== undefined) trozos.push({ tipo: 'formula', valor: arreglarEntorno((g.doble ?? g.corchete).trim()), bloque: true })
    else if (g.entorno !== undefined) trozos.push({ tipo: 'formula', valor: arreglarEntorno(g.entorno), bloque: true })
    else if (g.parentesis !== undefined || g.simple !== undefined) trozos.push({ tipo: 'formula', valor: (g.parentesis ?? g.simple).trim(), bloque: false })
    else agregarTexto(trozos, '$') // \$
  }
  agregarTexto(trozos, texto.slice(desde))
  return trozos
}

/**
 * Junta lo que va en línea (texto y fórmulas chicas) en un solo párrafo; las fórmulas en bloque y los diagramas cortan el
 * párrafo y quedan solos, en el mismo orden del original.
 */
export function agrupar(trozos: Trozo[]): Trozo[][] {
  const grupos: Trozo[][] = []
  for (const t of trozos) {
    const enLinea = t.tipo === 'texto' || (t.tipo === 'formula' && !t.bloque)
    const ultimo = grupos[grupos.length - 1]
    const ultimoEsParrafo = ultimo !== undefined && (ultimo[0].tipo === 'texto' || (ultimo[0].tipo === 'formula' && !ultimo[0].bloque))
    if (enLinea && ultimoEsParrafo) ultimo.push(t)
    else grupos.push([t])
  }
  return grupos
}
