/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, Pencil, Trash2 } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { EditorPizarra } from '@/components/EditorPizarra'
import { TextoConFormulas } from '@/components/TextoConFormulas'
import { Button } from '@/components/ui/button'
import { api, type PizarraLeida } from '@/lib/api'

/**
 * Lo que la IA leyó de una foto de la pizarra. El alumno solo lo ve dibujado; el profesor puede corregir el texto
 * (con vista previa de las fórmulas mientras escribe) o quitarlo si salió mal.
 */
export function FotoLeida({ claseId, foto, editable, onCambio }: { claseId: number; foto: PizarraLeida; editable: boolean; onCambio: () => void }) {
  const [editando, setEditando] = useState(false)
  const [borrador, setBorrador] = useState(foto.texto)
  const [confirmando, setConfirmando] = useState(false)
  const [trabajando, setTrabajando] = useState<'guardar' | 'quitar' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const titulo = useRef<HTMLParagraphElement>(null)
  const botonCorregir = useRef<HTMLButtonElement>(null)
  const yaMontado = useRef(false)

  // El foco acompaña al cambio: al abrir el editor va a su título, al cerrarlo vuelve al botón «Corregir».
  useEffect(() => {
    if (!yaMontado.current) {
      yaMontado.current = true
      return
    }
    if (editando) titulo.current?.focus()
    else botonCorregir.current?.focus()
  }, [editando])

  const ejecutar = async (que: 'guardar' | 'quitar') => {
    setError(null)
    setTrabajando(que)
    try {
      if (que === 'guardar') await api(`/clases/${claseId}/pizarra/${foto.id}`, { metodo: 'PUT', cuerpo: { texto: borrador } })
      else await api(`/clases/${claseId}/pizarra/${foto.id}`, { metodo: 'DELETE' })
      setEditando(false)
      setConfirmando(false)
      onCambio()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTrabajando(null)
    }
  }

  return (
    <li className="space-y-2">
      <p ref={titulo} tabIndex={-1} className="text-xs font-medium text-muted-foreground outline-none">
        {editando ? 'Corrigiendo la foto' : 'Foto'} a los {Math.floor(foto.segundo / 60)} min de la clase
      </p>
      {editando ? (
        <div className="space-y-2">
          <EditorPizarra texto={foto.texto} onCambio={setBorrador} />
          <p className="text-xs font-medium text-muted-foreground">Así lo verán los alumnos:</p>
          <div className="rounded-lg bg-muted/50 p-3">
            <TextoConFormulas texto={borrador} />
          </div>
          <ErrorForm mensaje={error} />
          <div className="flex gap-2">
            <Button className="h-11 desk:h-9" disabled={trabajando !== null || !borrador.trim()} onClick={() => void ejecutar('guardar')}>
              {trabajando === 'guardar' && <Loader2 className="animate-spin" />} Guardar
            </Button>
            <Button variant="outline" className="h-11 desk:h-9" disabled={trabajando !== null} onClick={() => { setEditando(false); setBorrador(foto.texto) }}>
              Cancelar
            </Button>
          </div>
        </div>
      ) : (
        <>
          <TextoConFormulas texto={foto.texto} />
          {editable && (
            <div className="flex flex-wrap gap-2">
              <Button ref={botonCorregir} variant="outline" className="h-10 desk:h-8" onClick={() => { setBorrador(foto.texto); setEditando(true) }}>
                <Pencil /> Corregir
              </Button>
              {confirmando ? (
                <>
                  <Button variant="destructive" className="h-10 desk:h-8" disabled={trabajando !== null} onClick={() => void ejecutar('quitar')}>
                    {trabajando === 'quitar' && <Loader2 className="animate-spin" />} Sí, quitar esta foto
                  </Button>
                  <Button variant="ghost" className="h-10 desk:h-8" onClick={() => setConfirmando(false)}>No</Button>
                </>
              ) : (
                <Button variant="ghost" className="h-10 desk:h-8" onClick={() => setConfirmando(true)}>
                  <Trash2 /> Quitar
                </Button>
              )}
            </div>
          )}
          <ErrorForm mensaje={error} />
        </>
      )}
    </li>
  )
}
