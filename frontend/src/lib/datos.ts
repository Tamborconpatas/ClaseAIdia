/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { api, type Bloque } from './api'

// ponytail: una petición por curso; si un profesor llega a tener decenas, pedir un endpoint propio.
export async function cargarBloques(cursoIds: number[]): Promise<Bloque[]> {
  return (await Promise.all(cursoIds.map((id) => api<Bloque[]>(`/cursos/${id}/bloques`)))).flat()
}
