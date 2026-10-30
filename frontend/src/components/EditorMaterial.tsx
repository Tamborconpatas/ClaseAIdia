/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useState, type FormEvent } from 'react'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { Tarjeta } from '@/lib/api'

export interface MaterialEditable {
  resumen: string
  puntos_clave: string
  hoja_repaso: string
  tarjetas: Tarjeta[]
}

const MAX_TARJETAS = 40
const AREA =
  'min-h-28 w-full rounded-lg border border-input bg-transparent px-3 py-2 text-base outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 desk:text-sm'

function Area({ id, etiqueta, ayuda, valor, onCambio, filas }: { id: string; etiqueta: string; ayuda?: string; valor: string; onCambio: (v: string) => void; filas: number }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{etiqueta}</Label>
      <textarea id={id} rows={filas} value={valor} maxLength={20_000} onChange={(e) => onCambio(e.target.value)} className={AREA} />
      {ayuda && <p className="text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  )
}

/** El profesor corrige lo que generó la IA antes de aprobarlo. La transcripción no se edita: es el registro de lo dicho. */
export function EditorMaterial({ inicial, onGuardar, onCancelar }: { inicial: MaterialEditable; onGuardar: (m: MaterialEditable) => Promise<void>; onCancelar: () => void }) {
  const [resumen, setResumen] = useState(inicial.resumen)
  const [puntos, setPuntos] = useState(inicial.puntos_clave)
  const [hoja, setHoja] = useState(inicial.hoja_repaso)
  const [tarjetas, setTarjetas] = useState<Tarjeta[]>(inicial.tarjetas)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const cambiarTarjeta = (i: number, campo: keyof Tarjeta, valor: string) =>
    setTarjetas((ts) => ts.map((t, j) => (j === i ? { ...t, [campo]: valor } : t)))

  const guardar = async (e: FormEvent) => {
    e.preventDefault()
    if (tarjetas.some((t) => !t.pregunta.trim() || !t.respuesta.trim())) {
      return setError('Cada tarjeta necesita pregunta y respuesta (o quítala).')
    }
    setError(null)
    setEnviando(true)
    try {
      await onGuardar({ resumen, puntos_clave: puntos, hoja_repaso: hoja, tarjetas })
    } catch (err) {
      setError((err as Error).message)
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={guardar} noValidate className="space-y-4 rounded-2xl border bg-card p-4 desk:p-5" aria-label="Editar el material de la clase">
      <Area id="mat-resumen" etiqueta="Resumen" valor={resumen} onCambio={setResumen} filas={6} />
      <Area id="mat-puntos" etiqueta="Puntos clave" ayuda="Uno por línea." valor={puntos} onCambio={setPuntos} filas={5} />
      <Area id="mat-hoja" etiqueta="Hoja de repaso" valor={hoja} onCambio={setHoja} filas={6} />

      <fieldset className="space-y-3">
        <legend className="mb-1 text-sm font-medium">Tarjetas de estudio</legend>
        {tarjetas.length === 0 && <p className="text-sm text-muted-foreground">Sin tarjetas. Puedes agregar las que quieras.</p>}
        {tarjetas.map((t, i) => (
          <div key={i} className="space-y-2 rounded-xl bg-muted/50 p-3">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1 space-y-2">
                <Input aria-label={`Pregunta de la tarjeta ${i + 1}`} placeholder="Pregunta" value={t.pregunta} onChange={(e) => cambiarTarjeta(i, 'pregunta', e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
                <Input aria-label={`Respuesta de la tarjeta ${i + 1}`} placeholder="Respuesta" value={t.respuesta} onChange={(e) => cambiarTarjeta(i, 'respuesta', e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
              </div>
              <Button type="button" variant="ghost" size="icon-lg" aria-label={`Quitar la tarjeta ${i + 1}`} onClick={() => setTarjetas((ts) => ts.filter((_, j) => j !== i))}>
                <Trash2 />
              </Button>
            </div>
          </div>
        ))}
        <Button type="button" variant="outline" className="h-10 desk:h-8" disabled={tarjetas.length >= MAX_TARJETAS} onClick={() => setTarjetas((ts) => [...ts, { pregunta: '', respuesta: '' }])}>
          <Plus /> Agregar tarjeta
        </Button>
      </fieldset>

      <ErrorForm mensaje={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={enviando} className="h-12 flex-1 text-base desk:h-10 desk:flex-none desk:text-sm">
          {enviando && <Loader2 className="animate-spin" />} Guardar cambios
        </Button>
        <Button type="button" variant="outline" className="h-12 desk:h-10" disabled={enviando} onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
    </form>
  )
}
