import fs from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Certificado propio para abrir la app por https (hace falta para grabar con el celular por la red local):
// `python -m scripts.generar_certificado` lo crea en ../certs y `npm run dev:https` lo usa.
function https(mode: string) {
  if (mode !== 'https') return undefined
  const carpeta = path.resolve(import.meta.dirname, '../certs')
  try {
    return { key: fs.readFileSync(path.join(carpeta, 'key.pem')), cert: fs.readFileSync(path.join(carpeta, 'cert.pem')) }
  } catch {
    throw new Error('Falta el certificado: desde la raíz del proyecto, corre «python -m scripts.generar_certificado».')
  }
}

// El frontend llama a /api/...; en desarrollo Vite lo reenvía al backend FastAPI.
// Misma origen = sin CORS, y funciona también abriendo el sitio desde un teléfono en la red local.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    https: https(mode),
    proxy: {
      '/api': { target: process.env.API_URL ?? 'http://127.0.0.1:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
}))
