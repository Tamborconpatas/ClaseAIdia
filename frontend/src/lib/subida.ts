/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { ApiError } from '@/lib/api'

/**
 * Qué decirle a quien graba cuando un trozo de audio no se pudo subir y se va a reintentar. El audio no se pierde: este
 * equipo lo conserva y lo sube cuando el servidor vuelva o tenga espacio.
 */
export function mensajeDeSubidaFallida(e: unknown): string {
  if (e instanceof ApiError && e.status === 507) return `${e.message} El audio se sigue guardando en este equipo y se subirá cuando haya espacio.`
  return 'Sin conexión con el servidor: el audio se sigue guardando aquí y se subirá cuando vuelva.'
}
