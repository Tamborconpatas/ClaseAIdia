import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { iniciarTema } from './lib/tema'

iniciarTema() // antes de dibujar: así no se ve un destello claro si se eligió oscuro

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
