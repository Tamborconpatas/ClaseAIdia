import { useSyncExternalStore } from 'react'
import { api, ApiError, subirTrozo, type Grabacion } from '@/lib/api'

/**
 * El equipo que graba: un PC de la sala o el celular del profesor (es el mismo código en los dos).
 *
 * No decide nada por su cuenta: cada par de segundos manda un latido al servidor y obedece el estado que
 * este le devuelve (iniciar, pausar, silenciar, terminar). Va subiendo el audio en trozos, así que si algo
 * se corta se pierde como mucho un trozo, no la clase. El audio nunca se guarda en este equipo más allá de
 * los trozos que aún no se pudieron subir.
 */

export type FaseGrabador = 'inactivo' | 'conectando' | 'listo' | 'grabando' | 'pausada' | 'terminando' | 'finalizado' | 'reemplazado' | 'error'

export interface InfoGrabador {
  fase: FaseGrabador
  nivel: number // 0 a 1, del micrófono de este equipo
  segundos: number // tiempo grabado (sin contar pausas)
  pendientes: number // trozos esperando a subirse
  mensaje: string | null
}

const TROZO_MS = 10_000
const LATIDO_MS = 2_000
const ESPERA_FINAL_MS = 60_000
const FORMATOS = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

/** ¿Este navegador puede usar el micrófono? Exige https o localhost: desde http://192.168… no se puede. */
export function puedeGrabarAqui(): { puede: boolean; motivo?: string } {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    return {
      puede: false,
      motivo:
        'Este navegador no deja usar el micrófono desde esta dirección (hace falta https, o abrir la app desde el mismo equipo con «localhost»). Graba desde el PC de la sala, o configura https en el servidor.',
    }
  }
  if (typeof MediaRecorder === 'undefined') return { puede: false, motivo: 'Este navegador no sabe grabar audio.' }
  return { puede: true }
}

/** Identifica este navegador ante el servidor (se mantiene si se recarga la página). */
export function idDeEsteEquipo(): string {
  const clave = 'claseaidia.equipo'
  try {
    const guardado = localStorage.getItem(clave)
    if (guardado) return guardado
  } catch {
    /* sin almacenamiento: queda un id para esta carga */
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  const id = 'eq-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  try {
    localStorage.setItem(clave, id)
  } catch {
    /* igual */
  }
  return id
}

export class Grabador {
  private info: InfoGrabador = { fase: 'inactivo', nivel: 0, segundos: 0, pendientes: 0, mensaje: null }
  private flujo: MediaStream | null = null
  private grabadora: MediaRecorder | null = null
  private contexto: AudioContext | null = null
  private analizador: AnalyserNode | null = null
  private bloqueo: WakeLockSentinel | null = null
  private cola: { n: number; trozo: Blob }[] = []
  private siguiente: number
  private subiendo = false
  private latidoId: ReturnType<typeof setInterval> | undefined
  private relojId: ReturnType<typeof setInterval> | undefined
  private ultimoReloj = 0
  private cerrando = false
  private activo = false

  private readonly grabacionId: number
  private readonly equipo: string
  private readonly alCambiar: (i: InfoGrabador) => void

  constructor(grabacionId: number, equipo: string, trozosPrevios: number, segundosPrevios: number, alCambiar: (i: InfoGrabador) => void) {
    this.grabacionId = grabacionId
    this.equipo = equipo
    this.alCambiar = alCambiar
    this.siguiente = trozosPrevios // si el equipo vuelve, sigue la numeración y no pisa lo ya subido
    this.info.segundos = segundosPrevios
  }

  private poner(cambio: Partial<InfoGrabador>) {
    this.info = { ...this.info, ...cambio }
    this.alCambiar(this.info)
  }

  /** Pide el micrófono, se registra como el equipo que graba y empieza a latir. */
  async conectar(forzar: boolean): Promise<void> {
    this.poner({ fase: 'conectando', mensaje: null })
    try {
      await this.abrirMicrofono()
      await api<Grabacion>(`/grabaciones/${this.grabacionId}/grabador`, { metodo: 'POST', cuerpo: { dispositivo: this.equipo, forzar } })
    } catch (e) {
      this.liberar()
      this.poner({ fase: 'error', mensaje: this.textoDeError(e) })
      throw e
    }
    this.activo = true
    this.poner({ fase: 'listo' })
    await this.pedirPantallaActiva()
    document.addEventListener('visibilitychange', this.alVolver)
    this.ultimoReloj = performance.now()
    this.relojId = setInterval(() => this.reloj(), 250)
    this.latidoId = setInterval(() => void this.latir(), LATIDO_MS)
    void this.latir()
  }

  /** Deja de grabar en este equipo (sin terminar la clase: otro equipo puede tomar el relevo). */
  soltar(): void {
    this.activo = false
    this.detenerGrabadora()
    this.liberar()
    this.poner({ fase: 'inactivo', nivel: 0 })
  }

  // --- micrófono -----------------------------------------------------------------------------

  private async abrirMicrofono(): Promise<void> {
    this.flujo = await navigator.mediaDevices.getUserMedia({
      // Voz de un profesor: sin cancelación de eco ni supresión (distorsionan); el volumen sí se ajusta solo.
      audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true },
    })
    this.contexto = new AudioContext()
    this.analizador = this.contexto.createAnalyser()
    this.analizador.fftSize = 1024
    this.contexto.createMediaStreamSource(this.flujo).connect(this.analizador)
  }

  private nivelActual(): number {
    if (!this.analizador) return 0
    const datos = new Uint8Array(this.analizador.fftSize)
    this.analizador.getByteTimeDomainData(datos)
    let maximo = 0
    for (const v of datos) maximo = Math.max(maximo, Math.abs(v - 128))
    return Math.min(1, maximo / 90)
  }

  private reloj() {
    const ahora = performance.now()
    const dt = (ahora - this.ultimoReloj) / 1000
    this.ultimoReloj = ahora
    const grabando = this.grabadora?.state === 'recording' // en silencio la clase sigue: el tiempo corre igual
    this.poner({ nivel: this.nivelActual(), segundos: this.info.segundos + (grabando ? dt : 0) })
  }

  private async pedirPantallaActiva() {
    try {
      this.bloqueo = (await navigator.wakeLock?.request('screen')) ?? null
    } catch {
      /* sin permiso o sin soporte: la pantalla puede apagarse; el aviso en pantalla lo advierte */
    }
  }

  /** El navegador suelta el bloqueo de pantalla al ocultar la página: se pide de nuevo al volver. */
  private alVolver = () => {
    if (document.visibilityState === 'visible' && this.activo && (!this.bloqueo || this.bloqueo.released)) void this.pedirPantallaActiva()
  }

  // --- latido: el servidor manda ------------------------------------------------------------

  private async latir() {
    if (!this.activo) return
    try {
      const g = await api<Grabacion>(`/grabaciones/${this.grabacionId}/latido`, {
        metodo: 'POST',
        cuerpo: { dispositivo: this.equipo, segundos: Math.floor(this.info.segundos), nivel: this.info.nivel },
      })
      await this.obedecer(g)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // Otro equipo tomó la grabación: este debe parar de inmediato para no duplicar el audio.
        this.activo = false
        this.detenerGrabadora()
        this.liberar()
        this.poner({ fase: 'reemplazado', mensaje: 'Otro equipo tomó el control de la grabación.' })
      }
      // sin conexión: se sigue grabando y subiendo cuando vuelva
    }
  }

  private async obedecer(g: Grabacion) {
    const pista = this.flujo?.getAudioTracks()[0]
    if (pista) pista.enabled = !g.silenciada
    if (g.estado === 'grabando') {
      if (!this.grabadora || this.grabadora.state === 'inactive' || pista?.readyState === 'ended') await this.empezarGrabadora()
      else if (this.grabadora.state === 'paused') this.grabadora.resume()
      this.poner({ fase: 'grabando' })
    } else if (g.estado === 'pausada') {
      if (this.grabadora?.state === 'recording') this.grabadora.pause()
      this.poner({ fase: 'pausada' })
    } else if (g.estado === 'terminando') {
      if (!this.cerrando) void this.terminar()
    } else if (g.estado === 'procesando' || g.estado === 'terminada' || g.estado === 'error') {
      this.activo = false
      this.liberar()
      this.poner({ fase: 'finalizado' })
    }
  }

  // --- grabar y subir ---------------------------------------------------------------------------

  private async empezarGrabadora() {
    if (!this.flujo || this.flujo.getAudioTracks()[0]?.readyState === 'ended') {
      this.liberarMicrofono()
      await this.abrirMicrofono() // el sistema cortó el micrófono (p. ej. el celular se durmió): se vuelve a abrir
    }
    const formato = FORMATOS.find((f) => MediaRecorder.isTypeSupported(f))
    const grabadora = new MediaRecorder(this.flujo!, formato ? { mimeType: formato, audioBitsPerSecond: 32_000 } : undefined)
    grabadora.ondataavailable = (e) => {
      if (e.data.size > 0) {
        this.cola.push({ n: this.siguiente++, trozo: e.data })
        this.poner({ pendientes: this.cola.length })
        void this.vaciar()
      }
    }
    grabadora.onerror = () => this.poner({ mensaje: 'La grabadora de este navegador falló; se intentará de nuevo.' })
    grabadora.start(TROZO_MS)
    this.grabadora = grabadora
  }

  private async vaciar() {
    if (this.subiendo) return
    this.subiendo = true
    try {
      while (this.cola.length > 0) {
        const { n, trozo } = this.cola[0]
        try {
          await subirTrozo(this.grabacionId, n, this.equipo, trozo)
          this.cola.shift()
          this.poner({ pendientes: this.cola.length, mensaje: null })
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            this.cola = [] // otro equipo tomó la grabación: este audio ya no sirve
            break
          }
          if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 0) {
            this.cola.shift() // el servidor lo rechazó (formato, tamaño): reintentar no lo arregla
            this.poner({ pendientes: this.cola.length, mensaje: `Un trozo de audio fue rechazado: ${e.message}` })
            continue
          }
          this.poner({ mensaje: 'Sin conexión con el servidor: el audio se sigue guardando aquí y se subirá cuando vuelva.' })
          await new Promise((r) => setTimeout(r, 2_000)) // sin red o servidor caído: reintentar
          if (!this.activo && !this.cerrando) break
        }
      }
    } finally {
      this.subiendo = false
    }
  }

  private async terminar() {
    this.cerrando = true
    this.poner({ fase: 'terminando' })
    const grabadora = this.grabadora
    if (grabadora && grabadora.state !== 'inactive') {
      await new Promise<void>((resolver) => {
        grabadora.addEventListener('stop', () => resolver(), { once: true })
        grabadora.stop() // entrega el último trozo antes de 'stop'
      })
    }
    const limite = Date.now() + ESPERA_FINAL_MS
    while (this.cola.length > 0 && Date.now() < limite) {
      void this.vaciar()
      await new Promise((r) => setTimeout(r, 300))
    }
    try {
      await api<Grabacion>(`/grabaciones/${this.grabacionId}/finalizar`, { metodo: 'POST', cuerpo: { dispositivo: this.equipo } })
    } catch {
      /* si no llega, el servidor procesa lo recibido pasados unos segundos */
    }
    this.activo = false
    this.liberar()
    this.poner({ fase: 'finalizado' })
  }

  // --- limpieza ----------------------------------------------------------------------------------

  private detenerGrabadora() {
    if (this.grabadora && this.grabadora.state !== 'inactive') {
      this.grabadora.ondataavailable = null
      this.grabadora.stop()
    }
    this.grabadora = null
    this.cola = []
  }

  private liberarMicrofono() {
    this.flujo?.getTracks().forEach((t) => t.stop())
    this.flujo = null
    void this.contexto?.close().catch(() => undefined)
    this.contexto = null
    this.analizador = null
  }

  private liberar() {
    clearInterval(this.latidoId)
    clearInterval(this.relojId)
    document.removeEventListener('visibilitychange', this.alVolver)
    this.liberarMicrofono()
    void this.bloqueo?.release().catch(() => undefined)
    this.bloqueo = null
  }

  private textoDeError(e: unknown): string {
    if (e instanceof ApiError) return e.message
    const nombre = (e as { name?: string })?.name
    if (nombre === 'NotAllowedError') return 'No diste permiso para usar el micrófono. Actívalo en el navegador y vuelve a intentarlo.'
    if (nombre === 'NotFoundError') return 'No se encontró ningún micrófono en este equipo.'
    return 'No se pudo usar el micrófono de este equipo.'
  }
}

// --- El equipo grabador de este navegador -----------------------------------------------------------
// Vive fuera de los componentes a propósito: si el profesor cambia de pestaña mientras graba, la grabación
// no se interrumpe. Solo se detiene al soltarlo, al terminar la clase o al cerrar la sesión.

const INACTIVO: InfoGrabador = { fase: 'inactivo', nivel: 0, segundos: 0, pendientes: 0, mensaje: null }
interface EstadoEquipo {
  info: InfoGrabador
  grabacionId: number | null
}
let actual: Grabador | null = null
let estado: EstadoEquipo = { info: INACTIVO, grabacionId: null }
const oyentes = new Set<() => void>()
const publicar = (cambio: Partial<EstadoEquipo>) => {
  estado = { ...estado, ...cambio }
  oyentes.forEach((f) => f())
}

/** Este navegador pasa a ser el equipo que graba la clase. Lanza el error si no se pudo (sin permiso, otro equipo graba...). */
export async function activarEquipo(g: Grabacion, forzar: boolean): Promise<void> {
  soltarEquipo()
  const grabador = new Grabador(g.id, idDeEsteEquipo(), g.trozos, g.segundos_grabados, (info) => publicar({ info }))
  actual = grabador
  publicar({ grabacionId: g.id })
  await grabador.conectar(forzar)
}

export function soltarEquipo(): void {
  actual?.soltar()
  actual = null
  publicar({ info: INACTIVO, grabacionId: null })
}

/** Cuando este navegador está grabando o listo para grabar (y por lo tanto no hay que cortarlo). */
export const equipoActivo = (i: InfoGrabador) => i.fase === 'listo' || i.fase === 'grabando' || i.fase === 'pausada' || i.fase === 'terminando'

export function useEquipo(): EstadoEquipo {
  return useSyncExternalStore(
    (f) => {
      oyentes.add(f)
      return () => oyentes.delete(f)
    },
    () => estado,
  )
}
