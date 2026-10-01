import { useMemo, useState, type FormEvent } from 'react'
import { CheckCircle2, Loader2, UserPlus, Users } from 'lucide-react'
import { Campo, Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { api, type Usuario } from '@/lib/api'
import { formatearRut, rutParaApi } from '@/lib/rut'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { errorPassword, errorRut } from '@/lib/validar'

/** El UTP ve los profesores del colegio y da de alta a los nuevos. */
export function Profesores() {
  const personal = useCarga(() => api<Usuario[]>('/usuarios'), [])
  const [creado, setCreado] = useState<string | null>(null)
  const profesores = useMemo(
    () => (personal.datos ?? []).filter((u) => u.roles.includes('PROFESOR')).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es')),
    [personal.datos],
  )

  return (
    <div className="space-y-6 desk:grid desk:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] desk:items-start desk:gap-8 desk:space-y-0">
      <FormProfesor
        onCreado={(nombre) => {
          setCreado(nombre)
          personal.recargar()
        }}
        mensajeCreado={creado}
        onCerrarMensaje={() => setCreado(null)}
      />

      <section aria-label="Profesores del colegio">
        {personal.cargando && !personal.datos ? (
          <Cargando />
        ) : personal.error ? (
          <ErrorForm mensaje={personal.error} />
        ) : profesores.length === 0 ? (
          <Vacio icono={Users} titulo="Sin profesores">
            Agrega al primero con el formulario. Después podrás asignarle bloques en el Horario.
          </Vacio>
        ) : (
          <ul className="divide-y rounded-2xl border bg-card">
            {profesores.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{p.nombre}</p>
                  <p className="text-xs tabular-nums text-muted-foreground">{p.rut}</p>
                </div>
                {p.roles.includes('UTP') && <span className="rounded-full bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">También UTP</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function FormProfesor({ onCreado, mensajeCreado, onCerrarMensaje }: { onCreado: (nombre: string) => void; mensajeCreado: string | null; onCerrarMensaje: () => void }) {
  const { usuario } = useSesion()
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
        cuerpo: { nombre: nombre.trim(), rut: rutParaApi(rut), colegio_id: usuario.colegio_id, roles: ['PROFESOR'], password },
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
          <UserPlus className="size-4 text-primary" /> Agregar profesor
        </h2>
        <p className="text-sm text-muted-foreground">Entrégale su RUT y la contraseña en persona; podrá usarlos de inmediato.</p>
      </div>
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
          <span>{mensajeCreado} fue agregado. Ya puedes asignarle bloques en el Horario.</span>
        </div>
      )}
      <Button type="submit" disabled={enviando} className="h-12 w-full text-base desk:h-10 desk:text-sm">
        {enviando && <Loader2 className="animate-spin" />} Agregar profesor
      </Button>
    </form>
  )
}
