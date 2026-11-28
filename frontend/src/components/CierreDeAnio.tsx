/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, CheckCircle2, Loader2, TriangleAlert } from 'lucide-react'
import { Cargando, ErrorForm } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api, type AlumnoDeCurso, type CierreAnioNuevo, type CierreEstado, type CierreHecho, type CierrePlan, type CierreVistaPrevia, type Curso } from '@/lib/api'
import { useCarga } from '@/lib/usar'
import { cn } from '@/lib/utils'

const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

const AvisoIrreversible = () => (
  <div className="flex items-start gap-2.5 rounded-xl bg-amber-50 p-3.5 text-sm text-amber-950 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-100 dark:ring-amber-800">
    <TriangleAlert className="mt-0.5 size-4 shrink-0" />
    <p>Lo que se borra no se puede recuperar desde la aplicación. Justo antes se guarda un respaldo aparte de la base, que permite restaurarlo a mano.</p>
  </div>
)

/** Volver a «Cursos»: primer elemento de las dos pantallas. */
const Volver = ({ onClick, texto = 'Cursos' }: { onClick: () => void; texto?: string }) => (
  <button onClick={onClick} className="-ml-2 flex h-11 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-foreground">
    <ArrowLeft className="size-4" /> {texto}
  </button>
)

/**
 * Primer tiempo: cerrar el año al terminar las clases. Borra todo el material de clases del año (para que el «8.°A» de la generación siguiente no vea las
 * clases de la anterior) y deja las grabaciones en pausa. Los alumnos siguen en su curso: cambian en febrero, al preparar el año nuevo.
 */
export function CerrarElAnio({ onSalir, onTerminado }: { onSalir: () => void; onTerminado: () => void }) {
  const estado = useCarga(() => api<CierreEstado>('/cierre-anio/estado'), [])
  const [confirmo, setConfirmo] = useState(false)
  const [trabajando, setTrabajando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState<CierreHecho | null>(null)
  const titulo = useRef<HTMLHeadingElement>(null)
  useEffect(() => titulo.current?.focus(), [estado.datos, hecho])
  if (estado.error) return <ErrorForm mensaje={estado.error} />
  if (!estado.datos) return <Cargando />
  const e = estado.datos

  const cerrar = async () => {
    setTrabajando(true)
    setError(null)
    try {
      setHecho(await api<CierreHecho>('/cierre-anio/cerrar', { metodo: 'POST', cuerpo: { confirmo: true } }))
    } catch (err) {
      setError((err as Error).message)
    }
    setTrabajando(false)
  }

  if (hecho) {
    return (
      <section aria-label="Año cerrado" className="mx-auto max-w-3xl space-y-4">
        <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="size-5" /><h2 ref={titulo} tabIndex={-1} className="text-lg font-semibold outline-none">Año cerrado</h2></div>
        <ul className="space-y-1.5 rounded-2xl border bg-card p-4 text-sm leading-relaxed">
          <li>Se borró el material de {plural(hecho.clases_borradas, 'clase', 'clases')} del año.</li>
          <li><strong>Las grabaciones están en pausa.</strong> Los alumnos siguen en su curso.</li>
          <li>Cuando llegue el momento de volver a clases, entra a «Cursos» → «Preparar el año nuevo»: ahí decides quién pasa, quién repite y quién se fue, y se reactivan las grabaciones.</li>
          {hecho.respaldo && <li className="text-muted-foreground">Respaldo previo: {hecho.respaldo}, en la carpeta de respaldos.</li>}
        </ul>
        <Button className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" onClick={onTerminado}>Listo</Button>
      </section>
    )
  }

  return (
    <section aria-label="Cerrar el año" className="mx-auto max-w-3xl space-y-4">
      <Volver onClick={onSalir} />
      <div>
        <h2 ref={titulo} tabIndex={-1} className="text-lg font-semibold outline-none">Cerrar el año escolar</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          Hazlo cuando terminen las clases. Se borra el material de las clases del año, para que el curso de la generación siguiente no vea las de la anterior, y las
          grabaciones quedan en pausa. <strong>Los alumnos siguen en su curso</strong>: lo que pasa con ellos se decide en febrero, antes de que empiecen las clases.
        </p>
      </div>
      {e.problemas.length > 0 && (
        <div role="alert" className="space-y-1 rounded-xl bg-destructive/10 p-4 text-sm text-destructive ring-1 ring-destructive/30">
          <p className="font-medium">No se puede cerrar todavía:</p>
          <ul className="list-disc pl-5">{e.problemas.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      )}
      <p className="rounded-2xl border bg-card p-4 text-sm">Se borrará el material de <strong>{plural(e.clases_a_borrar, 'clase', 'clases')}</strong>. El horario se conserva.</p>
      <AvisoIrreversible />
      <label className="flex min-h-11 items-start gap-3 text-sm">
        <input type="checkbox" className="mt-0.5 size-5 shrink-0" checked={confirmo} onChange={(ev) => setConfirmo(ev.target.checked)} />
        Entiendo que se borran las clases del año y que no se puede deshacer.
      </label>
      <ErrorForm mensaje={error} />
      <Button variant="destructive" className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" disabled={!confirmo || e.problemas.length > 0 || trabajando} onClick={() => void cerrar()}>
        {trabajando ? <Loader2 className="animate-spin" /> : null} Cerrar el año escolar
      </Button>
    </section>
  )
}

// ---------------------------------------------------------------------------------------------------------------------

type Decision = { tipo: '' | 'curso' | 'nuevo' | 'egresa'; destinoId?: number; nombre?: string }
type Suerte = 'pasa' | 'repite' | 'se_fue'

const SUERTES: { valor: Suerte; etiqueta: string }[] = [
  { valor: 'pasa', etiqueta: 'Pasa' },
  { valor: 'repite', etiqueta: 'Repite' },
  { valor: 'se_fue', etiqueta: 'Se fue del colegio' },
]

/**
 * Lo que más probablemente se quiere, solo como punto de partida (el UTP siempre puede cambiarlo): «4.° medio» egresa; «8°A» pasa al «9°A» si ya existe y, si no,
 * se propone crearlo con ese nombre.
 */
export function sugerido(c: Curso, todos: Curso[]): Decision {
  const nombre = c.nombre.trim()
  if (/^(4|iv|cuarto)\s*°?\s*(m|medio)\b/i.test(nombre)) return { tipo: 'egresa' }
  const m = /^(\d+)(.*)$/.exec(nombre)
  if (!m) return { tipo: '' }
  const siguiente = `${Number(m[1]) + 1}${m[2]}`
  const destino = todos.find((x) => x.id !== c.id && x.nombre.trim().toLowerCase() === siguiente.toLowerCase())
  return destino ? { tipo: 'curso', destinoId: destino.id } : { tipo: 'nuevo', nombre: siguiente }
}

/**
 * Segundo tiempo: preparar el año nuevo (solo el UTP), cuando las grabaciones están por activarse de nuevo (los alumnos cambian de curso en febrero, antes de
 * que empiecen las clases). En tres pasos: a dónde pasa cada curso, quién no pasa, y una vista previa de todo antes de confirmar. Al confirmar se reactivan las
 * grabaciones. Lo borrado no se puede recuperar (solo con el respaldo que se hace justo antes).
 */
export function PrepararAnioNuevo({ cursos, onSalir, onTerminado }: { cursos: Curso[]; onSalir: () => void; onTerminado: () => void }) {
  const [paso, setPaso] = useState<1 | 2 | 3 | 4>(1)
  const [alumnos, setAlumnos] = useState<Record<number, AlumnoDeCurso[]> | null>(null)
  const [errorCarga, setErrorCarga] = useState<string | null>(null)
  const [decision, setDecision] = useState<Record<number, Decision>>({})
  const [suerte, setSuerte] = useState<Record<number, Suerte>>({})
  const [previa, setPrevia] = useState<CierreVistaPrevia | null>(null)
  const [confirmo, setConfirmo] = useState(false)
  const [trabajando, setTrabajando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<CierreAnioNuevo | null>(null)
  const titulo = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    let vivo = true
    Promise.all(cursos.map(async (c) => [c.id, await api<AlumnoDeCurso[]>(`/cursos/${c.id}/alumnos`)] as const))
      .then((r) => {
        if (!vivo) return
        const por = Object.fromEntries(r)
        setAlumnos(por)
        setDecision(Object.fromEntries(cursos.filter((c) => por[c.id].length > 0).map((c) => [c.id, sugerido(c, cursos)])))
      })
      .catch((e) => vivo && setErrorCarga((e as Error).message))
    return () => {
      vivo = false
    }
  }, [cursos])
  useEffect(() => titulo.current?.focus(), [paso]) // el foco acompaña al cambio de paso

  const conAlumnos = useMemo(() => cursos.filter((c) => (alumnos?.[c.id]?.length ?? 0) > 0).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')), [cursos, alumnos])
  if (errorCarga) return <ErrorForm mensaje={errorCarga} />
  if (!alumnos) return <Cargando />

  const completo = conAlumnos.every((c) => {
    const d = decision[c.id]
    return d && (d.tipo === 'egresa' || (d.tipo === 'curso' && d.destinoId) || (d.tipo === 'nuevo' && (d.nombre ?? '').trim()))
  })
  const plan = (): CierrePlan => ({
    cursos: conAlumnos.map((c) => {
      const d = decision[c.id]
      return d.tipo === 'egresa' ? { curso_id: c.id, egresa: true } : d.tipo === 'curso' ? { curso_id: c.id, destino_id: d.destinoId } : { curso_id: c.id, destino_nuevo: (d.nombre ?? '').trim() }
    }),
    repiten: Object.entries(suerte).filter(([, s]) => s === 'repite').map(([id]) => Number(id)),
    se_van: Object.entries(suerte).filter(([, s]) => s === 'se_fue').map(([id]) => Number(id)),
  })

  const verPrevia = async () => {
    setTrabajando(true)
    setError(null)
    try {
      setPrevia(await api<CierreVistaPrevia>('/cierre-anio/anio-nuevo/vista-previa', { metodo: 'POST', cuerpo: plan() }))
      setConfirmo(false)
      setPaso(3)
    } catch (e) {
      setError((e as Error).message)
    }
    setTrabajando(false)
  }
  const empezar = async () => {
    setTrabajando(true)
    setError(null)
    try {
      setResultado(await api<CierreAnioNuevo>('/cierre-anio/anio-nuevo', { metodo: 'POST', cuerpo: { ...plan(), confirmo: true } }))
      setPaso(4)
    } catch (e) {
      setError((e as Error).message)
    }
    setTrabajando(false)
  }

  const encabezado = (texto: string, ayuda: string) => (
    <div>
      <h2 ref={titulo} tabIndex={-1} className="text-lg font-semibold outline-none">{texto}</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{ayuda}</p>
    </div>
  )

  return (
    <section aria-label="Preparar el año nuevo" className="mx-auto max-w-3xl space-y-5">
      {paso < 4 && (
        <div className="flex items-center justify-between gap-3">
          <Volver onClick={paso === 1 ? onSalir : () => setPaso(paso === 3 && conAlumnos.length === 0 ? 1 : ((paso - 1) as 1 | 2))} texto={paso === 1 ? 'Cursos' : 'Atrás'} />
          <p className="text-sm text-muted-foreground" aria-live="polite">Paso {paso} de 3</p>
        </div>
      )}

      {paso === 1 && (
        <div className="space-y-4">
          {encabezado('¿A dónde pasa cada curso?', 'Cada año los cursos no son el mismo grupo. Elige a qué curso pasan los alumnos de cada uno (ya viene una sugerencia); en el paso siguiente marcas a los que repiten o se fueron. El horario no cambia.')}
          {conAlumnos.length === 0 && <p className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">Ningún curso tiene alumnos todavía: no hay nada que pasar de curso. Sigue para reactivar las grabaciones.</p>}
          <ul className="space-y-3">
            {conAlumnos.map((c) => {
              const d = decision[c.id] ?? { tipo: '' as const }
              const valor = d.tipo === 'curso' ? `curso:${d.destinoId}` : d.tipo
              return (
                <li key={c.id} className="space-y-2 rounded-2xl border bg-card p-4">
                  <label htmlFor={`destino-${c.id}`} className="font-medium">{c.nombre} <span className="text-sm font-normal text-muted-foreground">({plural(alumnos[c.id].length, 'alumno', 'alumnos')})</span></label>
                  <select
                    id={`destino-${c.id}`}
                    value={valor}
                    onChange={(e) => {
                      const v = e.target.value
                      setDecision({ ...decision, [c.id]: v.startsWith('curso:') ? { tipo: 'curso', destinoId: Number(v.slice(6)) } : { tipo: v as Decision['tipo'], nombre: d.nombre } })
                    }}
                    className="block h-11 w-full rounded-lg border bg-background px-3 text-base desk:h-9 desk:text-sm"
                  >
                    <option value="">Elegir a dónde pasa…</option>
                    <optgroup label="Pasa a un curso que ya existe">
                      {cursos.filter((x) => x.id !== c.id).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')).map((x) => <option key={x.id} value={`curso:${x.id}`}>{x.nombre}</option>)}
                    </optgroup>
                    <option value="nuevo">Pasa a un curso nuevo…</option>
                    <option value="egresa">Es el último curso: egresan</option>
                  </select>
                  {d.tipo === 'nuevo' && (
                    <div className="space-y-1">
                      <label htmlFor={`nuevo-${c.id}`} className="block text-sm font-medium">Nombre del curso nuevo</label>
                      <Input id={`nuevo-${c.id}`} value={d.nombre ?? ''} maxLength={40} onChange={(e) => setDecision({ ...decision, [c.id]: { ...d, nombre: e.target.value } })} className="h-11 w-full max-w-48 text-base desk:h-9 desk:text-sm" />
                    </div>
                  )}
                  {d.tipo === 'egresa' && <p className="text-sm text-muted-foreground">Se borran las cuentas de sus alumnos, salvo las de quienes marques como «Repite».</p>}
                </li>
              )
            })}
          </ul>
          <Button className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" disabled={!completo} onClick={() => (conAlumnos.length === 0 ? void verPrevia() : setPaso(2))}>Continuar</Button>
          {!completo && conAlumnos.length > 0 && <p className="text-sm text-muted-foreground">Falta elegir el destino de todos los cursos.</p>}
        </div>
      )}

      {paso === 2 && (
        <div className="space-y-4">
          {encabezado('¿Quién no pasa con su curso?', 'Todos pasan salvo que marques otra cosa. «Repite» se queda en su curso; «Se fue del colegio» (retiro o cambio) borra su cuenta.')}
          {conAlumnos.map((c) => {
            const marcados = alumnos[c.id].filter((a) => (suerte[a.id] ?? 'pasa') !== 'pasa').length
            return (
              <details key={c.id} className="rounded-2xl border bg-card p-4" open={conAlumnos.length === 1}>
                <summary className="cursor-pointer font-medium">
                  {c.nombre} <span className="text-sm font-normal text-muted-foreground">({plural(alumnos[c.id].length, 'alumno', 'alumnos')}{marcados ? `, ${marcados} sin pasar` : ''})</span>
                </summary>
                <ul className="mt-3 divide-y">
                  {alumnos[c.id].map((a) => (
                    <li key={a.id} className="py-2.5">
                      <fieldset>
                        <legend className="text-sm font-medium">{a.nombre} <span className="font-normal text-muted-foreground">{a.rut}</span></legend>
                        <div className="mt-1.5 flex flex-wrap gap-2">
                          {SUERTES.map((s) => {
                            const activo = (suerte[a.id] ?? 'pasa') === s.valor
                            return (
                              <label key={s.valor} className={cn('flex min-h-11 cursor-pointer items-center rounded-lg px-3 text-sm ring-1 ring-border has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring desk:min-h-8', activo ? (s.valor === 'se_fue' ? 'bg-destructive/10 text-red-700 ring-destructive/40 dark:text-destructive' : 'bg-primary text-primary-foreground ring-primary') : 'bg-card text-muted-foreground')}>
                                <input type="radio" className="sr-only" name={`suerte-${a.id}`} checked={activo} onChange={() => setSuerte({ ...suerte, [a.id]: s.valor })} />
                                {s.etiqueta}
                              </label>
                            )
                          })}
                        </div>
                      </fieldset>
                    </li>
                  ))}
                </ul>
              </details>
            )
          })}
          <ErrorForm mensaje={error} />
          <Button className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" disabled={trabajando} onClick={() => void verPrevia()}>
            {trabajando ? <Loader2 className="animate-spin" /> : null} Revisar y confirmar
          </Button>
        </div>
      )}

      {paso === 3 && previa && (
        <div className="space-y-4">
          {encabezado('Revisa antes de empezar el año nuevo', 'Esto es lo que va a pasar. Nada se ha cambiado todavía.')}
          {previa.problemas.length > 0 && (
            <div role="alert" className="space-y-2 rounded-xl bg-destructive/10 p-4 text-sm text-destructive ring-1 ring-destructive/30">
              <p className="font-medium">No se puede continuar todavía:</p>
              <ul className="list-disc space-y-1 pl-5">{previa.problemas.map((p) => <li key={p}>{p}</li>)}</ul>
            </div>
          )}
          <ul className="divide-y rounded-2xl border bg-card px-4 text-sm">
            {previa.cursos.filter((c) => c.alumnos > 0).map((c) => (
              <li key={c.curso_id} className="flex items-center justify-between gap-3 py-2.5">
                <span>{c.curso} <span className="text-muted-foreground">({plural(c.alumnos, 'alumno', 'alumnos')})</span></span>
                <span className="font-medium">{c.destino ? `→ ${c.destino}` : 'sin destino'}</span>
              </li>
            ))}
          </ul>
          <div className="space-y-2 rounded-2xl border bg-card p-4 text-sm leading-relaxed">
            <p><strong>{previa.resumen.pasan}</strong> {previa.resumen.pasan === 1 ? 'alumno pasa' : 'alumnos pasan'} de curso y <strong>{previa.resumen.repiten}</strong> {previa.resumen.repiten === 1 ? 'repite' : 'repiten'}.</p>
            {previa.resumen.cursos_nuevos.length > 0 && <p>Se crean los cursos: {previa.resumen.cursos_nuevos.join(', ')}.</p>}
            <p>Se borran <strong>{plural(previa.resumen.cuentas_a_borrar, 'cuenta', 'cuentas')}</strong> ({previa.resumen.egresan} por egresar y {previa.resumen.se_van} por irse del colegio).</p>
            <p>Los {previa.resumen.codigos_nuevos} cursos reciben un código de invitación nuevo, las grabaciones se activan de nuevo y el horario se conserva.</p>
          </div>
          <AvisoIrreversible />
          <label className="flex min-h-11 items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-5 shrink-0" checked={confirmo} onChange={(e) => setConfirmo(e.target.checked)} />
            Entiendo que se borran las cuentas indicadas y que no se puede deshacer.
          </label>
          <ErrorForm mensaje={error} />
          <Button variant="destructive" className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" disabled={!confirmo || previa.problemas.length > 0 || trabajando} onClick={() => void empezar()}>
            {trabajando ? <Loader2 className="animate-spin" /> : null} Empezar el año nuevo
          </Button>
        </div>
      )}

      {paso === 4 && resultado && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="size-5" /><h2 ref={titulo} tabIndex={-1} className="text-lg font-semibold outline-none">Año nuevo listo</h2></div>
          <ul className="space-y-1.5 rounded-2xl border bg-card p-4 text-sm leading-relaxed">
            <li>{plural(resultado.resumen.pasan, 'alumno pasó', 'alumnos pasaron')} de curso y {resultado.resumen.repiten} {resultado.resumen.repiten === 1 ? 'repite' : 'repiten'}.</li>
            <li>Se borraron {plural(resultado.resumen.cuentas_a_borrar, 'cuenta', 'cuentas')}.</li>
            <li><strong>Las grabaciones están activadas de nuevo.</strong></li>
            {resultado.respaldo && <li className="text-muted-foreground">Respaldo previo: {resultado.respaldo}, en la carpeta de respaldos.</li>}
          </ul>
          <div>
            <h3 className="text-sm font-semibold">Códigos nuevos para los alumnos que entran</h3>
            <p className="text-sm text-muted-foreground">Los códigos de antes ya no sirven. También los ves en «Cursos» → «Código».</p>
            <ul className="mt-2 divide-y rounded-2xl border bg-card px-4 text-sm">
              {resultado.codigos.map((c) => (
                <li key={c.curso} className="flex items-center justify-between gap-3 py-2.5"><span>{c.curso}</span><code className="rounded bg-muted px-2 py-0.5 font-mono text-sm tracking-wider">{c.codigo}</code></li>
              ))}
            </ul>
          </div>
          <Button className="h-auto min-h-11 w-full whitespace-normal py-2 desk:min-h-9 desk:w-auto" onClick={onTerminado}>Listo</Button>
        </div>
      )}
    </section>
  )
}
