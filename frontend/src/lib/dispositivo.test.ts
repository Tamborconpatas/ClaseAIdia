/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { codigoDeDispositivo } from '@/lib/dispositivo'

describe('código de dispositivo', () => {
  beforeEach(() => localStorage.clear())

  it('es aleatorio, de 16 caracteres hexadecimales, y se mantiene entre llamadas', () => {
    const a = codigoDeDispositivo()
    expect(a).toMatch(/^[0-9a-f]{16}$/)
    expect(codigoDeDispositivo()).toBe(a)
    expect(localStorage.getItem('claseaidia:dispositivo')).toBe(a)
  })

  it('un valor guardado que no tiene el formato esperado se reemplaza por uno nuevo', () => {
    localStorage.setItem('claseaidia:dispositivo', "x'; DROP TABLE")
    expect(codigoDeDispositivo()).toMatch(/^[0-9a-f]{16}$/)
  })
})
