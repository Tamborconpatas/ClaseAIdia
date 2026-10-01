import { api, type Bloque } from './api'

// ponytail: una petición por curso; si un profesor llega a tener decenas, pedir un endpoint propio.
export async function cargarBloques(cursoIds: number[]): Promise<Bloque[]> {
  return (await Promise.all(cursoIds.map((id) => api<Bloque[]>(`/cursos/${id}/bloques`)))).flat()
}
