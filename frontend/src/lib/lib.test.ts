import { describe, expect, it } from 'vitest'
import { aMinutos, colorAsignatura, hhmm, ordenar } from './horario'
import { formatearRut, rutParaApi, rutValido } from './rut'
import { errorPassword, errorPin, errorRut, soloDigitos } from './validar'
import type { Bloque } from './api'

// Estas reglas deben coincidir con las del backend (interfaz/api/esquemas.py), que es quien manda.

describe('rut', () => {
  it('valida el dígito verificador', () => {
    expect(rutValido('12.345.678-5')).toBe(true)
    expect(rutValido('11111111-1')).toBe(true)
    expect(rutValido('12.345.678-4')).toBe(false)
    expect(rutValido('abc')).toBe(false)
    expect(rutValido('')).toBe(false)
  })
  it('acepta K y 0 como dígito verificador', () => {
    expect(rutValido('6-k')).toBe(false) // cuerpo demasiado corto (< 7 dígitos)
    expect(rutValido('10.000.013-k')).toBe(true)
    expect(rutValido('10000013-K')).toBe(true)
  })
  it('formatea mientras se escribe y manda al API sin puntos', () => {
    expect(formatearRut('123456785')).toBe('12.345.678-5')
    expect(formatearRut('1')).toBe('1')
    expect(formatearRut('12345678-5999')).toBe('12.345.678-5') // tope de 9 caracteres
    expect(rutParaApi('12.345.678-5')).toBe('12345678-5')
    expect(rutParaApi('10.000.013-k')).toBe('10000013-K')
  })
  it('errorRut da mensaje solo si es inválido', () => {
    expect(errorRut('12.345.678-5')).toBeNull()
    expect(errorRut('12.345.678-1')).toMatch(/RUT inválido/)
  })
})

describe('PIN (igual que pin_es_facil del backend)', () => {
  it('acepta 6 dígitos no triviales', () => {
    expect(errorPin('135792')).toBeNull()
    expect(errorPin('482915')).toBeNull()
  })
  it('rechaza largo o caracteres incorrectos', () => {
    for (const p of ['12345', '1234567', 'abcdef', '12 456', '']) expect(errorPin(p)).not.toBeNull()
  })
  it('rechaza repetidos y secuencias, ascendentes o descendentes', () => {
    for (const p of ['111111', '000000', '123456', '234567', '654321', '987654']) expect(errorPin(p)).toMatch(/fácil/)
  })
  it('soloDigitos limpia y corta a 6', () => {
    expect(soloDigitos('12a3-45678')).toBe('123456')
  })
})

describe('contraseña (igual que _password_valida y _password_sin_rut del backend)', () => {
  const rut = '12.345.678-5'
  it('acepta una contraseña razonable', () => {
    expect(errorPassword('buena-clave-larga', rut)).toBeNull()
  })
  it('exige entre 10 y 128 caracteres', () => {
    expect(errorPassword('corta-123', rut)).toMatch(/al menos 10/)
    expect(errorPassword('a1b2c3d4e5'.repeat(13), rut)).toMatch(/128/)
    expect(errorPassword('a1b2c3d4e5'.repeat(12) + 'xxxxxxxx', rut)).toBeNull() // 128 exactos
  })
  it('rechaza contraseñas repetitivas (menos de 4 caracteres distintos)', () => {
    expect(errorPassword('abababababab', rut)).toMatch(/repetitiva/)
    expect(errorPassword('abcabcabcabc', rut)).toMatch(/repetitiva/)
    expect(errorPassword('abcdabcdabcd', rut)).toBeNull()
  })
  it('rechaza contraseñas que contienen el RUT (con o sin puntos)', () => {
    expect(errorPassword('mi-rut-12345678-ok', rut)).toMatch(/RUT/)
    expect(errorPassword('mi-rut-12.345.678-ok', rut)).toMatch(/RUT/)
  })
})

describe('horario', () => {
  const b = (dia: number, ini: string): Bloque => ({ dia_semana: dia, hora_inicio: ini }) as Bloque
  it('aMinutos y hhmm aceptan HH:MM y HH:MM:SS', () => {
    expect(aMinutos('08:30')).toBe(510)
    expect(aMinutos('18:15:00')).toBe(1095)
    expect(hhmm('08:30:00')).toBe('08:30')
  })
  it('ordena por hora y luego por día, sin tocar el original', () => {
    const original = [b(2, '09:00'), b(0, '09:00'), b(4, '08:00')]
    expect(ordenar(original).map((x) => [x.dia_semana, x.hora_inicio])).toEqual([
      [4, '08:00'],
      [0, '09:00'],
      [2, '09:00'],
    ])
    expect(original[0].dia_semana).toBe(2)
  })
  it('el color de una asignatura es estable y siempre existe', () => {
    expect(colorAsignatura('Matemática')).toBe(colorAsignatura('Matemática'))
    expect(colorAsignatura(null)).toMatch(/^bg-/)
  })
})
