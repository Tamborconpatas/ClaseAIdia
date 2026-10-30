/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Cargando, ErrorForm, Requisito } from '@/components/comunes'
import { api, type EstadoServidor } from '@/lib/api'
import { fechaCorta } from '@/lib/horario'
import { useSondeo } from '@/lib/usar'
import { cn } from '@/lib/utils'

const CADA_MS = 10_000

const VERDE = 'bg-emerald-100 text-emerald-900 ring-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:ring-emerald-800'
const AMBAR = 'bg-amber-100 text-amber-900 ring-amber-200 dark:bg-amber-950/60 dark:text-amber-200 dark:ring-amber-800'
const ROJO = 'bg-red-100 text-red-900 ring-red-200 dark:bg-red-950/60 dark:text-red-200 dark:ring-red-800'

const num = (n: number, decimales = 1) => n.toLocaleString('es-CL', { maximumFractionDigits: decimales })
const tamaño = (mb: number) => (mb >= 1000 ? `${num(mb / 1000)} GB` : `${num(mb, mb < 10 ? 1 : 0)} MB`)
const hora = (iso: string) => new Date(iso).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
const hace = (dias: number) => (dias === 0 ? 'hoy' : dias === 1 ? 'ayer' : `hace ${dias} días`)
const ESTADO_EN_VIVO: Record<string, string> = { esperando: 'esperando que empiece', grabando: 'grabando', pausada: 'en pausa', terminando: 'terminando de recibir el audio' }

/**
 * Panel de estado para el UTP. El servidor corre 24/7 y casi nadie lo mira: aquí se ve qué se está procesando y se entera a tiempo de que
 * algo anda mal (disco, respaldos, IA apagada) sin abrir una consola. Los avisos los redacta el servidor; esta pantalla solo los muestra.
 */
export function Estado() {
  const estado = useSondeo(() => api<EstadoServidor>('/estado'), CADA_MS, [])
  const e = estado.datos
  if (!e) return estado.sinConexion ? <ErrorForm mensaje="No se pudo conectar con el servidor." /> : <Cargando />

  const { procesamiento: p, ollama: o, disco: d, respaldos: r, memoria: m, vigilancia: v } = e
  const urgentes = e.alertas.filter((a) => a.nivel === 'critico').length
  const resumen =
    e.alertas.length === 0
      ? 'Todo en orden.'
      : `${urgentes ? `${urgentes} ${urgentes === 1 ? 'problema urgente' : 'problemas urgentes'}` : ''}${urgentes && e.alertas.length > urgentes ? ' y ' : ''}${
          e.alertas.length > urgentes ? `${e.alertas.length - urgentes} ${e.alertas.length - urgentes === 1 ? 'aviso' : 'avisos'}` : ''
        }.`
  const mal = (tema: EstadoServidor['alertas'][number]['tema']) => e.alertas.some((a) => a.tema === tema)
  const hayClases = p.en_vivo.length + p.procesando.length + p.con_reintento.length + p.con_error.length > 0
  const minutosHasta = (iso: string) => Math.max(1, Math.round((new Date(iso).getTime() - new Date(e.generado_en).getTime()) / 60_000))

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {estado.sinConexion && <ErrorForm mensaje={`Se perdió la conexión con el servidor. Lo que ves es de las ${hora(e.generado_en)}`} />}

      <section aria-labelledby="titulo-alertas" className={cn('rounded-2xl p-4 ring-1', e.alertas.length === 0 ? VERDE : urgentes ? ROJO : AMBAR)}>
        <h2 id="titulo-alertas" className="flex items-center gap-2 font-semibold">
          {e.alertas.length === 0 ? <CheckCircle2 className="size-5 shrink-0" aria-hidden /> : urgentes ? <AlertCircle className="size-5 shrink-0" aria-hidden /> : <AlertTriangle className="size-5 shrink-0" aria-hidden />}
          {resumen}
        </h2>
        {e.alertas.length > 0 && (
          <ul className="mt-2 space-y-2 text-sm leading-relaxed">
            {e.alertas.map((a) => (
              <li key={a.texto}>
                <span className="font-semibold">{a.nivel === 'critico' ? 'Urgente: ' : 'Aviso: '}</span>
                {a.texto}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs opacity-80">Última lectura a las {hora(e.generado_en)} · se actualiza sola cada 10 segundos.</p>
        <p role="status" className="sr-only">{resumen}</p>
      </section>

      <Tarjeta id="titulo-clases" titulo="Clases en proceso">
        {!hayClases && <p className="text-sm text-muted-foreground">No hay ninguna clase grabándose ni procesándose ahora.</p>}
        <Grupo titulo="Grabándose">
          {p.en_vivo.map((c) => (
            <Clase key={c.clase_id} c={c}>{ESTADO_EN_VIVO[c.estado] ?? c.estado}.</Clase>
          ))}
        </Grupo>
        <Grupo titulo="Procesándose">
          {p.procesando.map((c) => (
            <Clase key={c.clase_id} c={c}>{c.turno === 'ahora'
                ? `procesándose ahora${c.minutos !== null ? ` (hace ${c.minutos} min)` : ''}.`
                : `en espera de su turno${c.posicion !== null ? ` (la n.º ${c.posicion} de la cola)` : ''}${c.prioritaria ? ', marcada como prioritaria' : ''}.`}</Clase>
          ))}
        </Grupo>
        <Grupo titulo="Fallaron y se reintentan solas">
          {p.con_reintento.map((c) => (
            <Clase key={c.clase_id} c={c} detalle={c.error}>reintento en unos {minutosHasta(c.reintento_en)} min (intento {c.intentos}).</Clase>
          ))}
        </Grupo>
        <Grupo titulo="Con error y sin reintento">
          {p.con_error.map((c) => (
            <Clase key={c.clase_id} c={c} detalle={c.error}>el profesor puede reintentarla desde «Grabar».</Clase>
          ))}
        </Grupo>
        <p className="text-sm text-muted-foreground">Terminadas en las últimas 24 horas: {p.terminadas_24h}.</p>
      </Tarjeta>

      <Tarjeta id="titulo-equipo" titulo="Equipo del colegio">
        <ul className="space-y-3">
          <Requisito ok={!mal('ollama')} titulo="Programa de IA (Ollama)">
            {!o.responde ? 'No responde por ahora.' : !o.modelo_texto_instalado ? `Funciona, pero falta el modelo de resúmenes (${o.modelo_texto}).` : 'Funcionando, con el modelo de resúmenes instalado.'}
          </Requisito>
          <Requisito ok={!mal('disco')} titulo="Espacio en disco">
            {num(d.libre_gb)} GB libres de {num(d.total_gb)} GB. Audio temporal: {tamaño(d.audio_temporal_mb)}. Fotos temporales: {tamaño(d.fotos_temporales_mb)}.
            {d.base_de_datos_mb !== null && ` Base de datos: ${tamaño(d.base_de_datos_mb)}.`}
          </Requisito>
          <Requisito ok={!mal('respaldos')} titulo="Respaldos de la base de datos">
            {r.cantidad === 0
              ? 'Todavía no hay ninguno.'
              : `Último: ${r.hace_dias !== null ? hace(r.hace_dias) : 'fecha desconocida'}. ${r.cantidad} ${r.cantidad === 1 ? 'copia' : 'copias'} (${tamaño(r.mb)}).`}
            {r.en_el_mismo_disco && ' Están en el mismo disco que la base de datos.'} Carpeta: {r.carpeta}
          </Requisito>
          <Requisito ok={!mal('memoria')} titulo="Memoria">
            {m.total_gb === null || m.libre_gb === null ? 'No se pudo medir.' : `${num(m.libre_gb)} GB libres de ${num(m.total_gb)} GB.`}
          </Requisito>
          {v.activa !== null && (
            <Requisito ok={!mal('vigilancia')} titulo="Vigilancia automática">
              {v.activa
                ? `Funcionando${v.ultima_pasada ? ` (última revisión hace ${Math.max(0, Math.round((new Date(e.generado_en).getTime() - new Date(v.ultima_pasada).getTime()) / 1000))} s)` : ''}.`
                : 'No responde.'}
            </Requisito>
          )}
        </ul>
      </Tarjeta>
    </div>
  )
}

function Tarjeta({ id, titulo, children }: { id: string; titulo: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-3 rounded-2xl border bg-card p-4 desk:p-5">
      <h2 id={id} className="text-lg font-semibold">{titulo}</h2>
      {children}
    </section>
  )
}

/** Un grupo de clases; sin clases no se dibuja. */
function Grupo({ titulo, children }: { titulo: string; children: ReactNode[] }) {
  if (children.length === 0) return null
  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold">{titulo}</h3>
      <ul className="space-y-1.5 text-sm">{children}</ul>
    </div>
  )
}

function Clase({ c, children, detalle }: { c: { curso: string; asignatura: string | null; fecha: string }; children: ReactNode; detalle?: string | null }) {
  return (
    <li className="leading-relaxed">
      <span className="font-medium">{c.curso} · {c.asignatura ?? 'Clase'}</span> <span className="text-muted-foreground">({fechaCorta(c.fecha)})</span>: {children}
      {detalle && <span className="block text-xs text-muted-foreground [overflow-wrap:anywhere]">{detalle}</span>}
    </li>
  )
}
