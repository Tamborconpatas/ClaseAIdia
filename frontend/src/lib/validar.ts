// Validación en el cliente: solo comodidad (mensajes claros antes de enviar).
// La que cuenta es la del backend, que aplica exactamente las mismas reglas.
import { rutValido } from './rut'

export const errorRut = (v: string) => (rutValido(v) ? null : 'RUT inválido: revisa el número y el dígito verificador.')

export function errorPin(pin: string): string | null {
  if (!/^\d{6}$/.test(pin)) return 'El PIN son exactamente 6 números.'
  if (new Set(pin).size === 1 || '0123456789'.includes(pin) || '9876543210'.includes(pin))
    return 'Ese PIN es muy fácil de adivinar (repetido o en secuencia). Elige otro.'
  return null
}

export function errorPassword(pw: string, rut: string): string | null {
  if (pw.length < 10) return 'La contraseña debe tener al menos 10 caracteres.'
  if (pw.length > 128) return 'La contraseña no puede superar los 128 caracteres.'
  if (new Set(pw).size < 4) return 'La contraseña es demasiado repetitiva.'
  const cuerpo = rut.replace(/[^0-9kK]/g, '').slice(0, -1)
  if (cuerpo && pw.replace(/\./g, '').includes(cuerpo)) return 'La contraseña no puede contener tu RUT.'
  return null
}

export const soloDigitos = (v: string) => v.replace(/\D/g, '').slice(0, 6)
