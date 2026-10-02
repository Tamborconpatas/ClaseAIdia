/**
 * Arma el código Mermaid de un mapa conceptual a partir de sus relaciones. El código se escribe aquí y no lo escribe
 * ningún modelo: los nombres de los nodos son N1, N2... y los textos van entre comillas con lo que Mermaid no tolera
 * sustituido, así que ninguna relación (venga de la IA o la escriba el profesor) puede romper la sintaxis.
 */
export interface Relacion {
  de: string
  relacion: string
  a: string
}

/** Texto seguro para ir entre comillas dobles en Mermaid. */
function texto(valor: string): string {
  return valor
    // oxlint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]/g, ' ') // sin saltos de línea ni caracteres de control
    .replace(/"/g, "'") // Mermaid no deja comillas dobles dentro de un texto entre comillas; "#quot;" se dibujaría tal cual
    .replace(/</g, '#lt;')
    .replace(/>/g, '#gt;')
    .replace(/\s+/g, ' ')
    .trim()
}

export function aMermaid(relaciones: Relacion[]): string {
  const ids = new Map<string, string>()
  const nodos: string[] = []
  const nodo = (nombre: string) => {
    const clave = nombre.trim().toLocaleLowerCase('es')
    let id = ids.get(clave)
    if (!id) {
      id = `N${ids.size + 1}`
      ids.set(clave, id)
      nodos.push(`${id}["${texto(nombre)}"]`)
    }
    return id
  }
  const flechas = relaciones
    .filter((r) => r.de.trim() && r.a.trim())
    .map((r) => {
      const origen = nodo(r.de)
      const destino = nodo(r.a)
      const rotulo = texto(r.relacion)
      return rotulo ? `${origen} -->|"${rotulo}"| ${destino}` : `${origen} --> ${destino}`
    })
  return ['flowchart TD', ...nodos.map((n) => `  ${n}`), ...flechas.map((f) => `  ${f}`)].join('\n')
}
