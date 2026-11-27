/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useState, type FormEvent } from 'react'
import { ArrowRightLeft, Check, Loader2, Pencil, Trash2, TriangleAlert, UserMinus } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { FilaConReset } from '@/components/FilaConReset'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api, type AlumnoDeCurso, type Curso } from '@/lib/api'

type Accion = 'nombre' | 'mover' | 'quitar' | 'eliminar'

interface FilaProps {
  alumno: AlumnoDeCurso
  cursoId: number
  /** Los demás cursos del colegio, para moverlo. */
  otrosCursos: Curso[]
  /** UTP: además de corregir el nombre, mueve, saca y elimina. El profesor solo corrige el nombre y revisa las marcas. */
  completo: boolean
  onCambio: (aviso: string) => void
}

/** Una fila de alumno para el UTP (los alumnos se inscriben solos con el código del curso): corregir nombre, mover de curso, sacarlo del curso o eliminarlo. */
export function FilaAlumno({ alumno, cursoId, otrosCursos, completo, onCambio }: FilaProps) {
  const [accion, setAccion] = useState<Accion | null>(null)
  const [nombre, setNombre] = useState(alumno.nombre)
  const [destino, setDestino] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const abrir = (a: Accion) => {
    setError(null)
    setAccion(accion === a ? null : a)
  }
  const ejecutar = async (peticion: () => Promise<unknown>, aviso: string) => {
    setEnviando(true)
    setError(null)
    try {
      await peticion()
      setAccion(null)
      onCambio(aviso)
    } catch (e) {
      setError((e as Error).message)
    }
    setEnviando(false)
  }

  const guardarNombre = (e: FormEvent) => {
    e.preventDefault()
    if (!nombre.trim()) return setError('Escribe un nombre.')
    return ejecutar(() => api(`/usuarios/${alumno.id}`, { metodo: 'PUT', cuerpo: { nombre: nombre.trim() } }), `El nombre quedó como ${nombre.trim()}.`)
  }
  const mover = () => {
    const curso = otrosCursos.find((c) => String(c.id) === destino)
    if (!curso) return setError('Elige el curso de destino.')
    return ejecutar(
      () => api(`/cursos/${cursoId}/alumnos/${alumno.id}/mover`, { metodo: 'POST', cuerpo: { curso_destino_id: curso.id } }),
      `${alumno.nombre} pasó a ${curso.nombre}.`,
    )
  }

  const boton = (a: Accion, etiqueta: string, icono: React.ReactNode) => (
    <Button variant={accion === a ? 'secondary' : 'outline'} size="icon-lg" aria-label={`${etiqueta}: ${alumno.nombre}`} title={etiqueta} aria-expanded={accion === a} onClick={() => abrir(a)}>
      {icono}
    </Button>
  )

  return (
    <FilaConReset
      usuarioId={alumno.id}
      nombre={alumno.nombre}
      tipo="pin"
      info={
        <>
          <p className="truncate font-medium">{alumno.nombre}</p>
          <p className="text-xs tabular-nums text-muted-foreground">{alumno.rut}</p>
          {alumno.revisar_nombre && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-amber-800 dark:text-amber-200">
              <TriangleAlert className="size-3.5" aria-hidden /> Revisar nombre: podría ser una broma
            </p>
          )}
        </>
      }
      accion={
        <>
          {alumno.revisar_nombre && (
            <Button variant="outline" className="h-10 desk:h-8" disabled={enviando} onClick={() => ejecutar(() => api(`/usuarios/${alumno.id}/nombre-revisado`, { metodo: 'POST' }), `El nombre de ${alumno.nombre} quedó como correcto.`)} aria-label={`El nombre de ${alumno.nombre} está bien`}>
              <Check /> Está bien
            </Button>
          )}
          {boton('nombre', 'Corregir el nombre', <Pencil />)}
          {completo && boton('mover', 'Mover de curso', <ArrowRightLeft />)}
          {completo && boton('quitar', 'Sacar del curso', <UserMinus />)}
          {completo && boton('eliminar', 'Eliminar al alumno', <Trash2 />)}
        </>
      }
      bajo={
        accion && (
          <div className="space-y-2 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
            {accion === 'nombre' && (
              <form onSubmit={guardarNombre} className="flex gap-2">
                <Input aria-label={`Nuevo nombre de ${alumno.nombre}`} autoFocus value={nombre} maxLength={120} onChange={(e) => setNombre(e.target.value)} className="h-10 min-w-0 flex-1 text-base desk:h-8 desk:text-sm" />
                <Button type="submit" size="icon-lg" disabled={enviando} aria-label="Guardar el nombre">
                  {enviando ? <Loader2 className="animate-spin" /> : <Check />}
                </Button>
              </form>
            )}
            {accion === 'mover' &&
              (otrosCursos.length === 0 ? (
                <p className="text-muted-foreground">No hay otros cursos: crea primero el curso de destino.</p>
              ) : (
                <div className="flex gap-2">
                  <select
                    aria-label={`Curso de destino de ${alumno.nombre}`}
                    value={destino}
                    onChange={(e) => setDestino(e.target.value)}
                    className="h-10 min-w-0 flex-1 rounded-lg border bg-background px-2 text-base desk:h-8 desk:text-sm"
                  >
                    <option value="">Elige el curso…</option>
                    {otrosCursos.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.nombre}
                      </option>
                    ))}
                  </select>
                  <Button className="h-10 desk:h-8" disabled={enviando} onClick={mover}>
                    {enviando && <Loader2 className="animate-spin" />} Mover
                  </Button>
                </div>
              ))}
            {accion === 'quitar' && (
              <>
                <p>¿Sacar a {alumno.nombre} de este curso? Conserva su cuenta, pero deja de ver las clases de este curso.</p>
                <Button disabled={enviando} className="h-10 desk:h-8" onClick={() => ejecutar(() => api(`/cursos/${cursoId}/alumnos/${alumno.id}`, { metodo: 'DELETE' }), `${alumno.nombre} salió del curso.`)}>
                  {enviando && <Loader2 className="animate-spin" />} Sí, sacarlo
                </Button>
              </>
            )}
            {accion === 'eliminar' && (
              <>
                <p className="text-destructive">¿Eliminar a {alumno.nombre}? Se borra su cuenta y no se puede deshacer. Para cambiarlo de sección, mejor muévelo.</p>
                <Button variant="destructive" disabled={enviando} className="h-10 desk:h-8" onClick={() => ejecutar(() => api(`/usuarios/${alumno.id}`, { metodo: 'DELETE' }), `${alumno.nombre} fue eliminado.`)}>
                  {enviando && <Loader2 className="animate-spin" />} Sí, eliminar
                </Button>
              </>
            )}
            <ErrorForm mensaje={error} />
          </div>
        )
      }
    />
  )
}
