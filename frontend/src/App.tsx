import { useState } from 'react'
import { BookOpen, CalendarDays, Sparkles, Users } from 'lucide-react'
import { AppShell, type ItemNav } from '@/components/AppShell'
import { Cargando } from '@/components/comunes'
import { api, type Curso, type Rol, type Usuario } from '@/lib/api'
import { SesionProvider, useSesion } from '@/lib/sesion'
import { useCarga } from '@/lib/usar'
import { Clases } from '@/views/Clases'
import { Cursos } from '@/views/Cursos'
import { Entrada } from '@/views/Entrada'
import { Horario } from '@/views/Horario'
import { Personal } from '@/views/Personal'

const HORARIO: ItemNav = { id: 'horario', etiqueta: 'Horario', icono: CalendarDays }
const CURSOS: ItemNav = { id: 'cursos', etiqueta: 'Cursos', icono: BookOpen }
const CLASES: ItemNav = { id: 'clases', etiqueta: 'Clases', icono: Sparkles }
const PERSONAL: ItemNav = { id: 'personal', etiqueta: 'Personal', icono: Users }

// El alumno tiene un solo curso, así que no hay pestaña de cursos: su curso se muestra junto a su nombre.
const NAV: Record<Rol, ItemNav[]> = {
  ALUMNO: [HORARIO, CLASES],
  PROFESOR: [{ ...HORARIO, etiqueta: 'Mi horario' }, CURSOS, CLASES],
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
      {id === 'horario' && <Horario onAbrirClase={abrirClase} />}
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

export default function App() {
  return (
    <SesionProvider>
      <Aplicacion />
    </SesionProvider>
  )
}
