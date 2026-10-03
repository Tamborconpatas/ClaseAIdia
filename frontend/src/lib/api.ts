// El backend vive detrás de /api (proxy de Vite en desarrollo, mismo servidor en producción).
const BASE = '/api'
const CLAVE = 'claseaidia.sesion'

export type Rol = 'ALUMNO' | 'PROFESOR' | 'UTP'
export type TipoBloque = 'CLASE' | 'RECREO' | 'ALMUERZO'

export interface Sesion {
  access_token: string
  roles: Rol[]
  colegio_id: number
}
export interface Usuario {
  id: number
  rut: string
  nombre: string
  colegio_id: number
  /** Falso: el personal que se fue; no entra, pero su nombre queda en horarios y clases. */
  activo: boolean
  roles: Rol[]
}
export interface Curso {
  id: number
  nombre: string
  colegio_id: number
}
export interface Bloque {
  id: number
  curso_id: number
  tipo: TipoBloque
  asignatura: string | null
  profesor_id: number | null
  profesor_nombre: string | null
  sala: string | null
  dia_semana: number // 0 = lunes
  hora_inicio: string // "08:00:00"
  hora_fin: string
}

export interface AlumnoDeCurso {
  id: number
  nombre: string
  rut: string
}
export interface ResetPin {
  codigo: string
  vence: string // ISO con zona (UTC)
}

export type EstadoClase = 'grabando' | 'procesando' | 'error' | 'por_aprobar' | 'provisoria' | 'publicada' | 'retirada'
export interface ClaseResumen {
  id: number
  bloque_id: number
  fecha: string // "2026-09-28"
  curso_id: number
  curso_nombre: string
  asignatura: string | null
  sala: string | null
  hora_inicio: string
  hora_fin: string
  profesor_id: number | null
  estado: EstadoClase
  /** Hasta cuándo puede el profesor revisarla antes de que se publique como provisoria (solo en por_aprobar). */
  revision_vence: string | null
  prioritaria: boolean
}
export interface Tarjeta {
  pregunta: string
  respuesta: string
}
import type { Relacion } from '@/lib/mapa'
export interface PizarraLeida {
  id: number
  segundo: number
  /** Markdown con LaTeX (`$...$`, `$$...$$`) y, a veces, un bloque ```mermaid. */
  texto: string
}
export interface ClaseDetalle extends ClaseResumen {
  contenido: {
    resumen: string | null
    puntos_clave: string | null
    hoja_repaso: string | null
    tarjetas: Tarjeta[]
    transcripcion_texto: string | null
    pizarra: PizarraLeida[]
    mapa: Relacion[]
  } | null
}

export type EstadoGrabacion = 'esperando' | 'grabando' | 'pausada' | 'terminando' | 'procesando' | 'terminada' | 'error'
export type AccionGrabacion =
  | 'iniciar' | 'pausar' | 'reanudar' | 'silenciar' | 'activar_audio' | 'terminar' | 'cancelar' | 'marcar_prioritaria' | 'quitar_prioritaria'
export interface FotoPizarra {
  id: number
  /** Segundo de la clase en que se sacó. */
  segundo: number
  estado: 'pendiente' | 'leida' | 'error'
  /** Lo que leyó el modelo de visión; la imagen no se guarda. */
  texto: string | null
  error: string | null
}
export interface Grabacion {
  id: number
  clase_id: number
  bloque_id: number
  asignatura: string | null
  curso_nombre: string
  sala: string | null
  fecha: string
  hora_inicio: string
  hora_fin: string
  estado: EstadoGrabacion
  silenciada: boolean
  prioritaria: boolean
  /** Hora local (sin zona) en que se corta sola. */
  corte_en: string
  segundos_grabados: number
  nivel: number
  trozos: number
  grabador_id: string | null
  grabador_conectado: boolean
  error: string | null
  /** Si el fallo se reintenta solo, cuándo (UTC); null si ya no quedan intentos. */
  reintento_en: string | null
  fotos: FotoPizarra[]
  /** El colegio activó las fotos de la pizarra (FOTOS_PIZARRA=si en el servidor). */
  fotos_habilitadas: boolean
}
export interface DescargaModelo {
  estado: 'descargando' | 'lista' | 'error'
  porcentaje: number
  mensaje: string
}
/** Lo que el UTP necesita para decidir si activa las fotos de la pizarra y dejarlas listas sin una consola. */
export interface AjusteFotos {
  activada: boolean
  modelo: string
  ollama_responde: boolean
  modelo_instalado: boolean
  memoria_total_gb: number | null
  memoria_recomendada_gb: number
  descarga: DescargaModelo | null
}
export interface BloqueDeHoy {
  bloque_id: number
  asignatura: string | null
  curso_nombre: string
  sala: string | null
  hora_inicio: string
  hora_fin: string
  puede_grabar: boolean
  motivo: string | null
  grabacion: Grabacion | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// La sesión se guarda en localStorage (el token vence solo, a las 12 h). Es razonable mientras la app
// no use dangerouslySetInnerHTML: un token en localStorage solo se roba con XSS.
export function leerSesion(): Sesion | null {
  try {
    const crudo = localStorage.getItem(CLAVE)
    return crudo ? (JSON.parse(crudo) as Sesion) : null
  } catch {
    return null
  }
}
export function guardarSesion(s: Sesion | null) {
  try {
    if (s) localStorage.setItem(CLAVE, JSON.stringify(s))
    else localStorage.removeItem(CLAVE)
  } catch {
    /* modo privado / almacenamiento bloqueado: la sesión dura lo que dure la pestaña */
  }
}

// FastAPI devuelve `detail` como texto o como lista de errores de validación.
function mensajeDe(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((e) => String((e as { msg?: string }).msg ?? '').replace(/^Value error, /, ''))
      .filter(Boolean)
      .join('. ')
  }
  return 'Algo salió mal. Intenta de nuevo.'
}

export async function api<T>(
  ruta: string,
  { metodo = 'GET', cuerpo, sesion }: { metodo?: string; cuerpo?: unknown; sesion?: Sesion | null } = {},
): Promise<T> {
  const cabeceras: Record<string, string> = {}
  if (cuerpo !== undefined) cabeceras['Content-Type'] = 'application/json'
  const token = (sesion ?? leerSesion())?.access_token
  if (token) cabeceras.Authorization = `Bearer ${token}`

  let r: Response
  try {
    r = await fetch(BASE + ruta, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor.')
  }
  if (r.status === 401 && token) window.dispatchEvent(new Event('claseaidia:sesion-vencida'))
  if (!r.ok) {
    const datos = await r.json().catch(() => null)
    const detalle = (datos as { detail?: unknown } | null)?.detail
    // Un 5xx sin cuerpo JSON es del proxy o del servidor caído, no de una validación.
    const caido = detalle === undefined && r.status >= 500
    throw new ApiError(r.status, caido ? 'El servidor no está disponible en este momento. Intenta de nuevo en un rato.' : mensajeDe(detalle))
  }
  return r.status === 204 ? (undefined as T) : ((await r.json()) as T)
}

/** Sube un trozo de audio (cuerpo crudo, no JSON). Devuelve el estado de la grabación. */
export async function subirFoto(grabacionId: number, foto: Blob, segundo: number): Promise<Grabacion> {
  const token = leerSesion()?.access_token
  let r: Response
  try {
    r = await fetch(`${BASE}/grabaciones/${grabacionId}/fotos?segundo=${Math.max(0, Math.floor(segundo))}`, {
      method: 'POST',
      headers: { 'Content-Type': foto.type || 'image/jpeg', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: foto,
    })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor.')
  }
  if (!r.ok) {
    const datos = await r.json().catch(() => null)
    throw new ApiError(r.status, mensajeDe((datos as { detail?: unknown } | null)?.detail))
  }
  return (await r.json()) as Grabacion
}

export async function subirTrozo(grabacionId: number, n: number, dispositivo: string, trozo: Blob): Promise<Grabacion> {
  const token = leerSesion()?.access_token
  let r: Response
  try {
    r = await fetch(`${BASE}/grabaciones/${grabacionId}/trozos/${n}?dispositivo=${encodeURIComponent(dispositivo)}`, {
      method: 'PUT',
      headers: { 'Content-Type': trozo.type || 'audio/webm', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: trozo,
    })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor.')
  }
  if (!r.ok) {
    const datos = await r.json().catch(() => null)
    throw new ApiError(r.status, mensajeDe((datos as { detail?: unknown } | null)?.detail))
  }
  return (await r.json()) as Grabacion
}
