import { useState } from 'react'
import { Loader2, Pencil, Trash2 } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { TextoConFormulas } from '@/components/TextoConFormulas'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { api, type PizarraLeida } from '@/lib/api'

const AREA =
  'min-h-32 w-full rounded-lg border border-input bg-transparent px-3 py-2 font-mono text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50'

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
      <p className="text-xs font-medium text-muted-foreground">Foto a los {Math.floor(foto.segundo / 60)} min de la clase</p>
      {editando ? (
        <div className="space-y-2">
          <Label htmlFor={`pizarra-${foto.id}`}>Texto de la foto (las fórmulas van entre $...$ o $$...$$)</Label>
          <textarea id={`pizarra-${foto.id}`} rows={6} maxLength={8000} value={borrador} onChange={(e) => setBorrador(e.target.value)} className={AREA} />
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
              <Button variant="outline" className="h-10 desk:h-8" onClick={() => { setBorrador(foto.texto); setEditando(true) }}>
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
