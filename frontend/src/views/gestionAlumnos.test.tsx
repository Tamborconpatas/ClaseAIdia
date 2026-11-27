/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FilaAlumno } from '@/components/GestionAlumnos'
import { SesionProvider } from '@/lib/sesion'
import { Entrada } from '@/views/Entrada'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const raices: Root[] = []
afterEach(() => {
  for (const r of raices.splice(0)) act(() => r.unmount())
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  window.history.replaceState(null, '', '/')
})

async function montar(elemento: ReactElement) {
  const contenedor = document.createElement('div')
  document.body.append(contenedor)
  const raiz = createRoot(contenedor)
  raices.push(raiz)
  await act(async () => raiz.render(elemento))
  await act(async () => void (await new Promise((r) => setTimeout(r, 50))))
  return contenedor
}

const boton = (texto: string) => [...document.querySelectorAll('button')].find((b) => b.textContent?.includes(texto) || b.getAttribute('aria-label')?.includes(texto))

async function escribir(etiqueta: string, valor: string) {
  const label = [...document.querySelectorAll('label')].find((l) => l.textContent?.startsWith(etiqueta))
  const campo = label?.control as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(campo, valor)
    campo.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

const json = (cuerpo: unknown, status = 200) => new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } })

describe('unirse con un nombre que suena a broma', () => {
  let llamadas: { ruta: string; cuerpo: Record<string, unknown> | null }[]
  beforeEach(() => {
    llamadas = []
    let unirse = 0
    vi.stubGlobal('fetch', async (ruta: string, init?: RequestInit) => {
      llamadas.push({ ruta, cuerpo: init?.body ? JSON.parse(String(init.body)) : null })
      if (ruta.endsWith('/auth/estado')) return json({ configurado: true })
      if (ruta.endsWith('/cursos/unirse')) return ++unirse === 1 ? json({ detail: 'El nombre necesita confirmación' }, 428) : json({ access_token: 'x', roles: ['ALUMNO'], colegio_id: 1 })
      return json({ id: 1, rut: '21000003-8', nombre: 'Armando Casas', colegio_id: 1, roles: ['ALUMNO'] })
    })
    window.history.replaceState(null, '', '/?unirse=ABC123')
  })

  it('pide confirmar con el RUT a la vista y recién entonces envía la confirmación', async () => {
    await montar(<SesionProvider><Entrada /></SesionProvider>)
    await escribir('Tu nombre', 'Armando Casas')
    await escribir('RUT', '210000038')
    await escribir('Elige un PIN', '482915')
    await escribir('Repite el PIN', '482915')
    await act(async () => boton('Unirme y entrar')!.click())
    await act(async () => void (await new Promise((r) => setTimeout(r, 20))))

    const alerta = document.querySelector('[role="alert"]')
    expect(alerta?.textContent).toContain('«Armando Casas»')
    expect(alerta?.textContent).toContain('quedará asociado permanentemente a tu RUT 21.000.003-8')
    expect(llamadas.filter((l) => l.ruta.endsWith('/cursos/unirse'))).toHaveLength(1)
    expect(llamadas.find((l) => l.ruta.endsWith('/cursos/unirse'))!.cuerpo).toMatchObject({ confirmar_nombre: false, rut: '21000003-8' })

    await act(async () => boton('Sí, es mi nombre real')!.click())
    await act(async () => void (await new Promise((r) => setTimeout(r, 20))))
    const envios = llamadas.filter((l) => l.ruta.endsWith('/cursos/unirse'))
    expect(envios).toHaveLength(2)
    expect(envios[1].cuerpo).toMatchObject({ confirmar_nombre: true })
    expect(document.querySelector('[role="alert"]')).toBeNull()
  })

  it('«Corregir mi nombre» cierra el aviso sin enviar nada más y cambiar el nombre vuelve a pedir confirmación', async () => {
    await montar(<SesionProvider><Entrada /></SesionProvider>)
    await escribir('Tu nombre', 'Armando Casas')
    await escribir('RUT', '210000038')
    await escribir('Elige un PIN', '482915')
    await escribir('Repite el PIN', '482915')
    await act(async () => boton('Unirme y entrar')!.click())
    await act(async () => void (await new Promise((r) => setTimeout(r, 20))))
    await act(async () => boton('Corregir mi nombre')!.click())
    expect(document.querySelector('[role="alert"]')).toBeNull()
    expect(llamadas.filter((l) => l.ruta.endsWith('/cursos/unirse'))).toHaveLength(1)
  })
})

describe('fila de alumno con la marca «Revisar nombre»', () => {
  const alumno = { id: 7, nombre: 'Alan Brito', rut: '21.000.003-8', revisar_nombre: true }

  it('al profesor le muestra la marca y solo corregir/dar por bueno; al UTP además mover, sacar y eliminar', async () => {
    const profe = await montar(<ul><FilaAlumno alumno={alumno} cursoId={1} otrosCursos={[]} completo={false} onCambio={() => {}} /></ul>)
    expect(profe.textContent).toContain('Revisar nombre')
    expect(boton('está bien')).toBeTruthy()
    expect(boton('Corregir el nombre')).toBeTruthy()
    expect(boton('Mover de curso')).toBeUndefined()
    expect(boton('Eliminar al alumno')).toBeUndefined()
    document.body.innerHTML = ''

    await montar(<ul><FilaAlumno alumno={{ ...alumno, revisar_nombre: false }} cursoId={1} otrosCursos={[]} completo onCambio={() => {}} /></ul>)
    expect(document.body.textContent).not.toContain('Revisar nombre')
    expect(boton('está bien')).toBeUndefined()
    for (const accion of ['Corregir el nombre', 'Mover de curso', 'Sacar del curso', 'Eliminar al alumno']) expect(boton(accion)).toBeTruthy()
  })
})
