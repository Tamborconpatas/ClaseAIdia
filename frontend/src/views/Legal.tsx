import type { ReactNode } from 'react'
import { ArrowLeft, Mail } from 'lucide-react'
import { Logo } from '@/components/comunes'

export type PaginaLegal = 'privacidad' | 'terminos'

/** Medio de contacto del equipo: se configura en frontend/.env (VITE_CONTACTO). Sin él, se pide al colegio. */
const CONTACTO = (import.meta.env.VITE_CONTACTO as string | undefined)?.trim()

export function Contacto() {
  return (
    <p className="flex items-start gap-2 rounded-xl bg-muted/60 p-3.5 text-sm">
      <Mail className="mt-0.5 size-4 shrink-0" />
      <span>
        {CONTACTO ? (
          <>
            ¿Dudas, o quieres acceder, corregir o eliminar datos? Escríbenos a <strong>{CONTACTO}</strong>.
          </>
        ) : (
          <>
            ¿Dudas, o quieres acceder, corregir o eliminar datos? Consulta a UTP de tu colegio, que administra esta
            plataforma. <em>(Falta configurar el contacto del equipo: ver «frontend/.env.example».)</em>
          </>
        )}
      </span>
    </p>
  )
}

/** Enlaces discretos a las páginas legales: pie de la entrada y de cada pantalla con sesión. */
export function PieLegal({ className }: { className?: string }) {
  return (
    <nav aria-label="Información legal" className={`flex flex-wrap justify-center gap-x-5 gap-y-1 text-xs text-muted-foreground ${className ?? ''}`}>
      <a href="#/privacidad" className="hover:text-foreground hover:underline">
        Privacidad
      </a>
      <a href="#/terminos" className="hover:text-foreground hover:underline">
        Términos y condiciones
      </a>
    </nav>
  )
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{titulo}</h2>
      <div className="space-y-2 leading-relaxed text-foreground/90 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5">{children}</div>
    </section>
  )
}

const PRIVACIDAD = (
  <>
    <Seccion titulo="Qué es ClaseAIdia">
      <p>
        ClaseAIdia ayuda a los alumnos que se distraen o faltan a clases: transcribe las clases y prepara un resumen, puntos
        clave, una hoja de repaso y tarjetas de estudio. Todo el procesamiento ocurre <strong>en el servidor del propio
        colegio</strong>, con inteligencia artificial que corre ahí mismo; no se envía información a servicios de IA en la
        nube.
      </p>
    </Seccion>
    <Seccion titulo="Qué datos se guardan">
      <ul>
        <li>De cada persona: nombre, RUT y curso (alumnos) o asignaturas (profesores).</li>
        <li>El PIN de los alumnos y la contraseña del personal se guardan <strong>cifrados de forma irreversible</strong>: nadie, ni el equipo, puede leerlos.</li>
        <li>Por cada clase procesada: la <strong>transcripción en texto</strong> y el material de estudio generado a partir de ella.</li>
        <li>El horario del curso y las clases realizadas.</li>
      </ul>
    </Seccion>
    <Seccion titulo="Qué NO se guarda">
      <ul>
        <li><strong>El audio nunca se guarda.</strong> Se usa para generar el texto y se borra apenas termina de procesarse.</li>
        <li>No hay cookies de seguimiento, publicidad ni analíticas de terceros. La sesión usa un código temporal guardado en el navegador, que vence solo.</li>
      </ul>
    </Seccion>
    <Seccion titulo="Quién puede ver qué">
      <ul>
        <li>Un <strong>alumno</strong> ve el horario y el material de las clases de su propio curso, una vez que su profesor lo revisó. Si el profesor no alcanza a revisarlo, se muestra igualmente con una advertencia de que no fue revisado.</li>
        <li>Un <strong>profesor</strong> ve las clases que dicta, puede corregir el material y decidir si se publica o se retira.</li>
        <li>El <strong>UTP</strong> administra cursos, horarios y personal, y puede ver las clases del colegio.</li>
        <li>Las personas de un colegio no ven los datos de otro.</li>
      </ul>
    </Seccion>
    <Seccion titulo="Menores de edad">
      <p>
        La plataforma está pensada para estudiantes de 7° básico a 4° medio. Antes de usarla con alumnos menores de edad, el
        colegio debe contar con el <strong>consentimiento informado de sus apoderados</strong>.
      </p>
    </Seccion>
    <Seccion titulo="Tus derechos">
      <p>
        Puedes pedir acceso a tus datos, que se corrijan o que se eliminen. En el caso de un alumno menor de edad, lo pide su
        apoderado. Por cuánto tiempo se conservan las transcripciones lo define el colegio.
      </p>
    </Seccion>
    <Contacto />
  </>
)

const TERMINOS = (
  <>
    <Seccion titulo="Para qué sirve">
      <p>
        ClaseAIdia es una herramienta de apoyo al estudio. Su material (resúmenes, puntos clave, hojas de repaso y tarjetas)
        lo genera una inteligencia artificial a partir de lo que se dijo en clase, y <strong>puede contener errores</strong>.
        No reemplaza a tu profesor, tus apuntes ni los materiales oficiales del curso.
      </p>
    </Seccion>
    <Seccion titulo="Material «sin revisar»">
      <p>
        Tu profesor revisa el material antes de publicarlo. Si no alcanza a hacerlo, el material aparece igual, marcado como
        «Sin revisar», para que no te quedes sin estudiar; ten especial cuidado con él y contrástalo con tus apuntes.
      </p>
    </Seccion>
    <Seccion titulo="Tu cuenta">
      <ul>
        <li>Tu PIN (alumnos) o tu contraseña (personal) son personales: no los compartas.</li>
        <li>Si los olvidas, tu profesor o UTP puede darte un código de un solo uso para elegir uno nuevo.</li>
        <li>Tras varios intentos fallidos la cuenta se bloquea un tiempo, para protegerla.</li>
      </ul>
    </Seccion>
    <Seccion titulo="Uso adecuado">
      <ul>
        <li>Usa la plataforma solo para fines de estudio y gestión escolar de tu colegio.</li>
        <li>No intentes acceder a cuentas, cursos o datos que no te corresponden.</li>
        <li>El colegio puede suspender una cuenta que se use de forma indebida.</li>
      </ul>
    </Seccion>
    <Seccion titulo="Grabación de clases">
      <p>
        Las clases solo se transcriben con el conocimiento del profesor y del curso. El audio no se conserva (ver la política
        de privacidad).
      </p>
    </Seccion>
    <Contacto />
  </>
)

/** Páginas públicas (se ven con o sin sesión). Son un borrador: deben ser revisadas por el colegio antes del piloto. */
export function Legal({ pagina, onVolver }: { pagina: PaginaLegal; onVolver: () => void }) {
  const titulo = pagina === 'privacidad' ? 'Política de privacidad' : 'Términos y condiciones'
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b bg-card px-4 py-3 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))]">
        <div className="mx-auto flex max-w-2xl items-center justify-between">
          <Logo />
          <button onClick={onVolver} className="flex h-10 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> Volver
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-2xl space-y-6 px-4 py-8 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))]">
        <h1 className="text-3xl font-semibold tracking-tight">{titulo}</h1>
        <p role="note" className="rounded-xl bg-muted/60 p-3.5 text-sm">
          Este texto resume el <strong>aviso para el colegio</strong> del archivo README del proyecto, que el colegio acepta al
          instalar y usar la plataforma. Esta página es su respaldo, para consulta de alumnos y apoderados.
        </p>
        {pagina === 'privacidad' ? PRIVACIDAD : TERMINOS}
        <PieLegal className="pt-4" />
      </main>
    </div>
  )
}
