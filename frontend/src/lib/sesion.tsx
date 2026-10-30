/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
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
