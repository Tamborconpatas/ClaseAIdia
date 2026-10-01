import { useState, type FormEvent, type ReactNode } from 'react'
import { ArrowLeft, BookOpenCheck, Loader2, ShieldCheck, Sparkles } from 'lucide-react'
import { Campo, Cargando, ErrorForm, Logo } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { api, type Sesion } from '@/lib/api'
import { formatearRut, rutParaApi } from '@/lib/rut'
import { useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { PieLegal } from '@/views/Legal'
import { errorPassword, errorPin, errorRut, soloDigitos } from '@/lib/validar'

/** Pantalla previa a la sesión: primer arranque del servidor o acceso. */
export function Entrada() {
  const estado = useCarga(() => api<{ configurado: boolean }>('/auth/estado'), [])

  return (
    <Marco>
      {estado.cargando ? (
        <Cargando />
      ) : estado.error ? (
        <div className="space-y-4">
          <ErrorForm mensaje={estado.error} />
          <Button className="h-11 w-full desk:h-9" onClick={estado.recargar}>
            Reintentar
          </Button>
        </div>
      ) : estado.datos?.configurado ? (
        <Acceso />
      ) : (
        <PrimerArranque />
      )}
    </Marco>
  )
}

/** PC: panel de marca a la izquierda y formulario a la derecha. Teléfono: cabecera compacta y formulario. */
function Marco({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh desk:grid desk:grid-cols-[1.05fr_1fr]">
      <section className="hidden flex-col justify-between bg-gradient-to-br from-indigo-600 via-indigo-600 to-violet-700 p-12 text-white desk:flex">
        <Logo claro />
        <div className="max-w-md space-y-8">
          <h2 className="text-4xl font-semibold leading-tight tracking-tight">
            Que ninguna clase se te pase.
          </h2>
          <ul className="space-y-5 text-indigo-50">
            <Beneficio icono={BookOpenCheck} titulo="Resumen de cada clase">
              Puntos clave, hoja de repaso y tarjetas de estudio, listos después de clases.
            </Beneficio>
            <Beneficio icono={Sparkles} titulo="Repasa mejor, no más">
              Preguntas para recordar y repaso espaciado, pensados para cómo se aprende.
            </Beneficio>
            <Beneficio icono={ShieldCheck} titulo="Tu voz no sale del colegio">
              El audio se procesa en el colegio y se borra. Solo se guarda el texto.
            </Beneficio>
          </ul>
        </div>
        <p className="text-sm text-indigo-200">Proyecto de título · pensado para 7° básico a 4° medio</p>
      </section>

      <div className="flex min-h-dvh flex-col desk:min-h-0 desk:items-center desk:justify-center">
        <header className="bg-gradient-to-br from-indigo-600 to-violet-700 px-6 pb-10 pt-8 text-white short:pb-8 short:pt-4 desk:hidden">
          <Logo claro />
          <p className="mt-5 text-2xl font-semibold leading-snug short:hidden">Que ninguna clase se te pase.</p>
        </header>
        <div className="-mt-5 flex-1 rounded-t-3xl bg-background px-6 pb-10 pt-7 desk:mt-0 desk:w-full desk:max-w-md desk:flex-none desk:rounded-none desk:bg-transparent desk:p-0">
          <div className="mx-auto w-full max-w-md">{children}<PieLegal className="mt-8" /></div>
        </div>
      </div>
    </div>
  )
}

function Beneficio({ icono: Icono, titulo, children }: { icono: typeof Sparkles; titulo: string; children: ReactNode }) {
  return (
    <li className="flex gap-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white/15">
        <Icono className="size-5" />
      </span>
      <span>
        <span className="block font-medium text-white">{titulo}</span>
        <span className="text-sm">{children}</span>
      </span>
    </li>
  )
}

// ---------------------------------------------------------------------------------------------

type Modo = 'entrar' | 'unirse' | 'olvide' | 'olvidePassword'

function Acceso() {
  const codigoEnUrl = new URLSearchParams(window.location.search).get('unirse')
  const [modo, setModo] = useState<Modo>(codigoEnUrl ? 'unirse' : 'entrar')

  if (modo !== 'entrar') {
    return (
      <div className="space-y-6">
        <button
          onClick={() => setModo('entrar')}
          className="-ml-1 flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Volver
        </button>
        {modo === 'unirse' ? <FormUnirse codigoInicial={codigoEnUrl ?? ''} /> : modo === 'olvide' ? <FormOlvide /> : <FormOlvidePassword />}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Entrar</h1>
        <p className="text-sm text-muted-foreground">Usa tu RUT para ingresar.</p>
      </div>
      <Tabs defaultValue="alumno">
        <TabsList className="h-11 w-full desk:h-9">
          <TabsTrigger value="alumno">Soy alumno</TabsTrigger>
          <TabsTrigger value="staff">Profesor o UTP</TabsTrigger>
        </TabsList>
        <TabsContent value="alumno" className="mt-5">
          <FormAlumno />
        </TabsContent>
        <TabsContent value="staff" className="mt-5">
          <FormStaff />
        </TabsContent>
      </Tabs>

      <div className="space-y-2 border-t pt-5 text-center text-sm">
        <p>
          ¿Primera vez?{' '}
          <button className="font-medium text-primary hover:underline" onClick={() => setModo('unirse')}>
            Únete a tu curso
          </button>
        </p>
        <p className="space-x-4">
          <button className="text-muted-foreground hover:text-foreground hover:underline" onClick={() => setModo('olvide')}>
            Olvidé mi PIN
          </button>
          <button className="text-muted-foreground hover:text-foreground hover:underline" onClick={() => setModo('olvidePassword')}>
            Olvidé mi contraseña
          </button>
        </p>
      </div>
    </div>
  )
}

/** Envío con estado de carga y error, común a todos los formularios. */
function useEnvio(accion: () => Promise<unknown>) {
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setEnviando(true)
    try {
      await accion()
    } catch (err) {
      setError((err as Error).message)
      setEnviando(false)
    }
  }
  return { enviando, error, setError, enviar }
}

function Enviar({ enviando, children }: { enviando: boolean; children: ReactNode }) {
  return (
    <Button type="submit" disabled={enviando} className="h-12 w-full text-base desk:h-10 desk:text-sm">
      {enviando && <Loader2 className="animate-spin" />}
      {children}
    </Button>
  )
}

function FormAlumno() {
  const { entrar } = useSesion()
  const [rut, setRut] = useState('')
  const [pin, setPin] = useState('')
  const [errRut, setErrRut] = useState<string | null>(null)
  const envio = useEnvio(async () => {
    entrar(await api<Sesion>('/auth/login/alumno', { metodo: 'POST', cuerpo: { rut: rutParaApi(rut), pin } }))
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = errorRut(rut)
    setErrRut(er)
    if (er) return e.preventDefault()
    if (!/^\d{6}$/.test(pin)) {
      e.preventDefault()
      return envio.setError('El PIN son 6 números.')
    }
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <Campo etiqueta="RUT" value={rut} error={errRut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="PIN" type="password" inputMode="numeric" maxLength={6} value={pin} placeholder="6 números"
        autoComplete="current-password" onChange={(e) => setPin(soloDigitos(e.target.value))} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Entrar</Enviar>
    </form>
  )
}

function FormStaff() {
  const { entrar } = useSesion()
  const [rut, setRut] = useState('')
  const [password, setPassword] = useState('')
  const [errRut, setErrRut] = useState<string | null>(null)
  const envio = useEnvio(async () => {
    entrar(await api<Sesion>('/auth/login/staff', { metodo: 'POST', cuerpo: { rut: rutParaApi(rut), password } }))
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = errorRut(rut)
    setErrRut(er)
    if (er) return e.preventDefault()
    if (!password) {
      e.preventDefault()
      return envio.setError('Escribe tu contraseña.')
    }
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <Campo etiqueta="RUT" value={rut} error={errRut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="Contraseña" type="password" value={password} autoComplete="current-password"
        onChange={(e) => setPassword(e.target.value)} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Entrar</Enviar>
    </form>
  )
}

function FormUnirse({ codigoInicial }: { codigoInicial: string }) {
  const { entrar } = useSesion()
  const [codigo, setCodigo] = useState(codigoInicial.toUpperCase())
  const [nombre, setNombre] = useState('')
  const [rut, setRut] = useState('')
  const [pin, setPin] = useState('')
  const [pin2, setPin2] = useState('')
  const [errores, setErrores] = useState<Record<string, string | null>>({})
  const envio = useEnvio(async () => {
    entrar(
      await api<Sesion>('/cursos/unirse', {
        metodo: 'POST',
        cuerpo: { codigo_invitacion: codigo.trim(), nombre: nombre.trim(), rut: rutParaApi(rut), pin },
      }),
    )
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = {
      codigo: codigo.trim() ? null : 'Escribe el código de tu curso.',
      nombre: nombre.trim() ? null : 'Escribe tu nombre.',
      rut: errorRut(rut),
      pin: errorPin(pin),
      pin2: pin === pin2 ? null : 'Los PIN no coinciden.',
    }
    setErrores(er)
    if (Object.values(er).some(Boolean)) return e.preventDefault()
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Únete a tu curso</h1>
        <p className="text-sm text-muted-foreground">
          Pide el código a tu profesor (o escanea el QR). Elige un PIN que recuerdes: lo usarás para entrar.
        </p>
      </div>
      <Campo etiqueta="Código del curso" value={codigo} error={errores.codigo} placeholder="ABC123" autoCapitalize="characters"
        onChange={(e) => setCodigo(e.target.value.toUpperCase())} />
      <Campo etiqueta="Tu nombre" value={nombre} error={errores.nombre} autoComplete="name" onChange={(e) => setNombre(e.target.value)} />
      <Campo etiqueta="RUT" value={rut} error={errores.rut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="Elige un PIN" type="password" inputMode="numeric" maxLength={6} value={pin} error={errores.pin}
        ayuda="6 números. Sin repetidos ni secuencias (nada de 111111 o 123456)." autoComplete="new-password"
        onChange={(e) => setPin(soloDigitos(e.target.value))} />
      <Campo etiqueta="Repite el PIN" type="password" inputMode="numeric" maxLength={6} value={pin2} error={errores.pin2}
        autoComplete="new-password" onChange={(e) => setPin2(soloDigitos(e.target.value))} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Unirme y entrar</Enviar>
    </form>
  )
}

function FormOlvide() {
  const { entrar } = useSesion()
  const [rut, setRut] = useState('')
  const [codigo, setCodigo] = useState('')
  const [pin, setPin] = useState('')
  const [pin2, setPin2] = useState('')
  const [errores, setErrores] = useState<Record<string, string | null>>({})
  const envio = useEnvio(async () => {
    entrar(
      await api<Sesion>('/auth/restablecer-pin', {
        metodo: 'POST',
        cuerpo: { rut: rutParaApi(rut), codigo: codigo.trim(), pin },
      }),
    )
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = {
      rut: errorRut(rut),
      codigo: codigo.trim() ? null : 'Escribe el código que te dio tu profesor.',
      pin: errorPin(pin),
      pin2: pin === pin2 ? null : 'Los PIN no coinciden.',
    }
    setErrores(er)
    if (Object.values(er).some(Boolean)) return e.preventDefault()
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Olvidé mi PIN</h1>
        <p className="text-sm text-muted-foreground">
          Pídele a tu profesor o a UTP que restablezca tu PIN: te dará un código que sirve una sola vez y vence en 15
          minutos.
        </p>
      </div>
      <Campo etiqueta="RUT" value={rut} error={errores.rut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="Código de restablecimiento" value={codigo} error={errores.codigo} autoCapitalize="characters"
        onChange={(e) => setCodigo(e.target.value.toUpperCase())} />
      <Campo etiqueta="Nuevo PIN" type="password" inputMode="numeric" maxLength={6} value={pin} error={errores.pin}
        autoComplete="new-password" onChange={(e) => setPin(soloDigitos(e.target.value))} />
      <Campo etiqueta="Repite el nuevo PIN" type="password" inputMode="numeric" maxLength={6} value={pin2} error={errores.pin2}
        autoComplete="new-password" onChange={(e) => setPin2(soloDigitos(e.target.value))} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Guardar PIN y entrar</Enviar>
    </form>
  )
}

/** Profesor o UTP que olvidó su contraseña: la cambia con el código de un solo uso que le dio un UTP. */
function FormOlvidePassword() {
  const { entrar } = useSesion()
  const [rut, setRut] = useState('')
  const [codigo, setCodigo] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [errores, setErrores] = useState<Record<string, string | null>>({})
  const envio = useEnvio(async () => {
    entrar(
      await api<Sesion>('/auth/restablecer-password', {
        metodo: 'POST',
        cuerpo: { rut: rutParaApi(rut), codigo: codigo.trim(), password },
      }),
    )
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = {
      rut: errorRut(rut),
      codigo: codigo.trim() ? null : 'Escribe el código que te dio tu UTP.',
      password: errorPassword(password, rut),
      password2: password === password2 ? null : 'Las contraseñas no coinciden.',
    }
    setErrores(er)
    if (Object.values(er).some(Boolean)) return e.preventDefault()
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Olvidé mi contraseña</h1>
        <p className="text-sm text-muted-foreground">
          Pídele a un UTP que te genere un código (en Personal, «Resetear contraseña»): sirve una sola vez y vence en 15
          minutos. Si eres el único UTP, quien administra el servidor puede restablecerla desde su consola.
        </p>
      </div>
      <Campo etiqueta="RUT" value={rut} error={errores.rut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="Código de restablecimiento" value={codigo} error={errores.codigo} autoCapitalize="characters"
        onChange={(e) => setCodigo(e.target.value.toUpperCase())} />
      <Campo etiqueta="Contraseña nueva" type="password" value={password} error={errores.password}
        ayuda="Mínimo 10 caracteres, sin tu RUT." autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
      <Campo etiqueta="Repite la contraseña" type="password" value={password2} error={errores.password2}
        autoComplete="new-password" onChange={(e) => setPassword2(e.target.value)} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Guardar contraseña y entrar</Enviar>
    </form>
  )
}

// ---------------------------------------------------------------------------------------------

function PrimerArranque() {
  const { entrar } = useSesion()
  const [colegio, setColegio] = useState('')
  const [nombre, setNombre] = useState('')
  const [rut, setRut] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [errores, setErrores] = useState<Record<string, string | null>>({})
  const envio = useEnvio(async () => {
    entrar(
      await api<Sesion>('/auth/setup', {
        metodo: 'POST',
        cuerpo: { colegio_nombre: colegio.trim(), nombre: nombre.trim(), rut: rutParaApi(rut), password },
      }),
    )
  })

  const validarYEnviar = (e: FormEvent) => {
    const er = {
      colegio: colegio.trim() ? null : 'Escribe el nombre del colegio.',
      nombre: nombre.trim() ? null : 'Escribe tu nombre.',
      rut: errorRut(rut),
      password: errorPassword(password, rut),
      password2: password === password2 ? null : 'Las contraseñas no coinciden.',
    }
    setErrores(er)
    if (Object.values(er).some(Boolean)) return e.preventDefault()
    return envio.enviar(e)
  }

  return (
    <form onSubmit={validarYEnviar} className="space-y-4" noValidate>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Configura tu colegio</h1>
        <p className="text-sm text-muted-foreground">
          Es la primera vez que se abre este servidor. Crea el colegio y la cuenta de UTP que lo administrará. Esta
          pantalla se cierra sola después.
        </p>
      </div>
      <Campo etiqueta="Nombre del colegio" value={colegio} error={errores.colegio} onChange={(e) => setColegio(e.target.value)} />
      <Campo etiqueta="Tu nombre" value={nombre} error={errores.nombre} autoComplete="name" onChange={(e) => setNombre(e.target.value)} />
      <Campo etiqueta="Tu RUT" value={rut} error={errores.rut} placeholder="12.345.678-5" autoComplete="username"
        onChange={(e) => setRut(formatearRut(e.target.value))} />
      <Campo etiqueta="Contraseña" type="password" value={password} error={errores.password}
        ayuda="Mínimo 10 caracteres, sin tu RUT." autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
      <Campo etiqueta="Repite la contraseña" type="password" value={password2} error={errores.password2}
        autoComplete="new-password" onChange={(e) => setPassword2(e.target.value)} />
      <ErrorForm mensaje={envio.error} />
      <Enviar enviando={envio.enviando}>Crear colegio y entrar</Enviar>
    </form>
  )
}
