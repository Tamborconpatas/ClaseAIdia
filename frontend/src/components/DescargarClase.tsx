/*
 * Copyright 2026 Tamborconpatas (Creador Original)
 * Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
 * Licencia Apache v2.0 + Commons Clause v1.0. Uso comercial restringido para terceros.
 */
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
 * - Word: un .docx con las fórmulas y los diagramas como imagen, que se ve en cualquier programa (Word, Google Docs, el
 *   celular). El profesor, que puede querer editarlas, tiene además una versión con ecuaciones de Word editables.
 */
export function DescargarClase({ clase, esProfesor }: { clase: ClaseDetalle; esProfesor: boolean }) {
  const [trabajando, setTrabajando] = useState<'pdf' | 'word' | 'ecuaciones' | null>(null)
  const [hoja, setHoja] = useState<Bloque[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState('') // lo anuncia el lector de pantalla: sin esto, pulsar «Descargar» no dice nada

  // Con la hoja montada se espera a que se dibuje todo y recién entonces se abre la impresión.
  useEffect(() => {
    if (!hoja) return
    let activo = true
    const terminar = () => {
      setHoja(null)
      setTrabajando(null)
      setAviso('')
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
    setAviso('Preparando la hoja para guardar como PDF…')
    setTrabajando('pdf')
    setHoja(construirModelo(clase))
  }

  const word = async (modo: 'word' | 'ecuaciones') => {
    setError(null)
    setAviso('Preparando el archivo de Word…')
    setTrabajando(modo)
    try {
      const { generarDocx } = await import('@/lib/exportar/docx') // la librería de Word se baja solo al pedir el archivo
      const nombre = nombreDeArchivo(clase, 'docx')
      descargar(await generarDocx(construirModelo(clase), { formulas: modo === 'word' ? 'imagen' : 'ecuacion' }), nombre)
      setAviso(`Listo: se descargó ${nombre}.`)
    } catch {
      setAviso('')
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
        <Button variant="outline" className="h-11 flex-1 desk:h-9 desk:flex-none" disabled={trabajando !== null} onClick={() => void word('word')}>
          {trabajando === 'word' ? <Loader2 className="animate-spin" /> : <FileDown />} Descargar Word
        </Button>
      </div>
      {esProfesor && (
        <div className="space-y-2 rounded-xl bg-muted/50 p-3 text-xs leading-relaxed text-muted-foreground">
          <p>
            <strong className="text-foreground">Sobre las fórmulas en el Word:</strong> van como <strong>imagen</strong> para que se vean en cualquier programa
            (Word, Google Docs, el celular), así que ahí no se pueden editar. Si una fórmula está mal, corrígela arriba, en «De la pizarra», y vuelve a descargar.
          </p>
          <p>
            Si prefieres editarlas dentro de Word, descarga la versión con ecuaciones editables: se ve bien en Word y LibreOffice, pero puede que otros programas no las muestren.
          </p>
          <Button variant="outline" className="h-10 desk:h-8" disabled={trabajando !== null} onClick={() => void word('ecuaciones')}>
            {trabajando === 'ecuaciones' ? <Loader2 className="animate-spin" /> : <FileDown />} Word con ecuaciones editables
          </Button>
        </div>
      )}
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <FileText className="mt-0.5 size-3.5 shrink-0" /> Incluye el resumen, los puntos clave, la hoja de repaso, el mapa, las tarjetas y lo leído de la pizarra, con las fórmulas y los diagramas.
      </p>
      <p role="status" aria-live="polite" className="sr-only">{aviso}</p>
      <ErrorForm mensaje={error} />
      {hoja && createPortal(<div id="impresion"><VistaImpresion bloques={hoja} /></div>, document.body)}
    </div>
  )
}
