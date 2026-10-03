import { useState } from 'react'
import { Download, Info } from 'lucide-react'
import { Cargando, ErrorForm, Requisito } from '@/components/comunes'
import { Button } from '@/components/ui/button'
import { api, type AjusteFotos } from '@/lib/api'
import { useSondeo } from '@/lib/usar'
import { cn } from '@/lib/utils'

/** Con menos memoria que esto las fotos casi siempre se saltan solas al procesar (medido; ver el README). */
const MEMORIA_MINIMA_GB = 12

/**
 * Ajustes del colegio. El UTP decide aquí lo que en otras aplicaciones se tocaría en un archivo de configuración: la app se
 * reparte portable y nadie edita archivos ni escribe comandos. Hoy: las fotos de la pizarra, que son opcionales.
 */
export function Ajustes() {
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

  const descargando = d.descarga?.estado === 'descargando'
  const memoriaAlcanza = d.memoria_total_gb === null ? null : d.memoria_total_gb >= MEMORIA_MINIMA_GB

  return (
    <div className="mx-auto max-w-2xl space-y-4">
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

            <Requisito ok={d.modelo_instalado} titulo="Modelo de lectura de imágenes">
              {d.modelo_instalado ? (
                'Instalado.'
              ) : (
                <>
                  Falta descargarlo (3,2 GB). Hace falta internet, y solo una vez.
                  {/* Al pulsar, la barra aparece ya (no hay que esperar la respuesta del servidor). */}
                  {trabajando === 'descargar' && <Avance porcentaje={0} mensaje="Preparando la descarga…" />}
                  {trabajando !== 'descargar' && descargando && d.descarga && <Avance porcentaje={d.descarga.porcentaje} mensaje={d.descarga.mensaje} />}
                  {d.descarga?.estado === 'error' && <ErrorForm mensaje={d.descarga.mensaje} />}
                  {!descargando && trabajando !== 'descargar' && (
                    <div className="mt-2">
                      <Button
                        variant="outline"
                        className="h-11 desk:h-9"
                        disabled={trabajando !== null} // con Ollama cerrado también se puede pedir: la aplicación intenta abrirlo ella misma
                        onClick={() => void ejecutar('descargar', () => api<AjusteFotos>('/ajustes/fotos-pizarra/modelo', { metodo: 'POST' }))}
                      >
                        <Download />
                        {d.descarga?.estado === 'error' ? 'Reintentar la descarga' : 'Descargar el modelo'}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </Requisito>
          </ul>
        </div>

        <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
          <Info className="mt-0.5 size-3.5 shrink-0" />
          Cada foto suma entre 10 y 50 segundos al procesamiento de la clase (medido sin tarjeta gráfica, en un equipo rápido; uno más antiguo puede tardar el doble). Lo que
          lee bien: letra clara, listas y esquemas. En matemática escrita a mano puede cambiar cifras: por eso el profesor revisa y corrige antes de aprobar.
        </p>
        <ErrorForm mensaje={error} />
      </section>
    </div>
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
