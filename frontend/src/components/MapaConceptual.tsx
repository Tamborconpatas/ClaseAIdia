/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useMemo, useState } from 'react'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { Mermaid } from '@/components/Mermaid'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/lib/api'
import { aMermaid, type Relacion } from '@/lib/mapa'

const MAX_RELACIONES = 30

/** El mapa dibujado, con su lista de relaciones como alternativa de texto (lectores de pantalla, copiar y pegar). */
export function MapaDibujado({ relaciones, nombre = 'Mapa conceptual' }: { relaciones: Relacion[]; nombre?: string }) {
  const codigo = useMemo(() => aMermaid(relaciones), [relaciones])
  return (
    <div className="space-y-2">
      <Mermaid codigo={codigo} descripcion={`${nombre} con ${relaciones.length} relaciones entre conceptos; la lista de abajo lo cuenta en texto`} />
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">Ver como lista</summary>
        <ul className="mt-2 space-y-1">
          {relaciones.map((r, i) => (
            <li key={i}>
              <strong>{r.de}</strong> {r.relacion ? `— ${r.relacion} →` : '→'} <strong>{r.a}</strong>
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}

/** La tabla de flechas («de» —relación→ «a») que editan el mapa de la clase y los diagramas de la pizarra. */
export function FilasDeRelaciones({ filas, onCambio }: { filas: Relacion[]; onCambio: (filas: Relacion[]) => void }) {
  const cambiar = (i: number, campo: keyof Relacion, valor: string) => onCambio(filas.map((f, j) => (j === i ? { ...f, [campo]: valor } : f)))
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Cada fila es una flecha. Repite el mismo nombre para que dos flechas lleguen al mismo concepto.</p>
      {filas.map((f, i) => (
        <div key={i} className="space-y-2 rounded-xl bg-muted/50 p-3">
          <div className="flex items-start gap-2">
            <div className="grid min-w-0 flex-1 gap-2 desk:grid-cols-3">
              <Input aria-label={`Concepto de origen de la relación ${i + 1}`} placeholder="Concepto de origen" maxLength={60} value={f.de} onChange={(e) => cambiar(i, 'de', e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
              <Input aria-label={`Verbo o frase de la relación ${i + 1}`} placeholder="se relaciona con (opcional)" maxLength={40} value={f.relacion} onChange={(e) => cambiar(i, 'relacion', e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
              <Input aria-label={`Concepto de destino de la relación ${i + 1}`} placeholder="Concepto de destino" maxLength={60} value={f.a} onChange={(e) => cambiar(i, 'a', e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
            </div>
            <Button type="button" variant="ghost" size="icon-lg" aria-label={`Quitar la relación ${i + 1}`} onClick={() => onCambio(filas.filter((_, j) => j !== i))}>
              <Trash2 />
            </Button>
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" className="h-10 desk:h-8" disabled={filas.length >= MAX_RELACIONES} onClick={() => onCambio([...filas, { de: '', relacion: '', a: '' }])}>
        <Plus /> Agregar relación
      </Button>
    </div>
  )
}

/**
 * El profesor arma o corrige el mapa como una tabla de flechas («de» —relación→ «a») con vista previa: no escribe código
 * Mermaid, y una fila mal escrita no puede romper el dibujo. Guardar con la tabla vacía quita el mapa.
 */
export function EditorMapa({ claseId, inicial, onGuardado, onCancelar }: { claseId: number; inicial: Relacion[]; onGuardado: () => void; onCancelar: () => void }) {
  const [filas, setFilas] = useState<Relacion[]>(inicial.length > 0 ? inicial : [{ de: '', relacion: '', a: '' }])
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const completas = filas.filter((f) => f.de.trim() && f.a.trim())
  const guardar = async () => {
    setError(null)
    setEnviando(true)
    try {
      await api(`/clases/${claseId}/mapa`, { metodo: 'PUT', cuerpo: { relaciones: completas } })
      onGuardado()
    } catch (e) {
      setError((e as Error).message)
      setEnviando(false)
    }
  }

  return (
    <div className="space-y-3">
      <FilasDeRelaciones filas={filas} onCambio={setFilas} />

      {completas.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Así lo verán los alumnos:</p>
          <div className="rounded-lg bg-muted/50 p-2">
            <Mermaid codigo={aMermaid(completas)} descripcion="Vista previa del mapa conceptual" />
          </div>
        </div>
      )}

      <ErrorForm mensaje={error} />
      <div className="flex gap-2">
        <Button className="h-11 desk:h-9" disabled={enviando} onClick={() => void guardar()}>
          {enviando && <Loader2 className="animate-spin" />} {completas.length === 0 ? 'Quitar el mapa' : 'Guardar mapa'}
        </Button>
        <Button variant="outline" className="h-11 desk:h-9" disabled={enviando} onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </div>
  )
}
