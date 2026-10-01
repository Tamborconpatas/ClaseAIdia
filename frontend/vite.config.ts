import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// El frontend llama a /api/...; en desarrollo Vite lo reenvía al backend FastAPI.
// Misma origen = sin CORS, y funciona también abriendo el sitio desde un teléfono en la red local.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    proxy: {
      '/api': { target: process.env.API_URL ?? 'http://127.0.0.1:8000', rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
