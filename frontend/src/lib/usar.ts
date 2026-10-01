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
