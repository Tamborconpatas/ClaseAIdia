/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { mensajeDeSubidaFallida } from '@/lib/subida'

describe('qué se dice cuando un trozo de audio no se pudo subir', () => {
  it('con el disco del servidor lleno, dice el motivo real y que el audio no se pierde', () => {
    const e = new ApiError(507, 'El disco del servidor está lleno: no se puede guardar más audio. Avisa al UTP para que libere espacio.')
    expect(mensajeDeSubidaFallida(e)).toBe(`${e.message} El audio se sigue guardando en este equipo y se subirá cuando haya espacio.`)
  })

  it('con cualquier otra falla (sin red, servidor caído, otro 5xx) habla de la conexión', () => {
    const conexion = 'Sin conexión con el servidor: el audio se sigue guardando aquí y se subirá cuando vuelva.'
    expect(mensajeDeSubidaFallida(new ApiError(0, 'sin red'))).toBe(conexion)
    expect(mensajeDeSubidaFallida(new ApiError(503, 'caído'))).toBe(conexion)
    expect(mensajeDeSubidaFallida(new ApiError(500, 'error'))).toBe(conexion)
    expect(mensajeDeSubidaFallida(new TypeError('Failed to fetch'))).toBe(conexion)
    expect(mensajeDeSubidaFallida(undefined)).toBe(conexion) // un error que no es un Error (algo lanzado sin más)
    expect(mensajeDeSubidaFallida(null)).toBe(conexion)
  })
})
