import { useMemo, useState, type ReactNode } from 'react'
import { CalendarDays, ChevronRight, Coffee, Info, Loader2, MapPin, Plus, User, Utensils, X } from 'lucide-react'
import { Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { EditorBloque, type EstadoEditor } from '@/components/EditorBloque'
import { Button } from '@/components/ui/button'
import { api, type Bloque, type ClaseResumen, type Curso, type Usuario } from '@/lib/api'
import { cargarBloques } from '@/lib/datos'
import { DIAS_CORTO, DIAS_LARGO, aMinutos, colorAsignatura, diaHoy, esAhora, hhmm, ordenar } from '@/lib/horario'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { cn } from '@/lib/utils'

/**
 * Alumno: los bloques de todos sus cursos. Profesor: solo los bloques que dicta él.
 * UTP: el horario completo de un curso a la vez.
 * Alumno y profesor pueden tocar un bloque para abrir la clase más reciente de ese bloque.
 * El UTP edita: toca un bloque para modificarlo o eliminarlo, o una celda vacía para agregar uno.
 */
export function Horario({ onAbrirClase }: { onAbrirClase: (claseId: number) => void }) {
  const { usuario, rol } = useSesion()
  const esUtp = rol === 'UTP'
  const cursos = useCarga(() => api<Curso[]>('/cursos'), [])
  const personal = useCarga(() => (esUtp ? api<Usuario[]>('/usuarios') : Promise.resolve([])), [esUtp])
  const [elegido, setElegido] = useState<number | null>(null)
  const [buscando, setBuscando] = useState<number | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [editor, setEditor] = useState<EstadoEditor | null>(null)

  // Un bloque se repite cada semana: se abre su clase más reciente entre las que el usuario puede ver
  // (la lista ya viene ordenada de la más nueva a la más antigua).
  const abrirBloque = async (b: Bloque) => {
    setAviso(null)
    setBuscando(b.id)
    try {
      const clase = (await api<ClaseResumen[]>('/clases')).find((c) => c.bloque_id === b.id)
      if (clase) return onAbrirClase(clase.id)
      setAviso(
        rol === 'ALUMNO'
          ? `Todavía no hay material de ${b.asignatura}. Aparecerá cuando tu profesor apruebe la clase.`
          : `Todavía no hay clases registradas de ${b.asignatura} en este bloque.`,
      )
    } catch (e) {
      setAviso((e as Error).message)
    } finally {
      setBuscando(null)
    }
  }

  const lista = useMemo(() => cursos.datos ?? [], [cursos.datos])
  const cursoUtp = elegido ?? lista[0]?.id
  const ids = esUtp ? (cursoUtp ? [cursoUtp] : []) : lista.map((c) => c.id)

  const bloques = useCarga(() => cargarBloques(ids), [ids.join(',')])

  const nombreCurso = useMemo(() => new Map(lista.map((c) => [c.id, c.nombre])), [lista])
  const profesores = useMemo(() => (personal.datos ?? []).filter((u) => u.roles.includes('PROFESOR')), [personal.datos])

  const editarBloque = (b: Bloque) => setEditor({ modo: 'editar', bloque: b, cursoNombre: nombreCurso.get(b.curso_id) ?? '' })
  const agregarBloque = (dia: number, inicio: string, fin: string) =>
    cursoUtp && setEditor({ modo: 'nuevo', cursoId: cursoUtp, cursoNombre: nombreCurso.get(cursoUtp) ?? '', dia, inicio, fin })
  const onAbrir = esUtp ? editarBloque : abrirBloque
  const visibles = useMemo(() => {
    const todos = bloques.datos ?? []
    return rol === 'PROFESOR' ? todos.filter((b) => b.profesor_id === usuario?.id) : todos
  }, [bloques.datos, rol, usuario?.id])

  if (cursos.cargando) return <Cargando />
  if (cursos.error) return <ErrorForm mensaje={cursos.error} />
  if (lista.length === 0) {
    return (
      <Vacio icono={CalendarDays} titulo="Todavía no hay horario">
        {rol === 'ALUMNO' ? 'Cuando te unas a un curso, tu horario aparecerá acá.' : 'Primero crea un curso en la pestaña Cursos.'}
      </Vacio>
    )
  }

  return (
    <div className="space-y-4">
      {esUtp && (
        <div className="flex items-center gap-3">
          <select
            aria-label="Curso"
            value={cursoUtp}
            onChange={(e) => setElegido(Number(e.target.value))}
            className="h-11 w-full rounded-lg border bg-background px-3 text-base desk:h-9 desk:w-56 desk:text-sm"
          >
            {lista.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
          </select>
          <Button className="hidden h-9 desk:inline-flex" onClick={() => agregarBloque(0, '08:00', '08:45')}>
            <Plus /> Agregar bloque
          </Button>
        </div>
      )}
      {aviso && (
        <div role="status" className="flex items-start gap-2.5 rounded-xl bg-secondary p-3.5 text-sm text-secondary-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p className="flex-1">{aviso}</p>
          <button onClick={() => setAviso(null)} aria-label="Cerrar aviso" className="-m-1 p-1 opacity-70 hover:opacity-100">
            <X className="size-4" />
          </button>
        </div>
      )}
      {bloques.cargando ? (
        <Cargando />
      ) : bloques.error ? (
        <ErrorForm mensaje={bloques.error} />
      ) : visibles.length === 0 ? (
        <Vacio
          icono={CalendarDays}
          titulo="Sin bloques"
          accion={
            esUtp && (
              <Button className="h-11 desk:h-9" onClick={() => agregarBloque(0, '08:00', '08:45')}>
                <Plus /> Agregar el primer bloque
              </Button>
            )
          }
        >
          {rol === 'PROFESOR' ? 'No tienes clases asignadas todavía.' : 'Este curso aún no tiene horario.'}
        </Vacio>
      ) : (
        <>
          <Semana bloques={visibles} nombreCurso={nombreCurso} multiCurso={!esUtp && lista.length > 1} onAbrir={onAbrir} buscando={buscando} mostrarProfesor={rol !== 'PROFESOR'} editar={esUtp} onAgregar={esUtp ? agregarBloque : undefined} />
          <Agenda bloques={visibles} nombreCurso={nombreCurso} multiCurso={!esUtp && lista.length > 1} onAbrir={onAbrir} buscando={buscando} mostrarProfesor={rol !== 'PROFESOR'} editar={esUtp} onAgregar={esUtp ? agregarBloque : undefined} />
        </>
      )}
      {esUtp && (
        <EditorBloque
          estado={editor}
          profesores={profesores}
          onCerrar={() => setEditor(null)}
          onGuardado={() => {
            setEditor(null)
            bloques.recargar()
          }}
        />
      )}
    </div>
  )
}

interface VistaProps {
  bloques: Bloque[]
  nombreCurso: Map<number, string>
  multiCurso: boolean
  /** Alumno/profesor: abrir la clase del bloque. UTP: editar el bloque. */
  onAbrir?: (b: Bloque) => void
  /** Modo edición (UTP): se ven también los recreos como bloques editables y las celdas vacías permiten agregar. */
  editar: boolean
  onAgregar?: (dia: number, inicio: string, fin: string) => void
  /** Bloque cuya clase se está buscando, para mostrar que está cargando. */
  buscando: number | null
  /** El nombre del profesor sobra en el horario del propio profesor. */
  mostrarProfesor: boolean
}

function Profesor({ b, mostrar, className }: { b: Bloque; mostrar: boolean; className?: string }) {
  if (!mostrar || !b.profesor_nombre) return null
  return (
    <p className={cn('flex items-center gap-1 opacity-80', className)}>
      <User className="size-3 shrink-0" />
      <span className="truncate">{b.profesor_nombre}</span>
    </p>
  )
}

/** El bloque del horario: un botón si se puede abrir (o editar), una tarjeta simple si no. */
function Casilla({ b, onAbrir, editar, className, children }: { b: Bloque; onAbrir?: (b: Bloque) => void; editar: boolean; className: string; children: ReactNode }) {
  if (!onAbrir) return <div className={className}>{children}</div>
  return (
    <button
      type="button"
      onClick={() => onAbrir(b)}
      aria-label={editar ? `Editar el bloque de ${b.asignatura ?? etiquetaNoLectivo(b)}` : `Abrir la clase de ${b.asignatura}`}
      className={cn(className, 'w-full cursor-pointer text-left transition-shadow hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary')}
    >
      {children}
    </button>
  )
}

const diasPresentes = (bs: Bloque[]) => {
  const hasta = Math.max(4, ...bs.map((b) => b.dia_semana))
  return Array.from({ length: hasta + 1 }, (_, i) => i)
}

function IconoNoLectivo({ tipo }: { tipo: Bloque['tipo'] }) {
  return tipo === 'ALMUERZO' ? <Utensils className="size-3.5" /> : <Coffee className="size-3.5" />
}
const etiquetaNoLectivo = (b: Bloque) => (b.tipo === 'ALMUERZO' ? 'Almuerzo' : 'Recreo')

// ---------------------------------------------------------------------------------------------
// PC: grilla semanal (días en columnas, tramos horarios en filas)
// ---------------------------------------------------------------------------------------------

function Semana({ bloques, nombreCurso, multiCurso, onAbrir, buscando, mostrarProfesor, editar, onAgregar }: VistaProps) {
  const dias = diasPresentes(bloques)
  const hoy = diaHoy()
  const tramos = [...new Set(ordenar(bloques).map((b) => `${b.hora_inicio}|${b.hora_fin}`))]
  const columnas = { gridTemplateColumns: `4.75rem repeat(${dias.length}, minmax(0, 1fr))` }
  // Jornada larga (p. ej. 8:30 a 18:15): filas más bajas, para que quepa sin alargar la tabla ni obligar a bajar de más.
  const compacta = tramos.length > 10

  return (
    // Sin overflow-hidden: el encabezado con los días queda fijo (sticky) al bajar por una jornada larga.
    <div className="hidden rounded-2xl border bg-card desk:block">
      <div className="sticky top-0 z-10 grid rounded-t-2xl border-b bg-muted text-sm font-medium" style={columnas}>
        <div />
        {dias.map((d) => (
          <div key={d} className={cn('px-3', compacta ? 'py-2' : 'py-2.5', d === hoy && 'text-primary')}>
            {DIAS_LARGO[d]}
            {d === hoy && <span className="ml-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] text-primary-foreground">hoy</span>}
          </div>
        ))}
      </div>
      {tramos.map((t) => {
        const [ini, fin] = t.split('|')
        const delTramo = bloques.filter((b) => b.hora_inicio === ini && b.hora_fin === fin)
        const soloNoLectivo = delTramo.every((b) => b.tipo !== 'CLASE')
        // Para editar, el recreo se ve día por día (cada uno es un bloque distinto) en vez de una franja única.
        if (soloNoLectivo && !editar) {
          return (
            <div key={t} className="grid items-center border-b py-1 text-xs text-muted-foreground last:border-b-0" style={columnas}>
              <div className="px-3 tabular-nums">{hhmm(ini)}</div>
              <div className="col-span-full col-start-2 flex items-center gap-1.5 rounded-md bg-muted/60 px-3 py-1" style={{ gridColumn: `2 / span ${dias.length}` }}>
                <IconoNoLectivo tipo={delTramo[0].tipo} /> {etiquetaNoLectivo(delTramo[0])} · {hhmm(ini)}–{hhmm(fin)}
              </div>
            </div>
          )
        }
        return (
          <div key={t} className="grid border-b last:border-b-0" style={columnas}>
            <div className={cn('px-3 text-xs tabular-nums text-muted-foreground', compacta ? 'py-1.5' : 'py-3')}>
              <div className="font-medium text-foreground">{hhmm(ini)}</div>
              {hhmm(fin)}
            </div>
            {dias.map((d) => {
              const b = delTramo.find((x) => x.dia_semana === d && (editar || x.tipo === 'CLASE'))
              return (
                <div key={d} className={cn(compacta ? 'p-1' : 'p-1.5', d === hoy && 'bg-primary/[0.04]')}>
                  {!b && onAgregar && (
                    <button
                      type="button"
                      onClick={() => onAgregar(d, hhmm(ini), hhmm(fin))}
                      aria-label={`Agregar un bloque el ${DIAS_LARGO[d]} a las ${hhmm(ini)}`}
                      className={cn('flex h-full w-full items-center justify-center rounded-lg border border-dashed border-transparent text-transparent transition-colors hover:border-border hover:text-muted-foreground focus-visible:border-primary focus-visible:text-primary', compacta ? 'min-h-9' : 'min-h-14')}
                    >
                      <Plus className="size-4" />
                    </button>
                  )}
                  {b && b.tipo !== 'CLASE' && (
                    <Casilla b={b} onAbrir={onAbrir} editar={editar} className={cn('block h-full rounded-lg bg-muted/60 px-2.5 text-xs text-muted-foreground', compacta ? 'py-1' : 'py-2')}>
                      <span className="flex items-center gap-1.5">
                        <IconoNoLectivo tipo={b.tipo} /> {etiquetaNoLectivo(b)}
                      </span>
                    </Casilla>
                  )}
                  {b && b.tipo === 'CLASE' && (
                    <Casilla
                      b={b}
                      onAbrir={onAbrir}
                      editar={editar}
                      className={cn(
                        'block h-full rounded-lg border-l-4',
                        compacta ? 'px-2 py-1 text-[13px]' : 'px-2.5 py-2 text-sm',
                        colorAsignatura(b.asignatura),
                        esAhora(b) && 'ring-2 ring-primary ring-offset-1',
                      )}
                    >
                      <p className="flex items-center justify-between gap-1 font-medium leading-tight">
                        <span className="truncate">{b.asignatura}</span>
                        {buscando === b.id && <Loader2 className="size-3.5 shrink-0 animate-spin" />}
                      </p>
                      {compacta ? (
                        // Una sola línea con lo demás (profesor · sala · curso): la fila queda a la mitad de alto.
                        <p className="truncate text-[11px] leading-tight opacity-75">
                          {[mostrarProfesor && b.profesor_nombre, b.sala, multiCurso && nombreCurso.get(b.curso_id)].filter(Boolean).join(' · ')}
                        </p>
                      ) : (
                        <>
                          <Profesor b={b} mostrar={mostrarProfesor} className="mt-0.5 text-xs" />
                          <p className="mt-0.5 flex items-center gap-1 text-xs opacity-70">
                            {b.sala && (
                              <>
                                <MapPin className="size-3" /> {b.sala}
                              </>
                            )}
                            {multiCurso && <span> · {nombreCurso.get(b.curso_id)}</span>}
                          </p>
                        </>
                      )}
                    </Casilla>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------
// Teléfono: agenda de un día, con chips para cambiar de día
// ---------------------------------------------------------------------------------------------

const aHHMM = (min: number) => {
  const m = Math.min(min, 23 * 60 + 59)
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

function Agenda({ bloques, nombreCurso, multiCurso, onAbrir, buscando, mostrarProfesor, editar, onAgregar }: VistaProps) {
  const dias = diasPresentes(bloques)
  const hoy = diaHoy()
  const [dia, setDia] = useState(dias.includes(hoy) ? hoy : 0)
  const delDia = ordenar(bloques.filter((b) => b.dia_semana === dia))
  // Al agregar, se sugiere un bloque de 45 min a continuación del último del día.
  const ultimo = delDia[delDia.length - 1]
  const sugerido = ultimo ? [hhmm(ultimo.hora_fin), aHHMM(aMinutos(ultimo.hora_fin) + 45)] : ['08:00', '08:45']

  return (
    <div className="space-y-4 desk:hidden">
      <div role="tablist" aria-label="Día" className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${dias.length}, minmax(0, 1fr))` }}>
        {dias.map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={d === dia}
            onClick={() => setDia(d)}
            className={cn(
              'relative flex h-14 flex-col items-center justify-center rounded-xl text-sm font-medium transition-colors short:h-9',
              d === dia ? 'bg-primary text-primary-foreground shadow-sm' : 'bg-card text-muted-foreground ring-1 ring-border',
            )}
          >
            {DIAS_CORTO[d]}
            {d === hoy && <span className={cn('mt-0.5 size-1.5 rounded-full', d === dia ? 'bg-primary-foreground' : 'bg-primary')} />}
          </button>
        ))}
      </div>

      <h2 className="text-sm font-medium text-muted-foreground short:hidden">
        {DIAS_LARGO[dia]}
        {dia === hoy && ' · hoy'}
      </h2>

      {delDia.length === 0 ? (
        <Vacio icono={CalendarDays} titulo="Día libre">
          No hay clases este día.
        </Vacio>
      ) : (
        <ol className="space-y-2.5 short:grid short:grid-cols-2 short:gap-x-3 short:gap-y-2 short:space-y-0">
          {delDia.map((b) =>
            b.tipo === 'CLASE' ? (
              <li key={b.id} className="flex gap-3">
                <div className="w-12 shrink-0 pt-3 text-right short:pt-2 text-xs tabular-nums text-muted-foreground">
                  <div className="font-semibold text-foreground">{hhmm(b.hora_inicio)}</div>
                  {hhmm(b.hora_fin)}
                </div>
                <Casilla
                  b={b}
                  onAbrir={onAbrir}
                  editar={editar}
                  className={cn('block flex-1 rounded-xl border-l-4 px-3.5 py-3 short:py-2', colorAsignatura(b.asignatura), esAhora(b) && 'ring-2 ring-primary')}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-base font-semibold leading-tight">{b.asignatura}</p>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {esAhora(b) && <span className="rounded-full bg-primary px-2 py-0.5 text-[11px] font-medium text-primary-foreground">Ahora</span>}
                      {buscando === b.id ? <Loader2 className="size-4 animate-spin" /> : onAbrir && <ChevronRight className="size-4 opacity-40" />}
                    </span>
                  </div>
                  <Profesor b={b} mostrar={mostrarProfesor} className="mt-0.5 text-sm" />
                  <p className="mt-1 flex items-center gap-1 text-sm opacity-75">
                    {b.sala && (
                      <>
                        <MapPin className="size-3.5" /> {b.sala}
                      </>
                    )}
                    {multiCurso && <span> · {nombreCurso.get(b.curso_id)}</span>}
                  </p>
                </Casilla>
              </li>
            ) : (
              <li key={b.id} className="pl-[3.75rem] text-xs text-muted-foreground short:col-span-2">
                {editar ? (
                  <Casilla b={b} onAbrir={onAbrir} editar className="flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-2">
                    <IconoNoLectivo tipo={b.tipo} /> {etiquetaNoLectivo(b)} · {hhmm(b.hora_inicio)}–{hhmm(b.hora_fin)}
                  </Casilla>
                ) : (
                  <span className="flex items-center gap-2">
                    <IconoNoLectivo tipo={b.tipo} /> {etiquetaNoLectivo(b)} · {hhmm(b.hora_inicio)}–{hhmm(b.hora_fin)}
                  </span>
                )}
              </li>
            ),
          )}
        </ol>
      )}
      {onAgregar && (
        <Button variant="outline" className="h-11 w-full border-dashed" onClick={() => onAgregar(dia, sugerido[0], sugerido[1])}>
          <Plus /> Agregar bloque el {DIAS_LARGO[dia].toLowerCase()}
        </Button>
      )}
    </div>
  )
}
