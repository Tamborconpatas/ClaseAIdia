import { useState } from 'react'
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock, Info, Loader2, Mic, MicOff, MonitorSmartphone, Pause, Play, Square, Timer, Wifi, WifiOff } from 'lucide-react'
import { Cargando, ErrorForm, Vacio } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { api, type AccionGrabacion, type BloqueDeHoy, type Grabacion } from '@/lib/api'
import { activarEquipo, equipoActivo, idDeEsteEquipo, puedeGrabarAqui, soltarEquipo, useEquipo } from '@/lib/grabador'
import { colorAsignatura, hhmm } from '@/lib/horario'
import { useCarga, useSondeo } from '@/lib/usar'
import { cn } from '@/lib/utils'

const mmss = (s: number) => {
  const t = Math.max(0, Math.floor(s))
  const h = Math.floor(t / 3600)
  const m = String(Math.floor((t % 3600) / 60)).padStart(2, '0')
  const seg = String(t % 60).padStart(2, '0')
  return h > 0 ? `${h}:${m}:${seg}` : `${m}:${seg}`
}

const ESTADO: Record<Grabacion['estado'], { texto: string; clase: string }> = {
  esperando: { texto: 'Lista para empezar', clase: 'bg-muted text-muted-foreground' },
  grabando: { texto: 'Grabando', clase: 'bg-red-100 text-red-900' },
  pausada: { texto: 'En pausa', clase: 'bg-amber-100 text-amber-900' },
  terminando: { texto: 'Terminando…', clase: 'bg-amber-100 text-amber-900' },
  procesando: { texto: 'Procesando', clase: 'bg-muted text-muted-foreground' },
  terminada: { texto: 'Lista', clase: 'bg-emerald-100 text-emerald-900' },
  error: { texto: 'Con error', clase: 'bg-red-200 text-red-950' },
}

/**
 * Grabar la clase. Sirve de las dos formas: un PC de la sala graba (el celular del profesor es solo el control
 * remoto), o el propio celular graba. Es la misma pantalla en los dos equipos: cualquiera puede controlar, y el
 * equipo que graba se elige con un botón. Solo funciona desde la red del colegio (lo exige el servidor).
 */
export function Grabar({ onAbrirClase }: { onAbrirClase: (claseId: number) => void }) {
  const equipo = useEquipo()
  // Si este equipo está grabando, al volver a esta pestaña se retoma directo su sesión (no la lista).
  const [sesion, setSesion] = useState<number | null>(equipo.grabacionId !== null && equipoActivo(equipo.info) ? equipo.grabacionId : null)
  if (sesion !== null) return <Sesion id={sesion} onSalir={() => setSesion(null)} onAbrirClase={onAbrirClase} />
  return <ListaDeHoy onAbrir={setSesion} />
}

function ListaDeHoy({ onAbrir }: { onAbrir: (grabacionId: number) => void }) {
  const hoy = useCarga(() => api<BloqueDeHoy[]>('/grabaciones/hoy'), [])
  const [abriendo, setAbriendo] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const abrir = async (b: BloqueDeHoy) => {
    setError(null)
    if (b.grabacion) return onAbrir(b.grabacion.id)
    setAbriendo(b.bloque_id)
    try {
      onAbrir((await api<Grabacion>('/grabaciones', { metodo: 'POST', cuerpo: { bloque_id: b.bloque_id } })).id)
    } catch (e) {
      setError((e as Error).message)
      setAbriendo(null)
    }
  }

  if (hoy.cargando && !hoy.datos) return <Cargando />
  if (hoy.error) {
    return (
      <Vacio icono={WifiOff} titulo="No se puede grabar desde aquí" accion={<Button variant="outline" onClick={hoy.recargar}>Reintentar</Button>}>
        {hoy.error}
      </Vacio>
    )
  }
  const bloques = hoy.datos ?? []
  if (bloques.length === 0) {
    return (
      <Vacio icono={Mic} titulo="Hoy no tienes clases para grabar">
        Aquí aparecen tus bloques de clase del día. Si hoy debería haber uno, pídele al UTP que revise tu horario.
      </Vacio>
    )
  }
  return (
    <div className="mx-auto max-w-xl space-y-4">
      <p className="text-sm text-muted-foreground">Elige la clase que vas a grabar. El audio se usa solo para generar el material y se borra al terminar de procesarse.</p>
      <ErrorForm mensaje={error} />
      <ul className="space-y-3">
        {bloques.map((b) => (
          <li key={b.bloque_id} className={cn('rounded-2xl border-l-4 p-4', colorAsignatura(b.asignatura))}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-lg font-semibold leading-tight">{b.asignatura}</p>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm opacity-80">
                  <span>{b.curso_nombre}</span>
                  <span className="flex items-center gap-1"><Clock className="size-3.5" /> {hhmm(b.hora_inicio)}–{hhmm(b.hora_fin)}</span>
                  {b.sala && <span>{b.sala}</span>}
                </p>
              </div>
              {b.grabacion && <span className={cn('shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium', ESTADO[b.grabacion.estado].clase)}>{ESTADO[b.grabacion.estado].texto}</span>}
            </div>
            {b.puede_grabar || b.grabacion ? (
              <Button className="mt-3 h-12 w-full text-base desk:h-10 desk:w-auto desk:text-sm" disabled={abriendo === b.bloque_id} onClick={() => void abrir(b)}>
                {abriendo === b.bloque_id ? <Loader2 className="animate-spin" /> : <Mic />}
                {b.grabacion ? (['esperando', 'grabando', 'pausada', 'terminando'].includes(b.grabacion.estado) ? 'Continuar' : 'Ver') : 'Preparar grabación'}
              </Button>
            ) : (
              <p className="mt-3 text-sm opacity-80">{b.motivo}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Sesion({ id, onSalir, onAbrirClase }: { id: number; onSalir: () => void; onAbrirClase: (claseId: number) => void }) {
  const { datos: g, sinConexion, actualizar } = useSondeo(() => api<Grabacion>(`/grabaciones/${id}`), 1500, [id])
  const equipo = useEquipo()
  const [error, setError] = useState<string | null>(null)
  const [trabajando, setTrabajando] = useState<string | null>(null)
  const [confirmando, setConfirmando] = useState<'terminar' | 'tomar' | null>(null)

  const esteGraba = equipo.grabacionId === id && equipoActivo(equipo.info)
  const posibilidad = puedeGrabarAqui()

  const comando = async (accion: AccionGrabacion) => {
    setError(null)
    setTrabajando(accion)
    try {
      await api(`/grabaciones/${id}/comando`, { metodo: 'POST', cuerpo: { accion } })
      if (accion === 'cancelar') {
        soltarEquipo()
        return onSalir()
      }
      actualizar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(null)
      setConfirmando(null)
    }
  }

  const grabarAqui = async (forzar: boolean) => {
    if (!g) return
    setError(null)
    setTrabajando('grabador')
    try {
      await activarEquipo(g, forzar)
      actualizar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(null)
      setConfirmando(null)
    }
  }

  const reintentar = async () => {
    setError(null)
    setTrabajando('reintentar')
    try {
      try {
        // Con un reintento automático programado, el botón solo lo adelanta (la sesión y su audio se conservan).
        await api(`/grabaciones/${id}/${g?.reintento_en ? 'reintentar-ahora' : 'regenerar'}`, { metodo: 'POST' })
      } catch {
        // No había transcripción que regenerar (falló antes): se vuelve a empezar la misma sesión.
        await api('/grabaciones', { metodo: 'POST', cuerpo: { bloque_id: g?.bloque_id } })
      }
      actualizar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(null)
    }
  }

  if (!g) return <Cargando />

  const enCurso = g.estado === 'esperando' || g.estado === 'grabando' || g.estado === 'pausada'
  const segundos = esteGraba ? Math.max(equipo.info.segundos, g.segundos_grabados) : g.segundos_grabados
  const nivel = esteGraba ? equipo.info.nivel : g.nivel
  // Este mismo navegador grababa y se interrumpió (se recargó la página, se apagó la pantalla): puede retomar sin pedir permiso.
  const eraEste = !esteGraba && g.grabador_id === idDeEsteEquipo()
  const otroGraba = g.grabador_conectado && !esteGraba && !eraEste
  const corte = new Date(g.corte_en)
  const horaCorte = Number.isNaN(corte.getTime()) ? '' : corte.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false })

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <button onClick={onSalir} className="-ml-2 flex h-10 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Mis clases de hoy
      </button>

      <header className={cn('rounded-2xl border-l-4 p-4', colorAsignatura(g.asignatura))}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-semibold leading-tight">{g.asignatura}</h2>
            <p className="mt-1 text-sm opacity-80">
              {g.curso_nombre} · {hhmm(g.hora_inicio)}–{hhmm(g.hora_fin)}
              {g.sala ? ` · ${g.sala}` : ''}
            </p>
          </div>
          <span role="status" className={cn('inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium', ESTADO[g.estado].clase)}>
            {g.estado === 'grabando' && <span className="size-2 animate-pulse rounded-full bg-red-600" />}
            {(g.estado === 'procesando' || g.estado === 'terminando') && <Loader2 className="size-3 animate-spin" />}
            {ESTADO[g.estado].texto}
          </span>
        </div>
      </header>

      {sinConexion && (
        <Aviso icono={WifiOff} tono="ambar">
          Sin conexión con el servidor. {esteGraba ? 'Este equipo sigue grabando y subirá el audio cuando vuelva.' : 'Los botones no harán efecto hasta que vuelva.'}
        </Aviso>
      )}
      <ErrorForm mensaje={error} />

      {(enCurso || g.estado === 'terminando') && (
        <section className="space-y-4 rounded-2xl border bg-card p-4 text-center desk:p-5" aria-label="Tiempo y volumen">
          <p className="font-mono text-5xl font-semibold tabular-nums tracking-tight" aria-label={`Tiempo grabado ${mmss(segundos)}`}>{mmss(segundos)}</p>
          <Medidor nivel={g.silenciada ? 0 : nivel} silenciada={g.silenciada} />
          {horaCorte && g.estado !== 'terminando' && (
            <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
              <Timer className="size-3.5" /> Si no la terminas, se corta sola a las {horaCorte}.
            </p>
          )}
        </section>
      )}

      {enCurso && (
        <>
          <EquipoGrabador
            esteGraba={esteGraba}
            fase={equipo.info.fase}
            pendientes={equipo.info.pendientes}
            mensaje={equipo.grabacionId === id ? equipo.info.mensaje : null}
            otroGraba={otroGraba}
            eraEste={eraEste}
            conectado={g.grabador_conectado}
            iniciada={g.estado !== 'esperando'}
            puedeAqui={posibilidad}
            ocupado={trabajando === 'grabador'}
            confirmando={confirmando === 'tomar'}
            onGrabarAqui={() => (otroGraba && confirmando !== 'tomar' ? setConfirmando('tomar') : void grabarAqui(otroGraba))}
            onCancelarCambio={() => setConfirmando(null)}
            onSoltar={soltarEquipo}
          />
          <Controles
            g={g}
            trabajando={trabajando}
            confirmandoTerminar={confirmando === 'terminar'}
            onComando={(a) => void comando(a)}
            onPedirTerminar={() => setConfirmando('terminar')}
            onNoTerminar={() => setConfirmando(null)}
          />
        </>
      )}

      {g.estado === 'terminando' && (
        <Aviso icono={Loader2} tono="gris" girar>
          Terminando: el equipo que graba está subiendo lo último. Enseguida se empieza a procesar.
        </Aviso>
      )}
      {g.estado === 'procesando' && (
        <Aviso icono={Loader2} tono="gris" girar>
          Procesando la clase: se transcribe y se genera el material. Puede tardar unos minutos y puedes cerrar esta pantalla.
        </Aviso>
      )}
      {g.estado === 'terminada' && (
        <section className="space-y-3 rounded-2xl border bg-card p-5 text-center">
          <CheckCircle2 className="mx-auto size-8 text-emerald-600" />
          <p className="font-medium">¡Listo! El material de la clase quedó por aprobar.</p>
          <p className="text-sm text-muted-foreground">Revísalo, corrígelo si hace falta y apruébalo para que lo vean los alumnos.</p>
          <Button className="h-12 w-full text-base desk:h-10 desk:w-auto desk:text-sm" onClick={() => onAbrirClase(g.clase_id)}>
            Ver la clase
          </Button>
        </section>
      )}
      {g.estado === 'error' && (
        <section className="space-y-3 rounded-2xl border border-destructive/30 bg-card p-5">
          <p className="flex items-start gap-2 font-medium text-destructive">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {g.reintento_en ? 'El procesamiento falló y se reintentará solo' : 'No se pudo procesar la clase'}
          </p>
          <p className="text-sm text-muted-foreground">{g.error}</p>
          <Button className="h-12 w-full text-base desk:h-10 desk:w-auto desk:text-sm" disabled={trabajando === 'reintentar'} onClick={() => void reintentar()}>
            {trabajando === 'reintentar' && <Loader2 className="animate-spin" />} {g.reintento_en ? 'Reintentar ahora' : 'Reintentar'}
          </Button>
        </section>
      )}
    </div>
  )
}

function Medidor({ nivel, silenciada }: { nivel: number; silenciada: boolean }) {
  return (
    <div className="space-y-1.5">
      <div
        role="meter"
        aria-label="Volumen del micrófono"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(nivel * 100)}
        className="h-3 overflow-hidden rounded-full bg-muted"
      >
        <div className={cn('h-full rounded-full transition-[width] duration-150', nivel > 0.9 ? 'bg-red-500' : 'bg-emerald-500')} style={{ width: `${Math.round(nivel * 100)}%` }} />
      </div>
      <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
        {silenciada ? <><MicOff className="size-3.5" /> Micrófono en silencio</> : <><Mic className="size-3.5" /> Volumen del micrófono</>}
      </p>
    </div>
  )
}

interface PropsEquipo {
  esteGraba: boolean
  fase: string
  pendientes: number
  mensaje: string | null
  otroGraba: boolean
  eraEste: boolean
  conectado: boolean
  iniciada: boolean
  puedeAqui: { puede: boolean; motivo?: string }
  ocupado: boolean
  confirmando: boolean
  onGrabarAqui: () => void
  onCancelarCambio: () => void
  onSoltar: () => void
}

/** Qué equipo graba. Con un PC de la sala: se abre «Grabar» allí y se pulsa el botón. Con el celular: el botón en el celular. */
function EquipoGrabador(p: PropsEquipo) {
  return (
    <section className="space-y-3 rounded-2xl border bg-card p-4 desk:p-5" aria-label="Equipo que graba">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-primary">
        <MonitorSmartphone className="size-4" /> Equipo que graba
      </h3>

      {p.esteGraba ? (
        <>
          <p className="flex items-center gap-2 text-sm">
            <Wifi className="size-4 text-emerald-600" /> Este equipo está grabando
            {p.pendientes > 0 && <span className="text-muted-foreground">· subiendo ({p.pendientes} pendiente{p.pendientes === 1 ? '' : 's'})</span>}
          </p>
          <Aviso icono={Info} tono="azul">
            Mantén esta pantalla abierta y encendida (y el equipo conectado al cargador): si el sistema la apaga o cierras esta pestaña, se deja de grabar.
          </Aviso>
          {p.mensaje && <p className="text-xs text-muted-foreground">{p.mensaje}</p>}
          <Button variant="ghost" className="h-10" onClick={p.onSoltar}>Dejar de grabar con este equipo</Button>
        </>
      ) : (
        <>
          <p className={cn('flex items-center gap-2 text-sm', p.iniciada && !p.conectado && 'text-amber-800')}>
            {p.conectado ? <Wifi className="size-4 text-emerald-600" /> : <WifiOff className="size-4" />}
            {p.eraEste
              ? 'Este equipo estaba grabando y se interrumpió'
              : p.conectado
                ? 'Otro equipo está grabando (conectado)'
                : p.iniciada
                  ? 'El equipo que grababa dejó de responder'
                  : 'Todavía ningún equipo graba'}
          </p>
          {p.eraEste && <p className="text-xs text-muted-foreground">Puede haberse recargado la página o apagado la pantalla. Retoma la grabación: lo grabado hasta ahora se conserva.</p>}
          {p.fase === 'error' || p.fase === 'reemplazado' ? <ErrorForm mensaje={p.mensaje} /> : null}
          {!p.puedeAqui.puede ? (
            <Aviso icono={Info} tono="gris">{p.puedeAqui.motivo}</Aviso>
          ) : p.confirmando ? (
            <div className="space-y-2 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
              <p>Otro equipo está grabando esta clase. ¿Tomar su lugar? Ese equipo dejará de grabar.</p>
              <div className="flex gap-2">
                <Button className="h-10 flex-1" onClick={p.onGrabarAqui} disabled={p.ocupado}>Sí, grabar aquí</Button>
                <Button variant="ghost" className="h-10" onClick={p.onCancelarCambio}>No</Button>
              </div>
            </div>
          ) : (
            <Button variant={p.conectado && !p.eraEste ? 'outline' : 'default'} className="h-12 w-full text-base desk:h-10 desk:w-auto desk:text-sm" disabled={p.ocupado} onClick={p.onGrabarAqui}>
              {p.ocupado ? <Loader2 className="animate-spin" /> : <Mic />} {p.eraEste ? 'Retomar la grabación' : p.conectado ? 'Grabar con este equipo en su lugar' : 'Grabar con este equipo'}
            </Button>
          )}
          {!p.conectado && !p.iniciada && (
            <p className="text-xs text-muted-foreground">
              ¿Hay un PC en la sala? Abre «Grabar» allí y pulsa este botón; desde tu celular solo controlas. Si no, graba con este mismo equipo.
            </p>
          )}
        </>
      )}
    </section>
  )
}

function Controles({
  g, trabajando, confirmandoTerminar, onComando, onPedirTerminar, onNoTerminar,
}: {
  g: Grabacion
  trabajando: string | null
  confirmandoTerminar: boolean
  onComando: (a: AccionGrabacion) => void
  onPedirTerminar: () => void
  onNoTerminar: () => void
}) {
  const ocupado = trabajando !== null
  const grande = 'h-14 text-base desk:h-11 desk:text-sm'
  return (
    <section className="space-y-3 rounded-2xl border bg-card p-4 desk:p-5" aria-label="Controles de la grabación">
      {g.estado === 'esperando' && (
        <>
          <Button className={cn(grande, 'w-full')} disabled={ocupado || !g.grabador_conectado} onClick={() => onComando('iniciar')}>
            {trabajando === 'iniciar' ? <Loader2 className="animate-spin" /> : <Play />} Iniciar la clase
          </Button>
          {!g.grabador_conectado && <p className="text-center text-xs text-muted-foreground">Para iniciar, primero tiene que haber un equipo grabando.</p>}
          <Button variant="ghost" className="h-10 w-full" disabled={ocupado} onClick={() => onComando('cancelar')}>Cancelar</Button>
        </>
      )}
      {(g.estado === 'grabando' || g.estado === 'pausada') && (
        <>
          <div className="grid grid-cols-2 gap-3">
            {g.estado === 'grabando' ? (
              <Button variant="outline" className={grande} disabled={ocupado} onClick={() => onComando('pausar')}><Pause /> Pausar</Button>
            ) : (
              <Button className={grande} disabled={ocupado} onClick={() => onComando('reanudar')}><Play /> Reanudar</Button>
            )}
            <Button variant="outline" className={grande} disabled={ocupado} aria-pressed={g.silenciada} onClick={() => onComando(g.silenciada ? 'activar_audio' : 'silenciar')}>
              {g.silenciada ? <><Mic /> Activar micrófono</> : <><MicOff /> Silenciar</>}
            </Button>
          </div>
          {confirmandoTerminar ? (
            <div className="space-y-2 rounded-lg bg-background p-3 text-sm ring-1 ring-border">
              <p>¿Terminar la clase? Se dejará de grabar y se empezará a procesar.</p>
              <div className="flex gap-2">
                <Button variant="destructive" className="h-10 flex-1" disabled={ocupado} onClick={() => onComando('terminar')}>
                  {trabajando === 'terminar' && <Loader2 className="animate-spin" />} Sí, terminar
                </Button>
                <Button variant="ghost" className="h-10" onClick={onNoTerminar}>No</Button>
              </div>
            </div>
          ) : (
            <Button variant="destructive" className={cn(grande, 'w-full')} disabled={ocupado} onClick={onPedirTerminar}><Square /> Terminar la clase</Button>
          )}
        </>
      )}
      <label className="flex min-h-10 items-center gap-3 text-sm">
        <input
          type="checkbox"
          className="size-5 rounded border-input accent-primary"
          checked={g.prioritaria}
          disabled={ocupado}
          onChange={(e) => onComando(e.target.checked ? 'marcar_prioritaria' : 'quitar_prioritaria')}
        />
        <span>
          Clase prioritaria <span className="text-muted-foreground">(se procesa antes que las demás)</span>
        </span>
      </label>
    </section>
  )
}

const TONOS = {
  ambar: 'bg-amber-50 text-amber-950 ring-amber-200',
  azul: 'bg-sky-50 text-sky-950 ring-sky-200',
  gris: 'bg-muted/60 text-foreground ring-border',
}
function Aviso({ icono: Icono, tono, girar = false, children }: { icono: typeof Info; tono: keyof typeof TONOS; girar?: boolean; children: React.ReactNode }) {
  return (
    <div role="note" className={cn('flex items-start gap-2.5 rounded-xl p-3.5 text-sm ring-1', TONOS[tono])}>
      <Icono className={cn('mt-0.5 size-4 shrink-0', girar && 'animate-spin')} />
      <p className="flex-1 leading-relaxed">{children}</p>
    </div>
  )
}
