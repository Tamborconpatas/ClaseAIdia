import { useMemo, useState, type FormEvent } from 'react'
import { CheckCircle2, Info, Loader2, UserCheck, UserPlus, UserX, Users } from 'lucide-react'
import { Campo, Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { FilaConReset } from '@/components/FilaConReset'
import { Button } from '@/components/ui/button'
import { api, type Rol, type Usuario } from '@/lib/api'
import { formatearRut, rutParaApi } from '@/lib/rut'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { errorPassword, errorRut } from '@/lib/validar'
import { cn } from '@/lib/utils'

const ETIQUETA: Record<'PROFESOR' | 'UTP', string> = { PROFESOR: 'Profesor', UTP: 'UTP' }

/** El UTP ve al personal del colegio (profesores y UTP), da de alta a los nuevos y les resetea la contraseña. */
export function Personal() {
  const { usuario } = useSesion()
  const personal = useCarga(() => api<Usuario[]>('/usuarios'), [])
  const [creado, setCreado] = useState<string | null>(null)
  const lista = useMemo(
    () =>
      (personal.datos ?? [])
        .filter((u) => u.roles.includes('PROFESOR') || u.roles.includes('UTP'))
        .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
    [personal.datos],
  )
  const hayOtroUtp = lista.some((u) => u.roles.includes('UTP') && u.activo && u.id !== usuario?.id)

  return (
    <div className="space-y-6 desk:grid desk:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] desk:items-start desk:gap-8 desk:space-y-0">
      <FormPersonal
        onCreado={(nombre) => {
          setCreado(nombre)
          personal.recargar()
        }}
        mensajeCreado={creado}
        onCerrarMensaje={() => setCreado(null)}
      />

      <section aria-label="Personal del colegio" className="space-y-3">
        {personal.cargando && !personal.datos ? (
          <Cargando />
        ) : personal.error ? (
          <ErrorForm mensaje={personal.error} />
        ) : lista.length === 0 ? (
          <Vacio icono={Users} titulo="Sin personal">
            Agrega al primero con el formulario. Después podrás asignarle bloques en el Horario.
          </Vacio>
        ) : (
          <ul className="divide-y rounded-2xl border bg-card" aria-label="Personal">
            {lista.map((p) => (
              <FilaPersonal key={p.id} persona={p} esYo={p.id === usuario?.id} onCambio={personal.recargar} />
            ))}
          </ul>
        )}

        <div className="flex gap-2.5 rounded-xl bg-muted/60 p-3.5 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          <p>
            Si alguien olvida su contraseña, genera un código con «Resetear contraseña». Si alguien deja el colegio, «Desactivar» le corta el acceso sin borrar su historial. Tú no puedes resetear ni desactivar tu cuenta:{' '}
            {hayOtroUtp
              ? 'pídeselo a otro UTP.'
              : 'hoy eres el único UTP, así que agrega a otro (rol UTP) para tener respaldo. Si igual la olvidas, quien administra el servidor puede restablecerla desde su consola con «python -m scripts.restablecer_utp ' + (usuario?.rut ?? 'TU-RUT') + '».'}
          </p>
        </div>
      </section>
    </div>
  )
}

function FilaPersonal({ persona: p, esYo, onCambio }: { persona: Usuario; esYo: boolean; onCambio: () => void }) {
  const [confirmando, setConfirmando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cambiar = async () => {
    setEnviando(true)
    setError(null)
    try {
      await api(`/usuarios/${p.id}/${p.activo ? 'desactivar' : 'activar'}`, { metodo: 'POST' })
      setConfirmando(false)
      onCambio()
    } catch (e) {
      setError((e as Error).message)
    }
    setEnviando(false)
  }

  return (
    <FilaConReset
      usuarioId={p.id}
      nombre={p.nombre}
      tipo="password"
      puedeResetear={!esYo && p.activo}
      info={
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <p className={cn('truncate font-medium', !p.activo && 'text-muted-foreground')}>{p.nombre}</p>
          {p.roles.includes('UTP') && <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">UTP</span>}
          {!p.activo && <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">Desactivado</span>}
          {esYo && <span className="text-xs text-muted-foreground">(tú)</span>}
          <p className="w-full text-xs tabular-nums text-muted-foreground">{p.rut}</p>
        </div>
      }
      accion={
        !esYo &&
        !confirmando && (
          <Button variant="ghost" className="h-10 desk:h-8" onClick={() => setConfirmando(true)} aria-label={`${p.activo ? 'Desactivar' : 'Reactivar'} a ${p.nombre}`}>
            {p.activo ? <UserX /> : <UserCheck />} {p.activo ? 'Desactivar' : 'Reactivar'}
          </Button>
        )
      }
      bajo={
        <>
          {confirmando && (
            <div className="space-y-2 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
              <p>
                {p.activo
                  ? `¿Desactivar a ${p.nombre}? Dejará de poder entrar, incluso si tiene la sesión abierta. Su nombre se conserva en horarios y clases, y puedes reactivarlo cuando quieras.`
                  : `¿Reactivar a ${p.nombre}? Volverá a poder entrar con su contraseña.`}
              </p>
              <div className="flex gap-2">
                <Button className="h-10 flex-1 desk:h-8 desk:flex-none" disabled={enviando} onClick={cambiar}>
                  {enviando && <Loader2 className="animate-spin" />} {p.activo ? 'Sí, desactivar' : 'Sí, reactivar'}
                </Button>
                <Button variant="ghost" className="h-10 desk:h-8" disabled={enviando} onClick={() => setConfirmando(false)}>
                  No
                </Button>
              </div>
            </div>
          )}
          <ErrorForm mensaje={error} />
        </>
      }
    />
  )
}

function FormPersonal({ onCreado, mensajeCreado, onCerrarMensaje }: { onCreado: (nombre: string) => void; mensajeCreado: string | null; onCerrarMensaje: () => void }) {
  const { usuario } = useSesion()
  const [rol, setRol] = useState<'PROFESOR' | 'UTP'>('PROFESOR')
  const [nombre, setNombre] = useState('')
  const [rut, setRut] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [errores, setErrores] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    onCerrarMensaje()
    const er = {
      nombre: nombre.trim() ? null : 'Escribe el nombre.',
      rut: errorRut(rut),
      password: errorPassword(password, rut),
      password2: password === password2 ? null : 'Las contraseñas no coinciden.',
    }
    setErrores(er)
    setError(null)
    if (Object.values(er).some(Boolean) || !usuario) return
    setEnviando(true)
    try {
      await api('/usuarios', {
        metodo: 'POST',
        cuerpo: { nombre: nombre.trim(), rut: rutParaApi(rut), colegio_id: usuario.colegio_id, roles: [rol satisfies Rol], password },
      })
      onCreado(nombre.trim())
      setNombre('')
      setRut('')
      setPassword('')
      setPassword2('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={enviar} noValidate className="space-y-4 rounded-2xl border bg-card p-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <UserPlus className="size-4 text-primary" /> Agregar personal
        </h2>
        <p className="text-sm text-muted-foreground">Entrégale su RUT y la contraseña en persona; podrá usarlos de inmediato.</p>
      </div>

      <div role="radiogroup" aria-label="Rol" className="grid grid-cols-2 gap-1.5 rounded-xl bg-muted p-1">
        {(['PROFESOR', 'UTP'] as const).map((r) => (
          <button
            key={r}
            type="button"
            role="radio"
            aria-checked={rol === r}
            onClick={() => setRol(r)}
            className={cn('h-10 rounded-lg text-sm font-medium transition-colors desk:h-8', rol === r ? 'bg-background shadow-sm' : 'text-muted-foreground')}
          >
            {ETIQUETA[r]}
          </button>
        ))}
      </div>
      {rol === 'UTP' && <p className="-mt-2 text-xs text-muted-foreground">Un UTP administra el colegio: horarios, cursos y personal. Úsalo para tener un respaldo si alguien olvida su contraseña.</p>}

      <Campo etiqueta="Nombre" value={nombre} error={errores.nombre} autoComplete="off" onChange={(e) => setNombre(e.target.value)} />
      <Campo etiqueta="RUT" value={rut} error={errores.rut} placeholder="12.345.678-5" autoComplete="off" onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo
        etiqueta="Contraseña"
        type="password"
        value={password}
        error={errores.password}
        ayuda="Mínimo 10 caracteres, sin el RUT."
        autoComplete="new-password"
        onChange={(e) => setPassword(e.target.value)}
      />
      <Campo etiqueta="Repite la contraseña" type="password" value={password2} error={errores.password2} autoComplete="new-password" onChange={(e) => setPassword2(e.target.value)} />
      <ErrorForm mensaje={error} />
      {mensajeCreado && (
        <div role="status" className="flex items-start gap-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950 ring-1 ring-emerald-200">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
          <span>{mensajeCreado} fue agregado. {rol === 'PROFESOR' ? 'Ya puedes asignarle bloques en el Horario.' : 'Ya puede entrar como UTP.'}</span>
        </div>
      )}
      <Button type="submit" disabled={enviando} className="h-12 w-full text-base desk:h-10 desk:text-sm">
        {enviando && <Loader2 className="animate-spin" />} Agregar {ETIQUETA[rol].toLowerCase()}
      </Button>
    </form>
  )
}
