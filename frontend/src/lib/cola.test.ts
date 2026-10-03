import { describe, expect, it } from 'vitest'
import { mensajeDeProcesamiento } from '@/lib/cola'

describe('lo que se le dice al profesor mientras su clase se procesa', () => {
  it('si ya la están procesando, dice que se transcribe y se genera el material', () => {
    expect(mensajeDeProcesamiento(null)).toBe('Procesando la clase: se transcribe y se genera el material. Puede tardar unos minutos y puedes cerrar esta pantalla.')
  })

  it('si es la próxima, lo dice', () => {
    expect(mensajeDeProcesamiento(1)).toBe('Tu clase es la próxima en procesarse. Puedes cerrar esta pantalla.')
  })

  it('si hay otras antes, cuenta cuántas, en singular y plural', () => {
    expect(mensajeDeProcesamiento(2)).toBe('Tu clase está en la cola: hay 1 clase antes que la tuya. Puedes cerrar esta pantalla.')
    expect(mensajeDeProcesamiento(4)).toBe('Tu clase está en la cola: hay 3 clases antes que la tuya. Puedes cerrar esta pantalla.')
  })
})
