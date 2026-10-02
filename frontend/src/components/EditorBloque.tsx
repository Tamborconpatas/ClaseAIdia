import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Loader2, Trash2 } from 'lucide-react'
import { Campo, ErrorForm } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { api, type Bloque, type TipoBloque, type Usuario } from '@/lib/api'
import { DIAS_LARGO, hhmm } from '@/lib/horario'
import { cn } from '@/lib/utils'

export type EstadoEditor =
  | { modo: 'nuevo'; cursoId: number; cursoNombre: string; dia: number; inicio: string; fin: string }
  | { modo: 'editar'; bloque: Bloque; cursoNombre: string }

const TIPOS: { valor: TipoBloque; etiqueta: string }[] = [
  { valor: 'CLASE', etiqueta: 'Clase' },
  { valor: 'RECREO', etiqueta: 'Recreo' },
  { valor: 'ALMUERZO', etiqueta: 'Almuerzo' },
]

const SELECT = 'h-11 w-full rounded-lg border bg-background px-3 text-base desk:h-9 desk:text-sm'

interface Props {
  estado: EstadoEditor | null
  /** Usuarios con rol PROFESOR del colegio, para asignar al bloque. */
  profesores: Usuario[]
  onCerrar: () => void
  onGuardado: () => void
}

/** Crear o editar un bloque del horario. Teléfono: hoja desde abajo. PC: cuadro centrado. */
export function EditorBloque({ estado, profesores, onCerrar, onGuardado }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (estado && !d.open) d.showModal()
    if (!estado && d.open) d.close()
  }, [estado])

  return (
    <dialog
      ref={ref}
      onClose={onCerrar}
      // Tocar el fondo oscuro cierra (el clic llega al <dialog> mismo, que no tiene relleno).
      onClick={(e) => e.target === ref.current && onCerrar()}
      aria-label="Editar bloque del horario"
      className="m-0 mt-auto max-h-[92dvh] w-full max-w-none overflow-y-auto rounded-t-3xl border-0 bg-background p-0 text-foreground shadow-2xl backdrop:bg-black/50 desk:m-auto desk:max-w-lg desk:rounded-2xl"
    >
      {estado && (
        <Formulario
          key={estado.modo === 'editar' ? `b${estado.bloque.id}` : `n${estado.dia}-${estado.inicio}`}
          estado={estado}
          profesores={profesores}
          onCerrar={onCerrar}
          onGuardado={onGuardado}
        />
      )}
    </dialog>
  )
}

function Formulario({ estado, profesores, onCerrar, onGuardado }: Omit<Props, 'estado'> & { estado: EstadoEditor }) {
  const b = estado.modo === 'editar' ? estado.bloque : null
  const [tipo, setTipo] = useState<TipoBloque>(b?.tipo ?? 'CLASE')
  const [asignatura, setAsignatura] = useState(b?.asignatura ?? '')
  const [profesorId, setProfesorId] = useState(b?.profesor_id ? String(b.profesor_id) : '')
  const [sala, setSala] = useState(b?.sala ?? '')
  const [dia, setDia] = useState(b ? b.dia_semana : (estado as { dia: number }).dia)
  const [inicio, setInicio] = useState(b ? hhmm(b.hora_inicio) : (estado as { inicio: string }).inicio)
  const [fin, setFin] = useState(b ? hhmm(b.hora_fin) : (estado as { fin: string }).fin)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [confirmando, setConfirmando] = useState(false)
  const esClase = tipo === 'CLASE'

  const ejecutar = async (accion: () => Promise<unknown>) => {
    setError(null)
    setEnviando(true)
    try {
      await accion()
      onGuardado()
    } catch (e) {
      setError((e as Error).message)
      setEnviando(false)
    }
  }

  const guardar = (e: FormEvent) => {
    e.preventDefault()
    if (fin <= inicio) return setError('La hora de término debe ser posterior a la de inicio.')
    if (esClase && !asignatura.trim()) return setError('Una clase necesita asignatura.')
    const cuerpo = {
      tipo,
      asignatura: esClase ? asignatura.trim() : null,
      profesor_id: esClase && profesorId ? Number(profesorId) : null,
      sala: esClase ? sala.trim() || null : null,
      dia_semana: dia,
      hora_inicio: inicio,
      hora_fin: fin,
    }
    void ejecutar(() =>
      estado.modo === 'editar'
        ? api(`/bloques/${estado.bloque.id}`, { metodo: 'PUT', cuerpo })
        : api(`/cursos/${estado.cursoId}/bloques`, { metodo: 'POST', cuerpo }),
    )
  }

  return (
    <form onSubmit={guardar} className="space-y-4 p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] desk:p-6" noValidate>
      <div>
        <h2 className="text-lg font-semibold">{estado.modo === 'editar' ? 'Editar bloque' : 'Nuevo bloque'}</h2>
        <p className="text-sm text-muted-foreground">Curso {estado.cursoNombre}</p>
      </div>

      <div role="radiogroup" aria-label="Tipo de bloque" className="grid grid-cols-3 gap-1.5 rounded-xl bg-muted p-1">
        {TIPOS.map((t) => (
          <button
            key={t.valor}
            type="button"
            role="radio"
            aria-checked={tipo === t.valor}
            onClick={() => setTipo(t.valor)}
            className={cn(
              'h-10 rounded-lg text-sm font-medium transition-colors desk:h-8',
              tipo === t.valor ? 'bg-background shadow-sm' : 'text-muted-foreground',
            )}
          >
            {t.etiqueta}
          </button>
        ))}
      </div>

      {esClase && (
        <>
          <Campo etiqueta="Asignatura" value={asignatura} onChange={(e) => setAsignatura(e.target.value)} placeholder="Matemática" />
          <div className="space-y-1.5">
            <label htmlFor="bloque-profesor" className="text-sm font-medium">Profesor</label>
            <select id="bloque-profesor" value={profesorId} onChange={(e) => setProfesorId(e.target.value)} className={SELECT}>
              <option value="">Sin asignar</option>
              {/* Un profesor desactivado solo aparece si el bloque ya era suyo: el backend no deja asignarle bloques nuevos. */}
              {profesores
                .filter((p) => p.activo || String(p.id) === profesorId)
                .map((p) => (
                  <option key={p.id} value={p.id}>{p.nombre}{p.activo ? '' : ' (desactivado)'}</option>
                ))}
            </select>
          </div>
          <Campo etiqueta="Sala" value={sala} onChange={(e) => setSala(e.target.value)} placeholder="Sala 12" />
        </>
      )}

      <div className="space-y-1.5">
        <label htmlFor="bloque-dia" className="text-sm font-medium">Día</label>
        <select id="bloque-dia" value={dia} onChange={(e) => setDia(Number(e.target.value))} className={SELECT}>
          {DIAS_LARGO.map((nombre, i) => (
            <option key={nombre} value={i}>{nombre}</option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Campo etiqueta="Desde" type="time" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        <Campo etiqueta="Hasta" type="time" value={fin} onChange={(e) => setFin(e.target.value)} />
      </div>

      <ErrorForm mensaje={error} />

      {confirmando ? (
        <div className="space-y-2 rounded-xl bg-destructive/10 p-3.5 text-sm">
          <p className="text-destructive">¿Eliminar este bloque? Desaparecerá del horario de todos.</p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="destructive"
              className="h-11 flex-1 desk:h-9"
              disabled={enviando}
              onClick={() => b && void ejecutar(() => api(`/bloques/${b.id}`, { metodo: 'DELETE' }))}
            >
              {enviando && <Loader2 className="animate-spin" />} Sí, eliminar
            </Button>
            <Button type="button" variant="outline" className="h-11 flex-1 desk:h-9" onClick={() => setConfirmando(false)}>
              No
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button type="submit" disabled={enviando} className="h-12 min-w-32 flex-1 text-base desk:h-10 desk:text-sm">
            {enviando && <Loader2 className="animate-spin" />} Guardar
          </Button>
          <Button type="button" variant="outline" className="h-12 desk:h-10" onClick={onCerrar}>
            Cancelar
          </Button>
          {b && (
            <Button type="button" variant="ghost" className="h-12 text-destructive desk:h-10" onClick={() => setConfirmando(true)}>
              <Trash2 /> Eliminar
            </Button>
          )}
        </div>
      )}
    </form>
  )
}
