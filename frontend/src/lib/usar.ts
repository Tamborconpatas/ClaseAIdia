/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useCallback, useEffect, useState } from 'react'

/** Carga datos al montar (y cuando cambian las dependencias). Ignora respuestas de cargas viejas. */
export function useCarga<T>(cargar: () => Promise<T>, deps: unknown[]) {
  const [estado, setEstado] = useState<{ datos?: T; error?: string; cargando: boolean }>({ cargando: true })
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let vigente = true
    setEstado((e) => ({ ...e, cargando: true, error: undefined }))
    cargar().then(
      (datos) => vigente && setEstado({ datos, cargando: false }),
      (err: Error) => vigente && setEstado({ error: err.message, cargando: false }),
    )
    return () => {
      vigente = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])

  const recargar = useCallback(() => setVersion((v) => v + 1), [])
  return { ...estado, recargar }
}

/**
 * Consulta cada `cadaMs` mientras la pantalla está abierta (el estado de una grabación en curso).
 * Si una consulta falla conserva los últimos datos y marca `sinConexion`, en vez de vaciar la pantalla.
 */
export function useSondeo<T>(consultar: () => Promise<T>, cadaMs: number, deps: unknown[]) {
  const [datos, setDatos] = useState<T | undefined>()
  const [sinConexion, setSinConexion] = useState(false)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let vigente = true
    let temporizador: ReturnType<typeof setTimeout>
    const ciclo = async () => {
      try {
        const d = await consultar()
        if (vigente) {
          setDatos(d)
          setSinConexion(false)
        }
      } catch {
        if (vigente) setSinConexion(true)
      }
      if (vigente) temporizador = setTimeout(ciclo, cadaMs)
    }
    void ciclo()
    return () => {
      vigente = false
      clearTimeout(temporizador)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])

  const actualizar = useCallback(() => setVersion((v) => v + 1), [])
  /** Pone ya un dato que se acaba de recibir por otro lado (la respuesta de un cambio), sin esperar a la próxima consulta. */
  const fijar = useCallback((nuevo: T) => setDatos(nuevo), [])
  return { datos, sinConexion, actualizar, fijar }
}
