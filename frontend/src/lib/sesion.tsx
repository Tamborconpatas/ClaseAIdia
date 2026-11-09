/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { rutParaApi } from './rut'
import { api, guardarSesion, leerSesion, type Rol, type Sesion, type Usuario } from './api'

interface Ctx {
  sesion: Sesion | null
  usuario: Usuario | null
  /** Rol con el que se muestra la app si el usuario tiene varios. */
  rol: Rol | null
  entrar: (s: Sesion) => void
  salir: () => void
}
const SesionCtx = createContext<Ctx | null>(null)

const PRIORIDAD: Rol[] = ['UTP', 'PROFESOR', 'ALUMNO']

/** Solo la demostración (`iniciar demo`): cuentas de ejemplo para entrar con `?demo=utp|profesor|alumno`. Fuera de la demo no existen. */
type CuentaDemo = { rut: string; secreto: string }
function cuentaDemo(rol: string | null): CuentaDemo | null {
  const crudo = import.meta.env.VITE_DEMO_CUENTAS as string | undefined
  if (!crudo || !rol) return null
  try {
    return (JSON.parse(crudo) as Record<string, CuentaDemo>)[rol] ?? null
  } catch {
    return null
  }
}

export function SesionProvider({ children }: { children: ReactNode }) {
  const [sesion, setSesion] = useState<Sesion | null>(leerSesion)
  const [usuario, setUsuario] = useState<Usuario | null>(null)

  const salir = useCallback(() => {
    guardarSesion(null)
    setSesion(null)
    setUsuario(null)
  }, [])
  const entrar = useCallback((s: Sesion) => {
    guardarSesion(s)
    setSesion(s)
    // Quita ?unirse=CODIGO (del QR) de la dirección: si no, al cerrar sesión volvería a abrirse el registro.
    window.history.replaceState(null, '', window.location.pathname)
  }, [])

  // Demo: la dirección `?demo=<rol>` entra sola con esa cuenta de ejemplo (si esta pestaña aún no tiene sesión).
  useEffect(() => {
    const rol = new URLSearchParams(window.location.search).get('demo')
    const c = cuentaDemo(rol)
    if (!c || leerSesion()) return
    const alumno = rol === 'alumno'
    api<Sesion>(alumno ? '/auth/login/alumno' : '/auth/login/staff', {
      metodo: 'POST',
      cuerpo: alumno ? { rut: rutParaApi(c.rut), pin: c.secreto } : { rut: rutParaApi(c.rut), password: c.secreto },
    }).then(entrar, () => {})
  }, [entrar])

  // Con sesión, traer quién es (nombre, id); si el token ya no sirve, volver al login.
  useEffect(() => {
    if (!sesion) return
    let vigente = true
    api<Usuario>('/auth/me', { sesion }).then(
      (u) => vigente && setUsuario(u),
      () => vigente && salir(),
    )
    return () => {
      vigente = false
    }
  }, [sesion, salir])

  useEffect(() => {
    window.addEventListener('claseaidia:sesion-vencida', salir)
    return () => window.removeEventListener('claseaidia:sesion-vencida', salir)
  }, [salir])

  const valor = useMemo<Ctx>(
    () => ({
      sesion,
      usuario,
      rol: sesion ? (PRIORIDAD.find((r) => sesion.roles.includes(r)) ?? null) : null,
      entrar,
      salir,
    }),
    [sesion, usuario, entrar, salir],
  )
  return <SesionCtx.Provider value={valor}>{children}</SesionCtx.Provider>
}

export function useSesion() {
  const c = useContext(SesionCtx)
  if (!c) throw new Error('useSesion fuera de SesionProvider')
  return c
}
