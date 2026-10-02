import { describe, expect, it } from 'vitest'
import { dibujosPendientes, empezarDibujo, esperarDibujos } from './dibujos'

describe('dibujos', () => {
  it('cuenta los dibujos en curso y marcar uno como terminado dos veces no descuenta de más', () => {
    const base = dibujosPendientes()
    const a = empezarDibujo()
    const b = empezarDibujo()
    expect(dibujosPendientes()).toBe(base + 2)
    a()
    a()
    expect(dibujosPendientes()).toBe(base + 1)
    b()
    expect(dibujosPendientes()).toBe(base)
  })

  it('espera a que termine lo que se está dibujando', async () => {
    const terminar = empezarDibujo()
    let listo = false
    const espera = esperarDibujos().then(() => (listo = true))
    await new Promise((r) => setTimeout(r, 200))
    expect(listo).toBe(false) // sigue habiendo un dibujo pendiente
    terminar()
    await espera
    expect(listo).toBe(true)
    expect(dibujosPendientes()).toBe(0)
  })

  it('no se cuelga si un dibujo nunca termina: se rinde al llegar al tope', async () => {
    const terminar = empezarDibujo()
    const t0 = Date.now()
    await esperarDibujos(300)
    expect(Date.now() - t0).toBeLessThan(2000)
    terminar()
  })
})
