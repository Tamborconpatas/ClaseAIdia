import { useMemo, useState, type FormEvent } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { BookOpen, Check, Copy, Loader2, Pencil, Plus, QrCode, Sparkles, Trash2, Users } from 'lucide-react'
import { Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { FilaConReset } from '@/components/FilaConReset'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api, type AlumnoDeCurso, type Curso } from '@/lib/api'
import { cargarBloques } from '@/lib/datos'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { cn } from '@/lib/utils'

interface Props {
  /** Solo el UTP crea, renombra y elimina cursos. */
  esUtp: boolean
  /** Profesor: ve qué asignaturas dicta en cada curso y puede saltar a sus clases. */
  esProfesor: boolean
  onVerClases: (cursoId: number) => void
}

type Panel = { cursoId: number; tipo: 'codigo' | 'alumnos' }

export function Cursos({ esUtp, esProfesor, onVerClases }: Props) {
  const { usuario } = useSesion()
  const cursos = useCarga(() => api<Curso[]>('/cursos'), [])
  const [panel, setPanel] = useState<Panel | null>(null)
  const [renombrando, setRenombrando] = useState<number | null>(null)
  const [borrando, setBorrando] = useState<number | null>(null)
  const lista = useMemo(() => cursos.datos ?? [], [cursos.datos])

  // Para el profesor: qué asignaturas dicta en cada curso (se deduce de sus bloques).
  const bloques = useCarga(() => (esProfesor ? cargarBloques(lista.map((c) => c.id)) : Promise.resolve([])), [esProfesor, lista.map((c) => c.id).join(',')])
  const asignaturas = useMemo(() => {
    const porCurso = new Map<number, Set<string>>()
    for (const b of bloques.datos ?? []) {
      if (b.tipo !== 'CLASE' || b.profesor_id !== usuario?.id || !b.asignatura) continue
      porCurso.set(b.curso_id, (porCurso.get(b.curso_id) ?? new Set()).add(b.asignatura))
    }
    return porCurso
  }, [bloques.datos, usuario?.id])

  if (cursos.cargando && !cursos.datos) return <Cargando />
  if (cursos.error) return <ErrorForm mensaje={cursos.error} />

  const alternar = (cursoId: number, tipo: Panel['tipo']) =>
    setPanel(panel?.cursoId === cursoId && panel.tipo === tipo ? null : { cursoId, tipo })

  return (
    <div className="space-y-5">
      {esUtp && (
        <NuevoCurso
          onCreado={(id) => {
            cursos.recargar()
            setPanel({ cursoId: id, tipo: 'codigo' })
          }}
        />
      )}

      {lista.length === 0 ? (
        <Vacio icono={BookOpen} titulo="Sin cursos">
          {esUtp ? 'Crea el primer curso para generar su código de invitación.' : 'Todavía no tienes cursos asignados. Cuando UTP te asigne bloques, aparecerán acá.'}
        </Vacio>
      ) : (
        <ul className="grid gap-3 desk:grid-cols-2 xl:grid-cols-3">
          {lista.map((c) => {
            const abierto = panel?.cursoId === c.id
            return (
              <li key={c.id} className={cn('rounded-2xl border bg-card p-4', abierto && 'desk:col-span-2 xl:col-span-3')}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-secondary text-sm font-semibold text-secondary-foreground">
                      {c.nombre.slice(0, 3)}
                    </span>
                    {renombrando === c.id ? (
                      <Renombrar
                        curso={c}
                        onListo={() => {
                          setRenombrando(null)
                          cursos.recargar()
                        }}
                        onCancelar={() => setRenombrando(null)}
                      />
                    ) : (
                      <div className="min-w-0">
                        <p className="truncate text-base font-semibold">{c.nombre}</p>
                        {esProfesor && (
                          <p className="truncate text-sm text-muted-foreground">{[...(asignaturas.get(c.id) ?? [])].join(' · ') || ' '}</p>
                        )}
                      </div>
                    )}
                  </div>
                  {esUtp && renombrando !== c.id && (
                    <div className="flex shrink-0 gap-1">
                      <Button variant="ghost" size="icon-lg" aria-label={`Renombrar el curso ${c.nombre}`} onClick={() => setRenombrando(c.id)}>
                        <Pencil />
                      </Button>
                      <Button variant="ghost" size="icon-lg" aria-label={`Eliminar el curso ${c.nombre}`} onClick={() => setBorrando(borrando === c.id ? null : c.id)}>
                        <Trash2 />
                      </Button>
                    </div>
                  )}
                </div>

                {borrando === c.id && (
                  <BorrarCurso
                    curso={c}
                    onListo={() => {
                      setBorrando(null)
                      setPanel(null)
                      cursos.recargar()
                    }}
                    onCancelar={() => setBorrando(null)}
                  />
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  {esProfesor && (
                    <Button className="h-10 desk:h-8" onClick={() => onVerClases(c.id)}>
                      <Sparkles /> Ver clases
                    </Button>
                  )}
                  <Button variant={abierto && panel?.tipo === 'alumnos' ? 'secondary' : 'outline'} className="h-10 desk:h-8" onClick={() => alternar(c.id, 'alumnos')} aria-expanded={abierto && panel?.tipo === 'alumnos'}>
                    <Users /> Alumnos
                  </Button>
                  <Button variant={abierto && panel?.tipo === 'codigo' ? 'secondary' : 'outline'} className="h-10 desk:h-8" onClick={() => alternar(c.id, 'codigo')} aria-expanded={abierto && panel?.tipo === 'codigo'}>
                    <QrCode /> Código
                  </Button>
                </div>
                {abierto && panel?.tipo === 'codigo' && <CodigoCurso cursoId={c.id} />}
                {abierto && panel?.tipo === 'alumnos' && <AlumnosDelCurso cursoId={c.id} />}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function NuevoCurso({ onCreado }: { onCreado: (id: number) => void }) {
  const { usuario } = useSesion()
  const [nombre, setNombre] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const crear = async (e: FormEvent) => {
    e.preventDefault()
    if (!nombre.trim() || !usuario) return
    setEnviando(true)
    setError(null)
    try {
      const c = await api<Curso>('/cursos', { metodo: 'POST', cuerpo: { nombre: nombre.trim(), colegio_id: usuario.colegio_id } })
      setNombre('')
      onCreado(c.id)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={crear} className="space-y-2">
      <div className="flex gap-2">
        <Input
          aria-label="Nombre del curso nuevo"
          placeholder="Nuevo curso, p. ej. 8°C"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          maxLength={60}
          className="h-11 flex-1 text-base desk:h-9 desk:max-w-xs desk:text-sm"
        />
        <Button type="submit" disabled={enviando || !nombre.trim()} className="h-11 px-4 desk:h-9">
          {enviando ? <Loader2 className="animate-spin" /> : <Plus />} Crear
        </Button>
      </div>
      <ErrorForm mensaje={error} />
    </form>
  )
}

function Renombrar({ curso, onListo, onCancelar }: { curso: Curso; onListo: () => void; onCancelar: () => void }) {
  const [nombre, setNombre] = useState(curso.nombre)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const guardar = async (e: FormEvent) => {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      await api(`/cursos/${curso.id}`, { metodo: 'PUT', cuerpo: { nombre } })
      onListo()
    } catch (err) {
      setError((err as Error).message)
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={guardar} className="min-w-0 flex-1 space-y-1.5">
      <div className="flex gap-2">
        <Input aria-label="Nuevo nombre del curso" autoFocus value={nombre} maxLength={60} onChange={(e) => setNombre(e.target.value)} className="h-10 min-w-0 flex-1 text-base desk:h-8 desk:text-sm" />
        <Button type="submit" size="icon-lg" disabled={enviando || !nombre.trim()} aria-label="Guardar el nombre">
          {enviando ? <Loader2 className="animate-spin" /> : <Check />}
        </Button>
        <Button type="button" variant="ghost" className="h-10 desk:h-8" onClick={onCancelar}>
          Cancelar
        </Button>
      </div>
      <ErrorForm mensaje={error} />
    </form>
  )
}

function BorrarCurso({ curso, onListo, onCancelar }: { curso: Curso; onListo: () => void; onCancelar: () => void }) {
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const borrar = async () => {
    setEnviando(true)
    setError(null)
    try {
      await api(`/cursos/${curso.id}`, { metodo: 'DELETE' })
      onListo()
    } catch (err) {
      setError((err as Error).message)
      setEnviando(false)
    }
  }

  return (
    <div className="mt-3 space-y-2 rounded-xl bg-destructive/10 p-3.5 text-sm">
      <p className="text-destructive">¿Eliminar el curso {curso.nombre}? Solo se puede si no tiene bloques ni alumnos.</p>
      <ErrorForm mensaje={error} />
      <div className="flex gap-2">
        <Button variant="destructive" className="h-10 flex-1 desk:h-8 desk:flex-none" disabled={enviando} onClick={borrar}>
          {enviando && <Loader2 className="animate-spin" />} Sí, eliminar
        </Button>
        <Button variant="outline" className="h-10 desk:h-8" onClick={onCancelar}>
          No
        </Button>
      </div>
    </div>
  )
}

/** Alumnos inscritos, con el reseteo de PIN: da un código de un solo uso que se entrega en persona. */
function AlumnosDelCurso({ cursoId }: { cursoId: number }) {
  const alumnos = useCarga(() => api<AlumnoDeCurso[]>(`/cursos/${cursoId}/alumnos`), [cursoId])
  if (alumnos.cargando) return <Cargando />
  if (alumnos.error) return <ErrorForm mensaje={alumnos.error} />
  const lista = alumnos.datos ?? []
  if (lista.length === 0) {
    return <p className="mt-4 rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">Todavía no hay alumnos inscritos. Comparte el código del curso para que se unan.</p>
  }
  return (
    <ul className="mt-4 divide-y rounded-xl bg-muted/40" aria-label="Alumnos del curso">
      {lista.map((a) => (
        <FilaConReset
          key={a.id}
          usuarioId={a.id}
          nombre={a.nombre}
          tipo="pin"
          info={
            <>
              <p className="truncate font-medium">{a.nombre}</p>
              <p className="text-xs tabular-nums text-muted-foreground">{a.rut}</p>
            </>
          }
        />
      ))}
    </ul>
  )
}

/** Código y QR para que los alumnos se unan: el QR abre la pantalla de registro con el código ya puesto. */
function CodigoCurso({ cursoId }: { cursoId: number }) {
  const codigo = useCarga(() => api<{ codigo_invitacion: string }>(`/cursos/${cursoId}/codigo`), [cursoId])
  const [copiado, setCopiado] = useState(false)

  if (codigo.cargando) return <Cargando />
  if (codigo.error || !codigo.datos) return <ErrorForm mensaje={codigo.error} />
  const c = codigo.datos.codigo_invitacion
  const enlace = `${window.location.origin}/?unirse=${c}`

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(c)
      setCopiado(true)
      setTimeout(() => setCopiado(false), 1800)
    } catch {
      /* sin permiso de portapapeles: el código está a la vista para copiarlo a mano */
    }
  }

  return (
    <div className="mt-4 flex flex-col items-center gap-5 rounded-xl bg-muted/50 p-5 desk:flex-row desk:items-center desk:gap-8 desk:p-6">
      <div className="rounded-2xl bg-white p-3 shadow-sm ring-1 ring-border">
        <QRCodeSVG value={enlace} size={168} title="Código QR para unirse al curso" />
      </div>
      <div className="space-y-3 text-center desk:text-left">
        <div>
          <p className="text-sm text-muted-foreground">Código del curso</p>
          <p className="font-mono text-4xl font-semibold tracking-[0.2em]">{c}</p>
        </div>
        <Button variant="outline" onClick={copiar} className="h-10 desk:h-8">
          {copiado ? <Check /> : <Copy />} {copiado ? 'Copiado' : 'Copiar código'}
        </Button>
        <p className="max-w-xs text-xs text-muted-foreground">
          Los alumnos pueden escribir el código o escanear el QR con el teléfono: los lleva directo al registro.
        </p>
        {/* El QR lleva la dirección con que se abrió esta página; "localhost" en un teléfono es el propio teléfono. */}
        {['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) && (
          <p className="max-w-xs rounded-lg bg-amber-50 p-2.5 text-xs text-amber-950 ring-1 ring-amber-200">
            <strong>Este QR no funcionará en un teléfono</strong>: abriste la app como «{window.location.hostname}». Ábrela con
            la dirección del servidor en la red del colegio y genera el QR desde ahí. Mientras tanto, los alumnos pueden
            escribir el código.
          </p>
        )}
      </div>
    </div>
  )
}
