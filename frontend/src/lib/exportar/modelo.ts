import type { ClaseDetalle } from '@/lib/api'
import { agrupar, partir, type Trozo } from '@/lib/formulas'
import { fechaCorta, hhmm } from '@/lib/horario'
import { aMermaid } from '@/lib/mapa'

/**
 * Lo que se descarga de una clase, en un solo modelo que usan el PDF (vista de impresión) y el Word, para que los dos
 * lleven lo mismo en el mismo orden. No incluye la transcripción completa: es larga y es el registro, no el material.
 */
export type Bloque =
  | { t: 'titulo'; texto: string }
  | { t: 'subtitulo'; texto: string }
  | { t: 'aviso'; texto: string }
  | { t: 'seccion'; texto: string; nota?: string }
  | { t: 'parrafo'; trozos: Trozo[] } // texto y fórmulas en línea
  | { t: 'vinetas'; items: string[] }
  | { t: 'formula'; tex: string }
  | { t: 'diagrama'; codigo: string; descripcion: string }
  | { t: 'tarjeta'; pregunta: string; respuesta: string }
  | { t: 'nota'; texto: string }

const parrafos = (texto: string): Bloque[] =>
  texto
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => ({ t: 'parrafo', trozos: [{ tipo: 'texto', valor: p }] }))

/** Un texto que puede traer LaTeX y diagramas (lo leído de la pizarra) como bloques. */
function conFormulas(texto: string): Bloque[] {
  const bloques: Bloque[] = []
  for (const grupo of agrupar(partir(texto))) {
    const t = grupo[0]
    if (t.tipo === 'mermaid') bloques.push({ t: 'diagrama', codigo: t.valor, descripcion: 'Diagrama de la pizarra' })
    else if (t.tipo === 'formula' && t.bloque) bloques.push({ t: 'formula', tex: t.valor })
    else {
      // Los saltos de línea que quedan pegados a una fórmula o a un diagrama no son un párrafo.
      const trozos = grupo.map((g, i): Trozo => {
        if (g.tipo !== 'texto') return g
        let valor = g.valor
        if (i === 0) valor = valor.trimStart()
        if (i === grupo.length - 1) valor = valor.trimEnd()
        return { ...g, valor }
      })
      if (trozos.some((g) => g.tipo !== 'texto' || g.valor !== '')) bloques.push({ t: 'parrafo', trozos })
    }
  }
  return bloques
}

export function construirModelo(c: ClaseDetalle): Bloque[] {
  const k = c.contenido
  const bloques: Bloque[] = [
    { t: 'titulo', texto: c.asignatura ?? 'Clase' },
    { t: 'subtitulo', texto: [c.curso_nombre, fechaCorta(c.fecha), `${hhmm(c.hora_inicio)}–${hhmm(c.hora_fin)}`, c.sala].filter(Boolean).join(' · ') },
  ]
  if (!k) return bloques
  if (c.estado === 'provisoria') {
    bloques.push({ t: 'aviso', texto: 'Material sin revisar: se generó automáticamente y el profesor todavía no lo ha revisado, así que puede tener errores.' })
  }
  if (k.resumen?.trim()) bloques.push({ t: 'seccion', texto: 'Resumen' }, ...parrafos(k.resumen))
  const puntos = (k.puntos_clave ?? '').split('\n').map((l) => l.replace(/^[-•*]\s*/, '').trim()).filter(Boolean)
  if (puntos.length > 0) bloques.push({ t: 'seccion', texto: 'Puntos clave' }, { t: 'vinetas', items: puntos })
  if (k.hoja_repaso?.trim()) bloques.push({ t: 'seccion', texto: 'Hoja de repaso' }, ...parrafos(k.hoja_repaso))
  if (k.mapa.length > 0) {
    bloques.push(
      { t: 'seccion', texto: 'Mapa conceptual', nota: 'Generado automáticamente a partir de la clase: puede tener errores.' },
      { t: 'diagrama', codigo: aMermaid(k.mapa), descripcion: `Mapa conceptual con ${k.mapa.length} relaciones entre conceptos` },
      { t: 'vinetas', items: k.mapa.map((r) => `${r.de} ${r.relacion ? `— ${r.relacion} →` : '→'} ${r.a}`) },
    )
  }
  if (k.tarjetas.length > 0) {
    bloques.push(
      { t: 'seccion', texto: 'Tarjetas de estudio', nota: 'Intenta responder antes de leer la respuesta: recordar activamente es lo que más ayuda a aprender.' },
      ...k.tarjetas.map((t): Bloque => ({ t: 'tarjeta', pregunta: t.pregunta, respuesta: t.respuesta })),
    )
  }
  if (k.pizarra.length > 0) {
    bloques.push({ t: 'seccion', texto: 'De la pizarra', nota: 'Lectura automática de fotos de la pizarra: puede tener errores, sobre todo en cifras. Contrástala con tus apuntes.' })
    for (const f of k.pizarra) bloques.push({ t: 'nota', texto: `Foto a los ${Math.floor(f.segundo / 60)} min de la clase` }, ...conFormulas(f.texto))
  }
  return bloques
}

/** Nombre de archivo seguro (sin caracteres que Windows o el teléfono no aceptan). */
export function nombreDeArchivo(c: ClaseDetalle, extension: string): string {
  // oxlint-disable-next-line no-control-regex
  const base = `${c.asignatura ?? 'Clase'} ${c.fecha}`.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '').replace(/\s+/g, ' ').trim()
  return `${base || 'Clase'}.${extension}`
}
