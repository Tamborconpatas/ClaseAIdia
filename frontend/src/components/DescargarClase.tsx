import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { FileDown, FileText, Loader2, Printer } from 'lucide-react'
import { ErrorForm } from '@/components/comunes'
import { VistaImpresion } from '@/components/VistaImpresion'
import { Button } from '@/components/ui/button'
import type { ClaseDetalle } from '@/lib/api'
import { esperarDibujos } from '@/lib/dibujos'
import { descargar } from '@/lib/exportar/descargar'
import { construirModelo, nombreDeArchivo, type Bloque } from '@/lib/exportar/modelo'

/**
 * Descargar la clase en PDF o Word. Todo lo hace el teléfono o el PC de quien descarga; el servidor no interviene:
 * - PDF: se abre la impresión del navegador con una hoja pensada para papel («Guardar como PDF»); las fórmulas y los
 *   diagramas salen dibujados.
 * - Word: un .docx con las fórmulas como ecuaciones de Word (editables) y los diagramas como imagen.
 */
export function DescargarClase({ clase }: { clase: ClaseDetalle }) {
  const [trabajando, setTrabajando] = useState<'pdf' | 'word' | null>(null)
  const [hoja, setHoja] = useState<Bloque[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Con la hoja montada se espera a que se dibuje todo y recién entonces se abre la impresión.
  useEffect(() => {
    if (!hoja) return
    let activo = true
    const terminar = () => {
      setHoja(null)
      setTrabajando(null)
    }
    void (async () => {
      await esperarDibujos()
      if (!activo) return
      window.addEventListener('afterprint', terminar, { once: true })
      window.print()
      setTimeout(terminar, 120_000) // en algunos teléfonos `afterprint` no llega
    })()
    return () => {
      activo = false
      window.removeEventListener('afterprint', terminar)
    }
  }, [hoja])

  const pdf = () => {
    setError(null)
    setTrabajando('pdf')
    setHoja(construirModelo(clase))
  }

  const word = async () => {
    setError(null)
    setTrabajando('word')
    try {
      const { generarDocx } = await import('@/lib/exportar/docx') // la librería de Word se baja solo al pedir el archivo
      descargar(await generarDocx(construirModelo(clase)), nombreDeArchivo(clase, 'docx'))
    } catch {
      setError('No se pudo preparar el archivo de Word. Prueba de nuevo, o usa el PDF.')
    } finally {
      setTrabajando(null)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" className="h-11 flex-1 desk:h-9 desk:flex-none" disabled={trabajando !== null} onClick={pdf}>
          {trabajando === 'pdf' ? <Loader2 className="animate-spin" /> : <Printer />} Guardar como PDF
        </Button>
        <Button variant="outline" className="h-11 flex-1 desk:h-9 desk:flex-none" disabled={trabajando !== null} onClick={() => void word()}>
          {trabajando === 'word' ? <Loader2 className="animate-spin" /> : <FileDown />} Descargar Word
        </Button>
      </div>
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <FileText className="mt-0.5 size-3.5 shrink-0" /> Incluye el resumen, los puntos clave, la hoja de repaso, el mapa, las tarjetas y lo leído de la pizarra, con las fórmulas y los diagramas.
      </p>
      <ErrorForm mensaje={error} />
      {hoja && createPortal(<div id="impresion"><VistaImpresion bloques={hoja} /></div>, document.body)}
    </div>
  )
}
