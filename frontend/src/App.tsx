import { useEffect, useState } from 'react'
import { BookOpen, CalendarDays, Mic, Sparkles, Users } from 'lucide-react'
import { AppShell, type ItemNav } from '@/components/AppShell'
import { Cargando } from '@/components/comunes'
import { api, type Curso, type Rol, type Usuario } from '@/lib/api'
import { equipoActivo, soltarEquipo, useEquipo } from '@/lib/grabador'
import { SesionProvider, useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { Clases } from '@/views/Clases'
import { Cursos } from '@/views/Cursos'
import { Entrada } from '@/views/Entrada'
import { Grabar } from '@/views/Grabar'
import { Horario } from '@/views/Horario'
import { Legal, type PaginaLegal } from '@/views/Legal'
import { Personal } from '@/views/Personal'

const HORARIO: ItemNav = { id: 'horario', etiqueta: 'Horario', icono: CalendarDays }
const CURSOS: ItemNav = { id: 'cursos', etiqueta: 'Cursos', icono: BookOpen }
const CLASES: ItemNav = { id: 'clases', etiqueta: 'Clases', icono: Sparkles }
const PERSONAL: ItemNav = { id: 'personal', etiqueta: 'Personal', icono: Users }
const GRABAR: ItemNav = { id: 'grabar', etiqueta: 'Grabar', icono: Mic }

// El alumno tiene un solo curso, así que no hay pestaña de cursos: su curso se muestra junto a su nombre.
const NAV: Record<Rol, ItemNav[]> = {
  ALUMNO: [HORARIO, CLASES],
  PROFESOR: [{ ...HORARIO, etiqueta: 'Mi horario' }, GRABAR, CURSOS, CLASES],
  UTP: [CURSOS, HORARIO, CLASES, PERSONAL],
}
const ETIQUETA_ROL: Record<Rol, string> = { ALUMNO: 'Alumno', PROFESOR: 'Profesor', UTP: 'UTP' }

/** Solo existe con sesión iniciada: al salir se desmonta, así quien entre después empieza de cero. */
function Principal({ usuario, rol, onSalir }: { usuario: Usuario; rol: Rol; onSalir: () => void }) {
  const [activo, setActivo] = useState<string | null>(null)
  // Curso preseleccionado en Clases cuando se llega desde "Ver clases" en un curso.
  const [cursoClases, setCursoClases] = useState<number | null>(null)
  // Clase abierta de entrada en Clases cuando se llega desde el horario.
  const [claseInicial, setClaseInicial] = useState<number | null>(null)
  const esAlumno = rol === 'ALUMNO'
  const equipo = useEquipo()
  // Al cerrar la sesión (o vencer) este componente se desmonta: el micrófono de este equipo se suelta.
  useEffect(() => () => soltarEquipo(), [])
  const cursoAlumno = useCarga(() => (esAlumno ? api<Curso[]>('/cursos') : Promise.resolve([])), [esAlumno])

  const items = NAV[rol]
  const id = items.find((i) => i.id === activo)?.id ?? items[0].id
  const nombreCurso = cursoAlumno.datos?.[0]?.nombre
  const etiquetaRol = esAlumno && nombreCurso ? `Alumno · ${nombreCurso}` : ETIQUETA_ROL[rol]

  const verClases = (cursoId: number) => {
    setCursoClases(cursoId)
    setClaseInicial(null)
    setActivo('clases')
  }
  const abrirClase = (claseId: number) => {
    setCursoClases(null)
    setClaseInicial(claseId)
    setActivo('clases')
  }
  const cambiar = (nuevo: string) => {
    setCursoClases(null)
    setClaseInicial(null)
    setActivo(nuevo)
  }

  return (
    <AppShell items={items} activo={id} onCambiar={cambiar} usuario={usuario} etiquetaRol={etiquetaRol} onSalir={onSalir}>
      {equipoActivo(equipo.info) && id !== 'grabar' && (
        <button
          onClick={() => cambiar('grabar')}
          className="mb-4 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-red-100 dark:bg-red-950/60 px-3 text-sm font-medium text-red-900 dark:text-red-200 ring-1 ring-red-200 dark:ring-red-800"
        >
          <span className="size-2 animate-pulse rounded-full bg-red-600" /> Este equipo está grabando una clase: volver a los controles
        </button>
      )}
      {id === 'horario' && <Horario onAbrirClase={abrirClase} />}
      {id === 'grabar' && <Grabar onAbrirClase={abrirClase} />}
      {id === 'cursos' && <Cursos esUtp={rol === 'UTP'} esProfesor={rol === 'PROFESOR'} onVerClases={verClases} />}
      {id === 'personal' && <Personal />}
      {id === 'clases' && <Clases key={`${cursoClases}-${claseInicial}`} cursoInicial={cursoClases} claseInicial={claseInicial} />}
    </AppShell>
  )
}

function Aplicacion() {
  const { sesion, usuario, rol, salir } = useSesion()
  if (!sesion || !rol) return <Entrada />
  if (!usuario) return <Cargando texto="Entrando…" />
  return <Principal key={usuario.id} usuario={usuario} rol={rol} onSalir={salir} />
}

/** Páginas públicas: #/privacidad y #/terminos (con hash, para no depender de cómo se sirva el sitio). */
function paginaLegalActual(): PaginaLegal | null {
  const h = window.location.hash
  return h === '#/privacidad' ? 'privacidad' : h === '#/terminos' ? 'terminos' : null
}

export default function App() {
  const [legal, setLegal] = useState(paginaLegalActual)
  useEffect(() => {
    const alCambiar = () => {
      setLegal(paginaLegalActual())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', alCambiar)
    return () => window.removeEventListener('hashchange', alCambiar)
  }, [])

  if (legal) return <Legal pagina={legal} onVolver={() => window.history.back()} />
  return (
    <SesionProvider>
      <Aplicacion />
    </SesionProvider>
  )
}
