import { useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronRight, Clock, EyeOff, FileText, Layers, ListChecks, Loader2, MapPin, PenLine, Pencil, RotateCcw, Sparkles } from 'lucide-react'
import { Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { FotoLeida } from '@/components/FotoLeida'
import { EditorMaterial, type MaterialEditable } from '@/components/EditorMaterial'
import { Button } from '@/components/ui/button'
import { api, type ClaseDetalle, type ClaseResumen, type EstadoClase } from '@/lib/api'
import { colorAsignatura, fechaCorta, hhmm } from '@/lib/horario'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { cn } from '@/lib/utils'

const ESTADO: Record<EstadoClase, { texto: string; clase: string }> = {
  grabando: { texto: 'Grabando', clase: 'bg-red-100 text-red-900' },
  procesando: { texto: 'Procesando', clase: 'bg-muted text-muted-foreground' },
  error: { texto: 'Con error', clase: 'bg-red-200 text-red-950' },
  por_aprobar: { texto: 'Por aprobar', clase: 'bg-amber-100 text-amber-900' },
  provisoria: { texto: 'Provisoria', clase: 'bg-orange-100 text-orange-900' },
  publicada: { texto: 'Publicada', clase: 'bg-emerald-100 text-emerald-900' },
  retirada: { texto: 'Retirada', clase: 'bg-rose-100 text-rose-900' },
}

/**
 * Lista de clases. Alumno: las de su curso con el material ya aprobado. Profesor: las que dicta, en
 * cualquier estado, agrupadas por curso. PC: lista a la izquierda y detalle a la derecha.
 * Teléfono: la lista, y al tocar una clase se abre el detalle a pantalla completa.
 */
export function Clases({ cursoInicial, claseInicial }: { cursoInicial: number | null; claseInicial: number | null }) {
  const { rol } = useSesion()
  const clases = useCarga(() => api<ClaseResumen[]>('/clases'), [])
  const [curso, setCurso] = useState<number | null>(cursoInicial)
  const [seleccion, setSeleccion] = useState<number | null>(claseInicial)
  const esAlumno = rol === 'ALUMNO'

  const lista = useMemo(() => clases.datos ?? [], [clases.datos])
  const cursos = useMemo(() => [...new Map(lista.map((c) => [c.curso_id, c.curso_nombre]))].sort((a, b) => a[1].localeCompare(b[1], 'es')), [lista])
  const visibles = curso ? lista.filter((c) => c.curso_id === curso) : lista

  if (clases.cargando && !clases.datos) return <Cargando />
  if (clases.error) return <ErrorForm mensaje={clases.error} />
  if (lista.length === 0) {
    return (
      <Vacio icono={Sparkles} titulo="Aún no hay clases">
        {esAlumno
          ? 'Cuando tu profesor apruebe el material de una clase, aparecerá acá.'
          : 'Las clases que grabes aparecerán acá con su resumen, para que lo revises antes de publicarlo.'}
      </Vacio>
    )
  }

  // Un profesor con varios cursos ve las clases agrupadas por curso.
  const grupos: [string | null, ClaseResumen[]][] =
    !esAlumno && !curso && cursos.length > 1
      ? cursos.map(([id, nombre]) => [nombre, visibles.filter((c) => c.curso_id === id)])
      : [[null, visibles]]

  return (
    <div className="desk:grid desk:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] desk:items-start desk:gap-6 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <div className={cn('space-y-4', seleccion && 'hidden desk:block')}>
        {!esAlumno && cursos.length > 1 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 desk:mx-0 desk:flex-wrap desk:px-0" role="tablist" aria-label="Curso">
            <Chip activo={curso === null} onClick={() => setCurso(null)}>Todos</Chip>
            {cursos.map(([id, nombre]) => (
              <Chip key={id} activo={curso === id} onClick={() => setCurso(id)}>{nombre}</Chip>
            ))}
          </div>
        )}
        {grupos.map(([titulo, items]) => (
          <section key={titulo ?? 'todas'} className="space-y-2">
            {titulo && (
              <h2 className="flex items-center gap-2 pt-1 text-sm font-semibold">
                {titulo} <span className="text-xs font-normal text-muted-foreground">{items.length} {items.length === 1 ? 'clase' : 'clases'}</span>
              </h2>
            )}
            <ul className="space-y-2">
              {items.map((c) => (
                <li key={c.id}>
                  <FilaClase c={c} mostrarEstado={!esAlumno} seleccionada={c.id === seleccion} onClick={() => setSeleccion(c.id)} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <div className={cn('desk:sticky desk:top-6', !seleccion && 'hidden desk:block')}>
        {seleccion ? (
          <DetalleClase key={seleccion} id={seleccion} onVolver={() => setSeleccion(null)} onCambio={clases.recargar} />
        ) : (
          <div className="rounded-2xl border border-dashed p-10">
            <Vacio icono={FileText} titulo="Elige una clase">Verás su resumen, los puntos clave, la hoja de repaso y las tarjetas de estudio.</Vacio>
          </div>
        )}
      </div>
    </div>
  )
}

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: string }) {
  return (
    <button
      role="tab"
      aria-selected={activo}
      onClick={onClick}
      className={cn(
        'h-10 shrink-0 rounded-full px-4 text-sm font-medium transition-colors desk:h-8 desk:px-3.5',
        activo ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground ring-1 ring-border hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function Estado({ estado, comoAlumno = false }: { estado: EstadoClase; comoAlumno?: boolean }) {
  const e = comoAlumno && estado === 'provisoria' ? { ...ESTADO.provisoria, texto: 'Sin revisar' } : ESTADO[estado]
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium', e.clase)}>
      {estado === 'procesando' && <Loader2 className="size-3 animate-spin" />}
      {e.texto}
    </span>
  )
}

function FilaClase({ c, mostrarEstado, seleccionada, onClick }: { c: ClaseResumen; mostrarEstado: boolean; seleccionada: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-current={seleccionada ? 'true' : undefined}
      className={cn(
        'flex w-full items-center gap-3 rounded-xl border-l-4 px-3.5 py-3 text-left transition-shadow hover:shadow-sm',
        colorAsignatura(c.asignatura),
        seleccionada && 'ring-2 ring-primary',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="truncate text-base font-semibold leading-tight">{c.asignatura}</p>
          {(mostrarEstado || c.estado === 'provisoria') && <Estado estado={c.estado} comoAlumno={!mostrarEstado} />}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs opacity-75">
          <span className="font-medium capitalize">{fechaCorta(c.fecha)}</span>
          <span className="flex items-center gap-1"><Clock className="size-3" /> {hhmm(c.hora_inicio)}–{hhmm(c.hora_fin)}</span>
          {mostrarEstado && <span>{c.curso_nombre}</span>}
        </p>
      </div>
      <ChevronRight className="size-4 shrink-0 opacity-40 desk:hidden" />
    </button>
  )
}

// ---------------------------------------------------------------------------------------------

const fechaHora = (iso: string) =>
  new Date(iso).toLocaleString('es-CL', { weekday: 'long', day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })

function DetalleClase({ id, onVolver, onCambio }: { id: number; onVolver: () => void; onCambio: () => void }) {
  const { rol } = useSesion()
  const clase = useCarga(() => api<ClaseDetalle>(`/clases/${id}`), [id])
  const [trabajando, setTrabajando] = useState<'aprobar' | 'retirar' | null>(null)
  const [editando, setEditando] = useState(false)
  const [errorAccion, setErrorAccion] = useState<string | null>(null)

  const revisar = async (accion: 'aprobar' | 'retirar') => {
    setTrabajando(accion)
    setErrorAccion(null)
    try {
      await api(`/clases/${id}/${accion}`, { metodo: 'POST' })
      clase.recargar()
      onCambio() // refresca la lista (el estado cambió)
    } catch (e) {
      setErrorAccion((e as Error).message)
    } finally {
      setTrabajando(null)
    }
  }

  // Guarda lo corregido por el profesor; el estado de la clase no cambia.
  const guardarMaterial = async (m: MaterialEditable) => {
    await api(`/clases/${id}/contenido`, { metodo: 'PUT', cuerpo: m })
    setEditando(false)
    clase.recargar()
    onCambio()
  }

  if (clase.cargando && !clase.datos) return <Cargando />
  if (clase.error || !clase.datos) return <ErrorForm mensaje={clase.error} />
  const c = clase.datos
  const esProfesor = rol !== 'ALUMNO'
  const k = c.contenido
  const puntos = (k?.puntos_clave ?? '').split('\n').map((l) => l.replace(/^[-•*]\s*/, '').trim()).filter(Boolean)

  return (
    <article className="space-y-4 desk:max-h-[calc(100dvh-3rem)] desk:overflow-y-auto desk:pr-1">
      <button onClick={onVolver} className="-ml-2 flex h-10 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-foreground desk:hidden">
        <ArrowLeft className="size-4" /> Clases
      </button>

      <header className={cn('rounded-2xl border-l-4 p-4', colorAsignatura(c.asignatura))}>
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-xl font-semibold leading-tight">{c.asignatura}</h2>
          {(esProfesor || c.estado === 'provisoria') && <Estado estado={c.estado} comoAlumno={!esProfesor} />}
        </div>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm opacity-80">
          <span className="capitalize">{fechaCorta(c.fecha)}</span>
          <span className="flex items-center gap-1"><Clock className="size-3.5" /> {hhmm(c.hora_inicio)}–{hhmm(c.hora_fin)}</span>
          {c.sala && <span className="flex items-center gap-1"><MapPin className="size-3.5" /> {c.sala}</span>}
          {rol !== 'ALUMNO' && <span>{c.curso_nombre}</span>}
        </p>
      </header>

      {/* Alumno: advertencia cuando el material se publicó sin que el profesor lo revisara. */}
      {c.estado === 'provisoria' && !esProfesor && (
        <Aviso icono={AlertTriangle} tono="naranja">
          <strong>Material sin revisar.</strong> Se generó automáticamente y tu profesor todavía no lo ha revisado, así que puede
          tener errores. Contrástalo con tus apuntes.
        </Aviso>
      )}

      {/* Profesor: qué pasa con este material y qué puede hacer. */}
      {esProfesor && c.estado === 'por_aprobar' && (
        <Aviso icono={EyeOff} tono="ambar">
          Los alumnos todavía no ven este material.{' '}
          {c.revision_vence && (
            <>
              Si no lo apruebas o retiras antes del <strong>{fechaHora(c.revision_vence)}</strong>, se publicará como
              <strong> provisorio</strong>, con una advertencia.
            </>
          )}
        </Aviso>
      )}
      {esProfesor && c.estado === 'provisoria' && (
        <Aviso icono={AlertTriangle} tono="naranja">
          Pasó el plazo de revisión, así que se publicó como <strong>provisorio</strong>: los alumnos lo ven con una advertencia.
          Apruébalo para quitarla, o retíralo si tiene errores.
        </Aviso>
      )}
      {esProfesor && c.estado === 'retirada' && (
        <Aviso icono={EyeOff} tono="rosa">
          Retiraste este material: los alumnos no lo ven y no se publicará solo. Puedes aprobarlo si cambias de opinión.
        </Aviso>
      )}
      {esProfesor && c.contenido && (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {c.estado !== 'publicada' && (
              <Button className="h-11 flex-1 desk:h-9 desk:flex-none" disabled={trabajando !== null} onClick={() => revisar('aprobar')}>
                {trabajando === 'aprobar' ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Aprobar y publicar
              </Button>
            )}
            {c.estado !== 'retirada' && (
              <Button variant="outline" className="h-11 flex-1 desk:h-9 desk:flex-none" disabled={trabajando !== null} onClick={() => revisar('retirar')}>
                {trabajando === 'retirar' ? <Loader2 className="animate-spin" /> : <EyeOff />} Retirar
              </Button>
            )}
            {!editando && (
              <Button variant="outline" className="h-11 flex-1 desk:h-9 desk:flex-none" onClick={() => setEditando(true)}>
                <Pencil /> Editar material
              </Button>
            )}
          </div>
          <ErrorForm mensaje={errorAccion} />
        </div>
      )}

      {editando && k ? (
        <EditorMaterial
          inicial={{ resumen: k.resumen ?? '', puntos_clave: k.puntos_clave ?? '', hoja_repaso: k.hoja_repaso ?? '', tarjetas: k.tarjetas }}
          onGuardar={guardarMaterial}
          onCancelar={() => setEditando(false)}
        />
      ) : !k ? (
        <Vacio icono={Loader2} titulo="Preparando el material">Estamos transcribiendo y resumiendo esta clase. Vuelve en unos minutos.</Vacio>
      ) : (
        <>
          {k.resumen && (
            <Seccion icono={FileText} titulo="Resumen">
              <p className="leading-relaxed">{k.resumen}</p>
            </Seccion>
          )}
          {puntos.length > 0 && (
            <Seccion icono={ListChecks} titulo="Puntos clave">
              <ul className="space-y-2">
                {puntos.map((p, i) => (
                  <li key={i} className="flex gap-2.5">
                    <Check className="mt-1 size-4 shrink-0 text-primary" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </Seccion>
          )}
          {k.hoja_repaso && (
            <Seccion icono={Layers} titulo="Hoja de repaso">
              <p className="leading-relaxed">{k.hoja_repaso}</p>
            </Seccion>
          )}
          {k.tarjetas.length > 0 && (
            <Seccion icono={Sparkles} titulo="Tarjetas de estudio" nota="Intenta responder antes de ver la respuesta: recordar activamente es lo que más ayuda a aprender.">
              <ul className="space-y-2.5">
                {k.tarjetas.map((t, i) => (
                  <TarjetaEstudio key={i} pregunta={t.pregunta} respuesta={t.respuesta} />
                ))}
              </ul>
            </Seccion>
          )}
          {k.pizarra.length > 0 && (
            <Seccion
              icono={PenLine}
              titulo="De la pizarra"
              nota={
                esProfesor
                  ? 'La IA leyó estas fotos. Las cifras escritas a mano son lo que más falla: corrígelas o quítalas antes de aprobar.'
                  : 'Lectura automática de la pizarra: puede tener errores, sobre todo en cifras. Contrástala con tus apuntes.'
              }
            >
              <ul className="space-y-4">
                {k.pizarra.map((f) => (
                  <FotoLeida key={f.id} claseId={id} foto={f} editable={esProfesor} onCambio={() => { clase.recargar(); onCambio() }} />
                ))}
              </ul>
            </Seccion>
          )}
          {k.transcripcion_texto && (
            <details className="rounded-2xl border bg-card p-4">
              <summary className="cursor-pointer text-sm font-medium">Ver transcripción</summary>
              <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{k.transcripcion_texto}</p>
            </details>
          )}
        </>
      )}
    </article>
  )
}

const TONOS = {
  ambar: 'bg-amber-50 text-amber-950 ring-amber-200',
  naranja: 'bg-orange-50 text-orange-950 ring-orange-300',
  rosa: 'bg-rose-50 text-rose-950 ring-rose-200',
}

function Aviso({ icono: Icono, tono, children }: { icono: typeof FileText; tono: keyof typeof TONOS; children: React.ReactNode }) {
  return (
    <div role="note" className={cn('flex items-start gap-2.5 rounded-xl p-3.5 text-sm ring-1', TONOS[tono])}>
      <Icono className="mt-0.5 size-4 shrink-0" />
      <p className="flex-1 leading-relaxed">{children}</p>
    </div>
  )
}

function Seccion({ icono: Icono, titulo, nota, children }: { icono: typeof FileText; titulo: string; nota?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border bg-card p-4 desk:p-5">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-primary">
        <Icono className="size-4" /> {titulo}
      </h3>
      {nota && <p className="-mt-1 mb-3 text-xs text-muted-foreground">{nota}</p>}
      <div className="text-[15px]">{children}</div>
    </section>
  )
}

function TarjetaEstudio({ pregunta, respuesta }: { pregunta: string; respuesta: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <li className="rounded-xl bg-muted/60 p-3.5">
      <p className="font-medium">{pregunta}</p>
      {visible ? (
        <div className="mt-2 flex items-start justify-between gap-3 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
          <p>{respuesta}</p>
          <button onClick={() => setVisible(false)} aria-label="Ocultar respuesta" className="shrink-0 text-muted-foreground hover:text-foreground">
            <RotateCcw className="size-4" />
          </button>
        </div>
      ) : (
        <Button variant="outline" size="sm" className="mt-2 h-9 desk:h-7" onClick={() => setVisible(true)}>
          Ver respuesta
        </Button>
      )}
    </li>
  )
}
