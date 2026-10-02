import { partir } from '@/lib/formulas'
import { aMermaid, type Relacion } from '@/lib/mapa'

/**
 * Lo leído de una foto de la pizarra como piezas que el profesor puede editar sin saber LaTeX ni Mermaid: texto, fórmulas
 * (que edita en un campo de matemática visual) y diagramas (que edita como una tabla de flechas). `aSegmentos` y
 * `deSegmentos` pasan del texto guardado a esas piezas y de vuelta.
 */
export type SegTexto = { id: number; tipo: 'texto'; valor: string }
export type SegFormula = { id: number; tipo: 'formula'; tex: string; bloque: boolean }
export type SegDiagrama = { id: number; tipo: 'diagrama'; relaciones: Relacion[] }
export type SegCodigo = { id: number; tipo: 'codigo'; codigo: string } // un diagrama que no se puede mostrar como tabla: solo se puede quitar
export type Segmento = SegTexto | SegFormula | SegDiagrama | SegCodigo

let contador = 0
const nuevoId = () => ++contador

export const segmentoNuevo = {
  texto: (): SegTexto => ({ id: nuevoId(), tipo: 'texto', valor: '' }),
  formula: (): SegFormula => ({ id: nuevoId(), tipo: 'formula', tex: '', bloque: true }),
  diagrama: (): SegDiagrama => ({ id: nuevoId(), tipo: 'diagrama', relaciones: [{ de: '', relacion: '', a: '' }] }),
}

const NODO = String.raw`(\w+)(?:\[(?:"([^"]*)"|([^\]]*))\])?`
const FLECHA = new RegExp(String.raw`^${NODO}\s*(?:-->|---|==>|-\.->)\s*(?:\|(?:"([^"]*)"|([^|]*))\|\s*)?${NODO}$`)
const DECLARACION = new RegExp(String.raw`^${NODO}$`)
const entidades = (t: string) => t.replaceAll('#lt;', '<').replaceAll('#gt;', '>').replaceAll('#quot;', "'").trim()

/**
 * El código Mermaid de un diagrama simple (el que arma esta app, o uno de flechas «A[texto] --> B[texto]») como relaciones,
 * o null si tiene algo que la tabla no puede representar (subgrafos, estilos, otro tipo de diagrama...).
 */
export function deMermaid(codigo: string): Relacion[] | null {
  const lineas = codigo.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lineas.length < 2 || !/^(flowchart|graph)\s+(TD|TB|LR|RL|BT)$/i.test(lineas[0])) return null
  const texto = new Map<string, string>()
  const relaciones: Relacion[] = []
  const nombre = (id: string, comillas?: string, plano?: string) => {
    const dado = comillas ?? plano
    if (dado !== undefined && dado.trim()) texto.set(id, entidades(dado))
    return id
  }
  const flechas: [string, string, string][] = []
  for (const l of lineas.slice(1)) {
    const f = FLECHA.exec(l)
    if (f) {
      const origen = nombre(f[1], f[2], f[3])
      const destino = nombre(f[6], f[7], f[8])
      flechas.push([origen, entidades(f[4] ?? f[5] ?? ''), destino])
      continue
    }
    const d = DECLARACION.exec(l)
    if (d && (d[2] !== undefined || d[3] !== undefined)) {
      nombre(d[1], d[2], d[3])
      continue
    }
    return null
  }
  for (const [origen, relacion, destino] of flechas) relaciones.push({ de: texto.get(origen) ?? origen, relacion, a: texto.get(destino) ?? destino })
  return relaciones.length > 0 ? relaciones : null
}

export function aSegmentos(texto: string): Segmento[] {
  const segmentos: Segmento[] = []
  for (const t of partir(texto)) {
    if (t.tipo === 'texto') segmentos.push({ id: nuevoId(), tipo: 'texto', valor: t.valor })
    else if (t.tipo === 'formula') segmentos.push({ id: nuevoId(), tipo: 'formula', tex: t.valor, bloque: t.bloque })
    else {
      const relaciones = deMermaid(t.valor)
      segmentos.push(relaciones ? { id: nuevoId(), tipo: 'diagrama', relaciones } : { id: nuevoId(), tipo: 'codigo', codigo: t.valor })
    }
  }
  // El salto de línea que separa un texto de una fórmula o diagrama en bloque no es parte del texto (`deSegmentos` lo vuelve a poner).
  const esBloque = (s: Segmento | undefined) => s !== undefined && (s.tipo === 'diagrama' || s.tipo === 'codigo' || (s.tipo === 'formula' && s.bloque))
  return segmentos
    .map((s, i) => {
      if (s.tipo !== 'texto') return s
      let valor = s.valor
      if (esBloque(segmentos[i - 1])) valor = valor.replace(/^\n+/, '')
      if (esBloque(segmentos[i + 1])) valor = valor.replace(/\n+$/, '')
      return { ...s, valor }
    })
    .filter((s) => !(s.tipo === 'texto' && s.valor === '')) // el salto de línea entre dos bloques no es un texto que editar
}

/** Vuelve al texto guardado. Lo que quedó vacío se descarta; las fórmulas y diagramas en bloque quedan en su propia línea. */
export function deSegmentos(segmentos: Segmento[]): string {
  const piezas: { texto: string; enBloque: boolean }[] = []
  for (const s of segmentos) {
    if (s.tipo === 'texto') {
      if (s.valor.trim()) piezas.push({ texto: s.valor.replaceAll('$', '\\$'), enBloque: false }) // un $ del texto no debe leerse como fórmula
    } else if (s.tipo === 'formula') {
      if (s.tex.trim()) piezas.push({ texto: s.bloque ? `$$${s.tex.trim()}$$` : `$${s.tex.trim()}$`, enBloque: s.bloque })
    } else if (s.tipo === 'diagrama') {
      const completas = s.relaciones.filter((r) => r.de.trim() && r.a.trim())
      if (completas.length > 0) piezas.push({ texto: '```mermaid\n' + aMermaid(completas) + '\n```', enBloque: true })
    } else piezas.push({ texto: '```mermaid\n' + s.codigo + '\n```', enBloque: true })
  }
  let salida = ''
  for (const [i, p] of piezas.entries()) {
    const antes = piezas[i - 1]
    const separar = i > 0 && (p.enBloque || antes.enBloque) && !salida.endsWith('\n') && !p.texto.startsWith('\n')
    salida += (separar ? '\n' : '') + p.texto
  }
  return salida.trim()
}
