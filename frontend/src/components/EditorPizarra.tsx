/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, FunctionSquare, Network, Trash2, Type } from 'lucide-react'
import { CampoFormula } from '@/components/CampoFormula'
import { FilasDeRelaciones } from '@/components/MapaConceptual'
import { Button } from '@/components/ui/button'
import { aSegmentos, deSegmentos, segmentoNuevo, type Segmento } from '@/lib/pizarra'

const NOMBRE = { texto: 'Texto', formula: 'Fórmula', diagrama: 'Diagrama', codigo: 'Diagrama (no editable)' } as const

const AREA =
  'min-h-20 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-base outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 desk:text-sm'

/**
 * Corregir lo que leyó la IA de una foto de la pizarra **sin conocer LaTeX ni Mermaid**: el texto se edita como texto, cada
 * fórmula en un campo de matemática visual (con teclado en pantalla) y cada diagrama como una tabla de flechas. El
 * resultado se devuelve como el texto que guarda la app.
 */
export function EditorPizarra({ texto, onCambio }: { texto: string; onCambio: (nuevo: string) => void }) {
  const [segmentos, setSegmentos] = useState<Segmento[]>(() => aSegmentos(texto))
  const [anuncio, setAnuncio] = useState('') // lo lee el lector de pantalla: mover o quitar una parte no cambia nada que se oiga
  const [recienAgregado, setRecienAgregado] = useState<number | null>(null)
  const raiz = useRef<HTMLDivElement>(null)
  // A dónde debe ir el foco después de un cambio (si no, se pierde al desaparecer o moverse el botón que se tocó).
  const foco = useRef<{ id: number; que: 'campo' | 'subir' | 'bajar' } | 'agregar' | null>(null)

  useEffect(() => {
    const destino = foco.current
    foco.current = null
    if (!destino || !raiz.current) return
    if (destino === 'agregar') raiz.current.querySelector<HTMLElement>('[data-agregar]')?.focus()
    else {
      const parte = raiz.current.querySelector(`[data-segmento="${destino.id}"]`)
      const botones = parte?.querySelectorAll<HTMLButtonElement>('[data-mover]')
      // Tras mover: el mismo botón y, si ya no se puede seguir en esa dirección (llegó al borde), el otro; si no, el campo.
      const [subir, bajar] = [botones?.[0], botones?.[1]]
      const preferidos = destino.que === 'subir' ? [subir, bajar] : destino.que === 'bajar' ? [bajar, subir] : []
      const elegido = preferidos.find((b) => b && !b.disabled) ?? parte?.querySelector<HTMLElement>('textarea, math-field, input:not([type=checkbox])')
      elegido?.focus()
    }
  })

  const poner = useCallback(
    (siguiente: Segmento[]) => {
      setSegmentos(siguiente)
      onCambio(deSegmentos(siguiente))
    },
    [onCambio],
  )
  const cambiar = (id: number, cambio: Partial<Segmento>) => poner(segmentos.map((s) => (s.id === id ? ({ ...s, ...cambio } as Segmento) : s)))
  const mover = (i: number, d: -1 | 1) => {
    const copia = [...segmentos]
    ;[copia[i], copia[i + d]] = [copia[i + d], copia[i]]
    foco.current = { id: segmentos[i].id, que: d < 0 ? 'subir' : 'bajar' }
    setAnuncio(`Parte movida: ahora es la ${i + d + 1} de ${copia.length}.`)
    poner(copia)
  }
  const quitar = (id: number) => {
    foco.current = 'agregar'
    setAnuncio('Parte quitada.')
    poner(segmentos.filter((x) => x.id !== id))
  }
  const agregar = (nueva: Segmento, nombre: string) => {
    foco.current = { id: nueva.id, que: 'campo' }
    setRecienAgregado(nueva.id)
    setAnuncio(`Se agregó ${nombre}.`)
    poner([...segmentos, nueva])
  }

  return (
    <div ref={raiz} className="space-y-3">
      <p role="status" aria-live="polite" className="sr-only">{anuncio}</p>
      {segmentos.length === 0 && <p className="text-sm text-muted-foreground">Esta foto no tiene nada todavía. Agrega texto, una fórmula o un diagrama.</p>}
      {segmentos.map((s, i) => (
        <div key={s.id} data-segmento={s.id} role="group" aria-label={`Parte ${i + 1} de ${segmentos.length}: ${NOMBRE[s.tipo]}`} className="space-y-2 rounded-xl border bg-card p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-muted-foreground">{NOMBRE[s.tipo]}</p>
            <div className="flex">
              <Button type="button" variant="ghost" size="icon-lg" aria-label="Subir esta parte" data-mover disabled={i === 0} onClick={() => mover(i, -1)}>
                <ArrowUp />
              </Button>
              <Button type="button" variant="ghost" size="icon-lg" aria-label="Bajar esta parte" data-mover disabled={i === segmentos.length - 1} onClick={() => mover(i, 1)}>
                <ArrowDown />
              </Button>
              <Button type="button" variant="ghost" size="icon-lg" aria-label="Quitar esta parte" onClick={() => quitar(s.id)}>
                <Trash2 />
              </Button>
            </div>
          </div>

          {s.tipo === 'texto' && <textarea aria-label="Texto" rows={3} maxLength={4000} value={s.valor} onChange={(e) => cambiar(s.id, { valor: e.target.value })} className={AREA} />}

          {s.tipo === 'formula' && (
            <>
              <CampoFormula enfocar={recienAgregado === s.id} etiqueta="Fórmula" valor={s.tex} onCambio={(tex) => cambiar(s.id, { tex })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={s.bloque} onChange={(e) => cambiar(s.id, { bloque: e.target.checked })} className="size-4" />
                En su propia línea, centrada
              </label>
            </>
          )}

          {s.tipo === 'diagrama' && <FilasDeRelaciones filas={s.relaciones} onCambio={(relaciones) => cambiar(s.id, { relaciones })} />}

          {s.tipo === 'codigo' && (
            <p className="text-sm text-muted-foreground">
              Este diagrama tiene una forma que no se puede mostrar como tabla, así que no se puede corregir aquí. Puedes quitarlo y agregarlo de nuevo como diagrama.
            </p>
          )}
        </div>
      ))}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" className="h-10 desk:h-8" data-agregar onClick={() => agregar(segmentoNuevo.texto(), 'un texto')}>
          <Type /> Agregar texto
        </Button>
        <Button type="button" variant="outline" className="h-10 desk:h-8" onClick={() => agregar(segmentoNuevo.formula(), 'una fórmula')}>
          <FunctionSquare /> Agregar fórmula
        </Button>
        <Button type="button" variant="outline" className="h-10 desk:h-8" onClick={() => agregar(segmentoNuevo.diagrama(), 'un diagrama')}>
          <Network /> Agregar diagrama
        </Button>
      </div>
    </div>
  )
}
