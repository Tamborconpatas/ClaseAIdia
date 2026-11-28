/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronRight, Clock, EyeOff, FileText, Layers, ListChecks, Loader2, MapPin, Network, PenLine, Pencil, RotateCcw, Sparkles } from 'lucide-react'
import { Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { FotoLeida } from '@/components/FotoLeida'
import { DescargarClase } from '@/components/DescargarClase'
import { EditorMapa, MapaDibujado } from '@/components/MapaConceptual'
import { EditorMaterial, type MaterialEditable } from '@/components/EditorMaterial'
import { Button } from '@/components/ui/button'
import { api, type ClaseDetalle, type ClaseResumen, type EstadoClase } from '@/lib/api'
import { colorAsignatura, fechaCorta, hhmm } from '@/lib/horario'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { cn } from '@/lib/utils'

const ESTADO: Record<EstadoClase, { texto: string; clase: string }> = {
  grabando: { texto: 'Grabando', clase: 'bg-red-100 dark:bg-red-950/60 text-red-900 dark:text-red-200' },
  procesando: { texto: 'Procesando', clase: 'bg-muted text-muted-foreground' },
  error: { texto: 'Con error', clase: 'bg-red-200 dark:bg-red-900/60 text-red-950 dark:text-red-100' },
  por_aprobar: { texto: 'Por aprobar', clase: 'bg-amber-100 dark:bg-amber-950/60 text-amber-900 dark:text-amber-200' },
  provisoria: { texto: 'Provisoria', clase: 'bg-orange-100 dark:bg-orange-950/60 text-orange-900 dark:text-orange-200' },
  publicada: { texto: 'Publicada', clase: 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-900 dark:text-emerald-200' },
  retirada: { texto: 'Retirada', clase: 'bg-rose-100 dark:bg-rose-950/60 text-rose-900 dark:text-rose-200' },
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
  const [materia, setMateria] = useState<string | null>(null)
  const [seleccion, setSeleccion] = useState<number | null>(claseInicial)
  const esAlumno = rol === 'ALUMNO'

  // Más nueva primero, sin fiarse del orden en que llegue (el «Última» de cada materia sale de acá).
  const lista = useMemo(() => [...(clases.datos ?? [])].sort((a, b) => b.fecha.localeCompare(a.fecha) || b.hora_inicio.localeCompare(a.hora_inicio)), [clases.datos])
  const cursos = useMemo(() => [...new Map(lista.map((c) => [c.curso_id, c.curso_nombre]))].sort((a, b) => a[1].localeCompare(b[1], 'es')), [lista])
  const visibles = curso ? lista.filter((c) => c.curso_id === curso) : lista
  // El alumno ve sus clases separadas por materia.
  const materias = useMemo(() => {
    const por = new Map<string, { n: number; ultima: string }>()
    for (const c of lista) {
      const m = por.get(nombreMateria(c))
      por.set(nombreMateria(c), { n: (m?.n ?? 0) + 1, ultima: m?.ultima ?? c.fecha })
    }
    return [...por].sort((a, b) => a[0].localeCompare(b[0], 'es'))
  }, [lista])
  const porMaterias = esAlumno && materias.length > 1

  // El foco acompaña al alumno: al entrar a una materia queda en su título y al volver, en su botón.
  const cabecera = useRef<HTMLHeadingElement>(null)
  const botonesMateria = useRef(new Map<string, HTMLButtonElement>())
  const materiaPrevia = useRef<string | null>(null)
  useEffect(() => {
    if (materia) cabecera.current?.focus()
    else if (materiaPrevia.current) botonesMateria.current.get(materiaPrevia.current)?.focus()
    materiaPrevia.current = materia
  }, [materia])
  // El gesto «atrás» del celular sube un nivel (clase → materia → materias) en vez de salirse de la aplicación.
  const scrollAntes = useRef(0)
  const empujadas = useRef(0)
  useEffect(() => {
    if (!esAlumno) return
    const alAtras = (e: PopStateEvent) => {
      const nivel = e.state?.claseidia
      empujadas.current = nivel === 'clase' ? empujadas.current : nivel === 'materia' ? 1 : 0
      if (nivel !== 'clase') setSeleccion(null)
      if (nivel !== 'clase' && nivel !== 'materia') setMateria(null)
      if (nivel === 'materia') requestAnimationFrame(() => window.scrollTo(0, scrollAntes.current)) // vuelve de una clase: donde estaba
    }
    window.addEventListener('popstate', alAtras)
    return () => window.removeEventListener('popstate', alAtras)
  }, [esAlumno])
  // Al salir de «Clases» (otra pestaña, cerrar sesión) se retiran las entradas que dejó, para que «atrás» no tenga pasos que no hacen nada.
  // Las páginas de privacidad y términos viven en el historial por su hash: ahí no se toca nada.
  useEffect(() => () => {
    if (empujadas.current > 0 && !window.location.hash.startsWith('#/')) window.history.go(-empujadas.current)
  }, [])

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

  // Un profesor con varios cursos ve las clases agrupadas por curso. El alumno con varias materias primero elige la materia
  // (una pantalla de botones grandes) y después ve solo las clases de esa materia.
  const eligiendoMateria = porMaterias && materia === null
  const delAlumno = porMaterias ? lista.filter((c) => nombreMateria(c) === materia) : visibles
  const grupos: [string | null, ClaseResumen[]][] =
    !esAlumno && !curso && cursos.length > 1
      ? cursos.map(([id, nombre]) => [nombre, visibles.filter((c) => c.curso_id === id)])
      : [[null, esAlumno ? delAlumno : visibles]]
  // Cada nivel que se abre deja una entrada en el historial, para que «atrás» suba de a un nivel; si no la hay (se llegó
  // desde el Horario), se cambia el estado directo. La lista de una materia empieza arriba aunque la pantalla anterior estuviera a medio recorrer.
  const elegirMateria = (m: string | null) => {
    if (m === null && window.history.state?.claseidia === 'materia') return window.history.back()
    if (m !== null && esAlumno) {
      window.history.pushState({ claseidia: 'materia' }, '')
      empujadas.current++
    }
    setMateria(m)
    window.scrollTo(0, 0)
  }
  const abrirClase = (id: number) => {
    scrollAntes.current = window.scrollY
    if (esAlumno) {
      window.history.pushState({ claseidia: 'clase' }, '')
      empujadas.current++
    }
    setSeleccion(id)
  }
  // Al volver de una clase se queda en la lista de su materia (no en la pantalla de materias).
  const volver = () => {
    if (window.history.state?.claseidia === 'clase') return window.history.back()
    const c = lista.find((x) => x.id === seleccion)
    if (porMaterias && c) setMateria(nombreMateria(c))
    setSeleccion(null)
  }

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
        {eligiendoMateria ? (
          <ul className="grid grid-cols-2 gap-3">
            {materias.map(([m, { n, ultima }]) => (
              <li key={m}>
                <button
                  ref={(el) => void (el ? botonesMateria.current.set(m, el) : botonesMateria.current.delete(m))}
                  onClick={() => elegirMateria(m)}
                  className="flex h-full min-h-32 w-full flex-col justify-between rounded-2xl border bg-card p-4 text-left transition-colors hover:bg-muted/50"
                >
                  <span aria-hidden className={cn('size-4 rounded-full border-2', colorAsignatura(m))} />
                  <span>
                    <span className="block text-base font-semibold leading-tight [overflow-wrap:anywhere]">{m}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">{n} {n === 1 ? 'clase' : 'clases'}</span>
                    <span className="block text-xs text-muted-foreground">Última: {diaClase(ultima).toLowerCase()}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <>
            {porMaterias && (
              <div className="sticky top-14 z-10 -mx-4 flex items-center gap-1 border-b bg-background/95 px-4 backdrop-blur short:top-11 desk:top-0 desk:mx-0 desk:px-0">
                <button onClick={() => elegirMateria(null)} className="-ml-2 flex h-11 shrink-0 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-foreground">
                  <ArrowLeft className="size-4" /> Materias
                </button>
                <h2 ref={cabecera} tabIndex={-1} className="flex min-w-0 flex-1 items-center gap-2 text-base font-semibold outline-none desk:text-lg">
                  <span aria-hidden className={cn('size-3.5 shrink-0 rounded-full border-2', colorAsignatura(materia))} />
                  <span className="truncate" title={materia ?? undefined}>{materia}</span>
                </h2>
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
                      <FilaClase c={c} mostrarEstado={!esAlumno} fechaPrimero={porMaterias} seleccionada={c.id === seleccion} onClick={() => abrirClase(c.id)} />
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </>
        )}
      </div>

      <div className={cn('desk:sticky desk:top-6', !seleccion && 'hidden desk:block')}>
        {seleccion ? (
          <DetalleClase key={seleccion} id={seleccion} onVolver={volver} onCambio={clases.recargar} />
        ) : (
          <div className="rounded-2xl border border-dashed p-10">
            <Vacio icono={FileText} titulo="Elige una clase">Verás su resumen, los puntos clave, la hoja de repaso y las tarjetas de estudio.</Vacio>
          </div>
        )}
      </div>
    </div>
  )
}

const nombreMateria = (c: ClaseResumen) => c.asignatura?.trim() || 'Sin materia'

/** «Hoy» y «Ayer» se entienden más rápido que una fecha; el resto, «vie, 27 nov». */
function diaClase(fecha: string): string {
  const dia = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
  const f = new Date(`${fecha}T00:00:00`)
  const hoy = new Date()
  const ayer = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() - 1)
  if (dia(f) === dia(hoy)) return 'Hoy'
  if (dia(f) === dia(ayer)) return 'Ayer'
  return f.getFullYear() === hoy.getFullYear() ? fechaCorta(fecha) : `${fechaCorta(fecha)} ${f.getFullYear()}`
}

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: string }) {
  return (
    <button
      role="tab"
      aria-selected={activo}
      onClick={onClick}
      className={cn(
        'h-11 shrink-0 rounded-full px-4 text-sm font-medium transition-colors desk:h-8 desk:px-3.5',
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

function FilaClase({ c, mostrarEstado, fechaPrimero, seleccionada, onClick }: { c: ClaseResumen; mostrarEstado: boolean; fechaPrimero: boolean; seleccionada: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-current={seleccionada ? 'true' : undefined}
      className={cn(
        'flex w-full items-center gap-3 rounded-xl px-3.5 py-3 text-left',
        fechaPrimero
          ? cn('border bg-card transition-colors hover:bg-muted/50', seleccionada && 'border-primary bg-primary/5')
          : cn('border-l-4 transition-shadow hover:shadow-sm', colorAsignatura(c.asignatura), seleccionada && 'ring-2 ring-primary'),
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className={cn('truncate text-base font-semibold leading-tight', fechaPrimero && 'first-letter:uppercase')}>{fechaPrimero ? diaClase(c.fecha) : c.asignatura}</p>
          {(mostrarEstado || c.estado === 'provisoria') && <Estado estado={c.estado} comoAlumno={!mostrarEstado} />}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs opacity-75">
          {!fechaPrimero && <span className="font-medium capitalize">{fechaCorta(c.fecha)}</span>}
          <span className="flex items-center gap-1"><Clock className="size-3" /> {hhmm(c.hora_inicio)}–{hhmm(c.hora_fin)}</span>
          {fechaPrimero && ['Hoy', 'Ayer'].includes(diaClase(c.fecha)) && <span className="first-letter:uppercase">{fechaCorta(c.fecha)}</span>}
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
  const [editandoMapa, setEditandoMapa] = useState(false)
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
      {k && !editando && <DescargarClase clase={c} esProfesor={esProfesor} />}

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
          {(k.mapa.length > 0 || (esProfesor && editandoMapa)) && (
            <Seccion
              icono={Network}
              titulo="Mapa conceptual"
              nota={esProfesor ? 'La IA lo propone solo con un modelo grande, y puede equivocarse: corrígelo o quítalo antes de aprobar.' : 'Generado automáticamente a partir de la clase: puede tener errores.'}
            >
              {editandoMapa ? (
                <EditorMapa claseId={id} inicial={k.mapa} onCancelar={() => setEditandoMapa(false)} onGuardado={() => { setEditandoMapa(false); clase.recargar() }} />
              ) : (
                <div className="space-y-3">
                  <MapaDibujado relaciones={k.mapa} />
                  {esProfesor && (
                    <Button variant="outline" className="h-10 desk:h-8" onClick={() => setEditandoMapa(true)}>
                      <Pencil /> Corregir el mapa
                    </Button>
                  )}
                </div>
              )}
            </Seccion>
          )}
          {esProfesor && k.mapa.length === 0 && !editandoMapa && (
            <Button variant="outline" className="h-11 w-full desk:h-9 desk:w-auto" onClick={() => setEditandoMapa(true)}>
              <Network /> Agregar un mapa conceptual
            </Button>
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
  ambar: 'bg-amber-50 dark:bg-amber-950/40 text-amber-950 dark:text-amber-100 ring-amber-200 dark:ring-amber-800',
  naranja: 'bg-orange-50 dark:bg-orange-950/40 text-orange-950 dark:text-orange-100 ring-orange-300 dark:ring-orange-700',
  rosa: 'bg-rose-50 dark:bg-rose-950/40 text-rose-950 dark:text-rose-100 ring-rose-200 dark:ring-rose-800',
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
