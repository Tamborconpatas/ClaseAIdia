/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useState, type FormEvent } from 'react'
import { Download, Info, Loader2 } from 'lucide-react'
import { Cargando, ErrorForm, Requisito } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api, type AjusteClases, type AjusteFotos, type AjusteModeloTexto, type AjusteRespaldos, type DescargaModelo } from '@/lib/api'
import { CREDITO } from '@/lib/autoria'
import { useCarga, useSondeo } from '@/lib/usar'
import { cn } from '@/lib/utils'

/** Con menos memoria que esto las fotos casi siempre se saltan solas al procesar (medido; ver el README). */
const MEMORIA_MINIMA_GB = 12

/**
 * Ajustes del colegio. El UTP decide aquí lo que en otras aplicaciones se tocaría en un archivo de configuración: la app se
 * reparte portable y nadie edita archivos ni escribe comandos. Hoy: el modelo que escribe los resúmenes (necesario), cómo se tratan
 * las clases (plazo de revisión y corte automático), el respaldo diario y las fotos de la pizarra (opcionales).
 */
export function Ajustes() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <ModeloDeResumenes />
      <ClasesDelColegio />
      <RespaldosDelServidor />
      <FotosDePizarra />
      <p className="text-center text-xs text-muted-foreground">{CREDITO}</p>
    </div>
  )
}

function FotosDePizarra() {
  const ajuste = useSondeo(() => api<AjusteFotos>('/ajustes/fotos-pizarra'), 3000, [])
  const [trabajando, setTrabajando] = useState<'cambiar' | 'descargar' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const d = ajuste.datos

  const ejecutar = async (que: 'cambiar' | 'descargar', llamada: () => Promise<AjusteFotos>) => {
    setError(null)
    setTrabajando(que)
    try {
      ajuste.fijar(await llamada()) // el pedido devuelve el estado nuevo: se ve ya, sin esperar la siguiente consulta
      ajuste.actualizar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(null)
    }
  }

  if (!d) return ajuste.sinConexion ? <ErrorForm mensaje="No se pudo conectar con el servidor." /> : <Cargando />

  const memoriaAlcanza = d.memoria_total_gb === null ? null : d.memoria_total_gb >= MEMORIA_MINIMA_GB

  return (
    <>
      <section aria-labelledby="titulo-fotos" className="space-y-4 rounded-2xl border bg-card p-4 desk:p-5">
        <div>
          <h2 id="titulo-fotos" className="text-lg font-semibold">
            Fotos de la pizarra <span className="text-sm font-normal text-muted-foreground">(opcional)</span>
          </h2>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Los profesores sacan una foto de la pizarra con su celular durante la clase. Después de la clase, la IA lee lo escrito y lo suma al material de
            estudio. La foto se borra apenas se lee: solo queda el texto. La transcripción y el resumen funcionan igual sin esto.
          </p>
        </div>

        <div className="flex items-center justify-between gap-4 rounded-xl bg-muted/50 p-3.5">
          <div>
            <p id="etiqueta-fotos" className="font-medium">Permitir fotos de la pizarra</p>
            <p className="text-sm text-muted-foreground">{d.activada ? 'Activadas: los profesores ven el botón «Foto de la pizarra».' : 'Apagadas: el botón no aparece.'}</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={d.activada}
            aria-labelledby="etiqueta-fotos"
            disabled={trabajando !== null}
            onClick={() => void ejecutar('cambiar', () => api<AjusteFotos>('/ajustes/fotos-pizarra', { metodo: 'PUT', cuerpo: { activada: !d.activada } }))}
            className={cn(
              'relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border-2 border-transparent transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-60',
              d.activada ? 'bg-primary' : 'bg-input',
            )}
          >
            <span className={cn('pointer-events-none block size-6 rounded-full bg-background shadow transition-transform', d.activada ? 'translate-x-6' : 'translate-x-0.5')} />
          </button>
        </div>
        <p role="status" aria-live="polite" className="sr-only">{d.activada ? 'Fotos de la pizarra activadas.' : 'Fotos de la pizarra apagadas.'}</p>

        <div>
          <h3 className="mb-2 text-sm font-semibold">Antes de activarlas, revisa</h3>
          <ul className="space-y-3">
            <Requisito ok={memoriaAlcanza} titulo="Memoria del equipo">
              {d.memoria_total_gb === null
                ? 'No se pudo medir la memoria de este equipo. Se recomiendan al menos 16 GB.'
                : memoriaAlcanza
                  ? `Este equipo tiene ${d.memoria_total_gb.toLocaleString('es-CL')} GB de memoria: alcanza para leer fotos.`
                  : `Este equipo tiene ${d.memoria_total_gb.toLocaleString('es-CL')} GB de memoria. Es poca: lo normal es que las fotos se salten solas al procesar (la clase se procesa igual, sin ellas). Se recomiendan ${d.memoria_recomendada_gb} GB.`}
            </Requisito>

            <Requisito ok={d.ollama_responde} titulo="Programa de IA (Ollama)">
              {d.ollama_responde ? 'Está funcionando en este equipo.' : 'No responde por ahora. Al descargar el modelo la aplicación intenta abrirlo; si no está instalado en este equipo, instálalo desde ollama.com.'}
            </Requisito>

            <RequisitoModelo
              titulo="Modelo de lectura de imágenes"
              etiqueta="Descargar el modelo de imágenes"
              instalado={d.modelo_instalado}
              tamanoGb={3.2}
              descarga={d.descarga}
              trabajando={trabajando === 'descargar'}
              ocupado={trabajando !== null} // con Ollama cerrado también se puede pedir: la aplicación intenta abrirlo ella misma
              onDescargar={() => void ejecutar('descargar', () => api<AjusteFotos>('/ajustes/fotos-pizarra/modelo', { metodo: 'POST' }))}
            />
          </ul>
        </div>

        <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          Cada foto suma entre 10 y 50 segundos al procesamiento de la clase (medido sin tarjeta gráfica, en un equipo rápido; uno más antiguo puede tardar el doble). Lo que
          lee bien: letra clara, listas y esquemas. En matemática escrita a mano puede cambiar cifras: por eso el profesor revisa y corrige antes de aprobar.
        </p>
        <ErrorForm mensaje={error} />
      </section>
    </>
  )
}

/** El modelo que escribe los resúmenes. Sin él ninguna clase se puede resumir: por eso se baja desde aquí y no con una consola. */
function ModeloDeResumenes() {
  const ajuste = useSondeo(() => api<AjusteModeloTexto>('/ajustes/modelo-texto'), 3000, [])
  const [trabajando, setTrabajando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const d = ajuste.datos

  const descargar = async () => {
    setError(null)
    setTrabajando(true)
    try {
      ajuste.fijar(await api<AjusteModeloTexto>('/ajustes/modelo-texto/descargar', { metodo: 'POST' })) // se ve ya, sin esperar la siguiente consulta
      ajuste.actualizar()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(false)
    }
  }

  if (!d) return ajuste.sinConexion ? <ErrorForm mensaje="No se pudo conectar con el servidor." /> : <Cargando />

  const alcanza = d.memoria_total_gb === null ? null : d.memoria_total_gb >= d.memoria_minima_gb
  return (
    <section aria-labelledby="titulo-resumenes" className="space-y-4 rounded-2xl border bg-card p-4 desk:p-5">
      <div>
        <h2 id="titulo-resumenes" className="text-lg font-semibold">
          Modelo que escribe los resúmenes <span className="text-sm font-normal text-muted-foreground">(necesario)</span>
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          La IA que resume las clases corre en este equipo y necesita su modelo ({d.modelo}). Se descarga una sola vez; sin él ninguna clase se puede resumir.
        </p>
      </div>
      <ul className="space-y-3">
        <Requisito ok={alcanza} titulo="Memoria del equipo">
          {d.memoria_total_gb === null
            ? `No se pudo medir la memoria de este equipo. Se recomiendan al menos ${d.memoria_minima_gb} GB.`
            : alcanza
              ? `Este equipo tiene ${d.memoria_total_gb.toLocaleString('es-CL')} GB de memoria: alcanza.`
              : `Este equipo tiene ${d.memoria_total_gb.toLocaleString('es-CL')} GB de memoria. Es poca: si el modelo no cabe, la aplicación usa uno más liviano (resúmenes más simples y sin mapa conceptual). Se recomiendan ${d.memoria_minima_gb} GB.`}
        </Requisito>
        <Requisito ok={d.ollama_responde} titulo="Programa de IA (Ollama)">
          {d.ollama_responde ? 'Está funcionando en este equipo.' : 'No responde por ahora. Al descargar el modelo la aplicación intenta abrirlo; si no está instalado en este equipo, instálalo desde ollama.com.'}
        </Requisito>
        <RequisitoModelo
          titulo="Modelo de resúmenes"
          etiqueta="Descargar el modelo de resúmenes"
          instalado={d.modelo_instalado}
          tamanoGb={d.tamano_gb}
          descarga={d.descarga}
          trabajando={trabajando}
          ocupado={trabajando}
          onDescargar={() => void descargar()}
        />
      </ul>
      <ErrorForm mensaje={error} />
    </section>
  )
}

/** Un número entero que el UTP puede cambiar, con su rango y lo que significa. */
function CampoNumerico({ id, etiqueta, ayuda, valor, onCambio, min, max }: {
  id: string
  etiqueta: string
  ayuda: string
  valor: string
  onCambio: (v: string) => void
  min: number
  max: number
}) {
  const n = Number(valor)
  const ok = valor.trim() !== '' && Number.isInteger(n) && n >= min && n <= max
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium">{etiqueta}</label>
      <Input id={id} type="number" inputMode="numeric" min={min} max={max} value={valor} aria-invalid={!ok} aria-describedby={`${id}-ayuda`} onChange={(e) => onCambio(e.target.value)} className="h-11 w-28 text-base desk:h-9 desk:text-sm" />
      <p id={`${id}-ayuda`} className={cn('text-xs leading-relaxed', ok ? 'text-muted-foreground' : 'text-destructive')}>
        {ok ? ayuda : `Escribe un número entero de ${min} a ${max}.`}
      </p>
    </div>
  )
}

/** Plazo de revisión del profesor y corte automático de la grabación: reglas de este colegio. */
function ClasesDelColegio() {
  const carga = useCarga(() => api<AjusteClases>('/ajustes/clases'), [])
  if (carga.error) return <ErrorForm mensaje={carga.error} />
  if (!carga.datos) return <Cargando />
  return <FormularioClases inicial={carga.datos} />
}

function FormularioClases({ inicial }: { inicial: AjusteClases }) {
  const [guardado, setGuardado] = useState(inicial)
  const [horas, setHoras] = useState(String(inicial.horas_revision))
  const [minutos, setMinutos] = useState(String(inicial.minutos_corte))
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState('')
  const [h0, h1] = guardado.rango_horas_revision
  const [m0, m1] = guardado.rango_minutos_corte
  const valido = Number.isInteger(Number(horas)) && horas.trim() !== '' && Number(horas) >= h0 && Number(horas) <= h1 && Number.isInteger(Number(minutos)) && minutos.trim() !== '' && Number(minutos) >= m0 && Number(minutos) <= m1
  const cambio = Number(horas) !== guardado.horas_revision || Number(minutos) !== guardado.minutos_corte
  const propio = guardado.horas_revision !== guardado.horas_revision_por_defecto || guardado.minutos_corte !== guardado.minutos_corte_por_defecto

  const enviar = async (h: number | null, m: number | null) => {
    setEnviando(true)
    setError(null)
    setAviso('')
    try {
      const nuevo = await api<AjusteClases>('/ajustes/clases', { metodo: 'PUT', cuerpo: { horas_revision: h, minutos_corte: m } })
      setGuardado(nuevo)
      setHoras(String(nuevo.horas_revision))
      setMinutos(String(nuevo.minutos_corte))
      setAviso('Guardado. Vale desde ahora.')
    } catch (e) {
      setError((e as Error).message)
    }
    setEnviando(false)
  }
  const guardar = (e: FormEvent) => {
    e.preventDefault()
    void enviar(Number(horas), Number(minutos))
  }

  return (
    <section aria-labelledby="titulo-clases" className="space-y-4 rounded-2xl border bg-card p-4 desk:p-5">
      <div>
        <h2 id="titulo-clases" className="text-lg font-semibold">Revisión y corte de las clases</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">Dos reglas de este colegio sobre cómo se tratan las clases.</p>
      </div>
      <form onSubmit={guardar} className="space-y-4">
        <CampoNumerico
          id="horas-revision"
          etiqueta="Horas para que el profesor revise el material"
          ayuda={`Pasado este plazo sin revisar, el material se publica igual como «provisorio», con una advertencia para los alumnos. Lo predeterminado es ${guardado.horas_revision_por_defecto} horas.`}
          valor={horas}
          onCambio={setHoras}
          min={h0}
          max={h1}
        />
        <CampoNumerico
          id="minutos-corte"
          etiqueta="Minutos de gracia del corte automático"
          ayuda={`Si el profesor olvida terminar la grabación, se corta sola pasados estos minutos del término del bloque. Lo predeterminado es ${guardado.minutos_corte_por_defecto} minutos.`}
          valor={minutos}
          onCambio={setMinutos}
          min={m0}
          max={m1}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" className="h-11 desk:h-9" disabled={enviando || !valido || !cambio}>
            {enviando && <Loader2 className="animate-spin" />} Guardar
          </Button>
          {propio && (
            <Button type="button" variant="ghost" className="h-11 desk:h-9" disabled={enviando} onClick={() => void enviar(null, null)}>
              Volver a lo predeterminado
            </Button>
          )}
        </div>
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">{aviso}</p>
        <ErrorForm mensaje={error} />
      </form>
    </section>
  )
}

/** Dónde se guarda el respaldo diario de la base y cuántos días se conservan. Vale para todo el servidor. */
function RespaldosDelServidor() {
  const carga = useCarga(() => api<AjusteRespaldos>('/ajustes/respaldos'), [])
  if (carga.error) return <ErrorForm mensaje={carga.error} />
  if (!carga.datos) return <Cargando />
  return <FormularioRespaldos inicial={carga.datos} />
}

function FormularioRespaldos({ inicial }: { inicial: AjusteRespaldos }) {
  const [guardado, setGuardado] = useState(inicial)
  const [carpeta, setCarpeta] = useState(inicial.carpeta)
  const [dias, setDias] = useState(String(inicial.dias))
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState('')
  const [d0, d1] = guardado.rango_dias
  const diasValidos = dias.trim() !== '' && Number.isInteger(Number(dias)) && Number(dias) >= d0 && Number(dias) <= d1
  const valido = carpeta.trim() !== '' && diasValidos
  const cambio = carpeta.trim() !== guardado.carpeta || Number(dias) !== guardado.dias
  const propio = guardado.carpeta !== guardado.carpeta_por_defecto || guardado.dias !== guardado.dias_por_defecto

  const enviar = async (c: string | null, d: number | null) => {
    setEnviando(true)
    setError(null)
    setAviso('')
    try {
      const nuevo = await api<AjusteRespaldos>('/ajustes/respaldos', { metodo: 'PUT', cuerpo: { carpeta: c, dias: d } })
      setGuardado(nuevo)
      setCarpeta(nuevo.carpeta)
      setDias(String(nuevo.dias))
      setAviso('Guardado. Vale desde el próximo respaldo, que se hace una vez al día.')
    } catch (e) {
      setError((e as Error).message)
    }
    setEnviando(false)
  }
  const guardar = (e: FormEvent) => {
    e.preventDefault()
    void enviar(carpeta.trim() === guardado.carpeta_por_defecto ? null : carpeta.trim(), Number(dias) === guardado.dias_por_defecto ? null : Number(dias))
  }

  return (
    <section aria-labelledby="titulo-respaldos" className="space-y-4 rounded-2xl border bg-card p-4 desk:p-5">
      <div>
        <h2 id="titulo-respaldos" className="text-lg font-semibold">Respaldo diario</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          Una vez al día se copia la base de datos (horario, usuarios y texto de las clases; nunca audio). Esto vale para todo el servidor.
        </p>
      </div>
      <form onSubmit={guardar} className="space-y-4">
        <div className="space-y-1">
          <label htmlFor="carpeta-respaldos" className="text-sm font-medium">Carpeta de los respaldos</label>
          <Input id="carpeta-respaldos" value={carpeta} maxLength={300} aria-describedby="carpeta-respaldos-ayuda" onChange={(e) => setCarpeta(e.target.value)} className="h-11 text-base desk:h-9 desk:text-sm" />
          <p id="carpeta-respaldos-ayuda" className="text-xs leading-relaxed text-muted-foreground">
            Escribe la ruta completa. Conviene que sea otro disco o una unidad externa: una copia en el mismo disco no protege si el disco falla. Si la carpeta no existe se crea, y antes de
            guardar se comprueba que se pueda escribir en ella. Los respaldos ya hechos quedan donde estaban.
          </p>
        </div>
        <CampoNumerico
          id="dias-respaldo"
          etiqueta="Días de respaldos que se conservan"
          ayuda={`Las copias más antiguas se borran solas. Lo predeterminado es ${guardado.dias_por_defecto} días.`}
          valor={dias}
          onCambio={setDias}
          min={d0}
          max={d1}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" className="h-11 desk:h-9" disabled={enviando || !valido || !cambio}>
            {enviando && <Loader2 className="animate-spin" />} Guardar
          </Button>
          {propio && (
            <Button type="button" variant="ghost" className="h-11 desk:h-9" disabled={enviando} onClick={() => void enviar(null, null)}>
              Volver a lo predeterminado
            </Button>
          )}
        </div>
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">{aviso}</p>
        <ErrorForm mensaje={error} />
      </form>
    </section>
  )
}

/** La fila «modelo» de una lista de requisitos: instalado, o el botón para bajarlo con su barra de avance. */
function RequisitoModelo({ titulo, etiqueta, instalado, tamanoGb, descarga, trabajando, ocupado, onDescargar }: {
  titulo: string
  etiqueta: string
  instalado: boolean
  tamanoGb: number | null
  descarga: DescargaModelo | null
  trabajando: boolean
  ocupado: boolean
  onDescargar: () => void
}) {
  const descargando = descarga?.estado === 'descargando'
  return (
    <Requisito ok={instalado} titulo={titulo}>
      {instalado ? (
        'Instalado.'
      ) : (
        <>
          Falta descargarlo{tamanoGb ? ` (${tamanoGb.toLocaleString('es-CL')} GB)` : ''}. Hace falta internet, y solo una vez.
          {/* Al pulsar, la barra aparece ya (no hay que esperar la respuesta del servidor). */}
          {trabajando && <Avance porcentaje={0} mensaje="Preparando la descarga…" />}
          {!trabajando && descargando && descarga && <Avance porcentaje={descarga.porcentaje} mensaje={descarga.mensaje} />}
          {descarga?.estado === 'error' && <ErrorForm mensaje={descarga.mensaje} />}
          {!descargando && !trabajando && (
            <div className="mt-2">
              <Button variant="outline" className="h-11 desk:h-9" disabled={ocupado} onClick={onDescargar}>
                <Download />
                {descarga?.estado === 'error' ? 'Reintentar la descarga' : etiqueta}
              </Button>
            </div>
          )}
        </>
      )}
    </Requisito>
  )
}

function Avance({ porcentaje, mensaje }: { porcentaje: number; mensaje: string }) {
  return (
    <div className="mt-2 space-y-1">
      <div
        role="progressbar"
        aria-label="Descarga del modelo"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(porcentaje)}
        className="h-2.5 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${porcentaje}%` }} />
      </div>
      <p aria-live="polite" className="text-xs">
        {mensaje} {Math.round(porcentaje)} %
      </p>
    </div>
  )
}
