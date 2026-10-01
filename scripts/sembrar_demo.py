"""Crea una base de demostración (escuela_demo.db) con un colegio, personal, alumnos y un
horario semanal realista, para ver la interfaz con datos sin cargarlos a mano.

    python -m scripts.sembrar_demo

Usa su propia base: no toca escuela.db. Para que la API la use:

    DATABASE_URL=sqlite:///./escuela_demo.db uvicorn api:app --port 8000
"""
import datetime
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./escuela_demo.db")

from infraestructura.basedatos import Base, SessionLocal, engine  # noqa: E402
from infraestructura.modelos_orm import (  # noqa: E402
    AlumnoCurso, Bloque, Clase, Colegio, ContenidoClase, Curso, RolNombre, TipoBloque, Usuario, UsuarioRol,
)
from infraestructura.seguridad import hashear_secreto  # noqa: E402
from nucleo.validadores import validar_rut  # noqa: E402

PASSWORD_STAFF = "demo-clave-2026"
PIN_ALUMNO = "482915"
T = datetime.time


def rut(numero: int) -> str:
    """Arma un RUT válido a partir del cuerpo."""
    for dv in "0123456789K":
        if validar_rut(f"{numero}-{dv}"):
            return f"{numero}-{dv}"
    raise ValueError(numero)


# (inicio, fin, tipo) — la jornada de un día; las asignaturas se reparten por día.
JORNADA = [
    (T(8, 0), T(8, 45), TipoBloque.CLASE),
    (T(8, 45), T(9, 30), TipoBloque.CLASE),
    (T(9, 30), T(9, 45), TipoBloque.RECREO),
    (T(9, 45), T(10, 30), TipoBloque.CLASE),
    (T(10, 30), T(11, 15), TipoBloque.CLASE),
    (T(11, 15), T(11, 30), TipoBloque.RECREO),
    (T(11, 30), T(12, 15), TipoBloque.CLASE),
    (T(12, 15), T(13, 0), TipoBloque.CLASE),
    (T(13, 0), T(13, 45), TipoBloque.ALMUERZO),
]
# Asignatura y profesor (índice en PROFESORES) por bloque de clase, para cada día.
SEMANA = [
    [("Matemática", 0), ("Matemática", 0), ("Lenguaje", 1), ("Historia", 1), ("Ciencias", 2), ("Inglés", 3)],
    [("Lenguaje", 1), ("Ciencias", 2), ("Matemática", 0), ("Artes", 3), ("Historia", 1), ("Ed. Física", 2)],
    [("Inglés", 3), ("Lenguaje", 1), ("Ciencias", 2), ("Matemática", 0), ("Música", 3), ("Historia", 1)],
    [("Ciencias", 2), ("Matemática", 0), ("Historia", 1), ("Lenguaje", 1), ("Ed. Física", 2), ("Inglés", 3)],
    [("Historia", 1), ("Inglés", 3), ("Lenguaje", 1), ("Ciencias", 2), ("Matemática", 0), ("Artes", 3)],
]


# Material de estudio de ejemplo (lo que después generará el pipeline de IA), por asignatura.
MATERIAL = {
    "Matemática": {
        "resumen": "Hoy resolvimos ecuaciones de primer grado con una incógnita. La idea central es que una ecuación es una balanza: lo que se hace a un lado se debe hacer al otro para mantener el equilibrio. Vimos cómo despejar la incógnita en tres pasos y verificamos cada resultado reemplazándolo en la ecuación original.",
        "puntos_clave": "- Una ecuación es una igualdad que se cumple solo para ciertos valores de la incógnita.\n- Para despejar, se aplica la operación inversa a ambos lados.\n- Primero se eliminan los paréntesis, después se agrupan los términos semejantes.\n- Siempre se comprueba reemplazando el resultado en la ecuación original.",
        "hoja_repaso": "Ecuación de primer grado: ax + b = c. Se resuelve restando b a ambos lados y luego dividiendo por a. Por qué funciona: restar y dividir son las operaciones inversas de sumar y multiplicar, así que deshacen lo que le pasó a x. Error común: cambiar el signo de un término al pasarlo al otro lado sin aplicar la operación inversa.",
        "tarjetas": [
            {"pregunta": "¿Qué significa resolver una ecuación?", "respuesta": "Encontrar el valor de la incógnita que hace verdadera la igualdad."},
            {"pregunta": "¿Cómo despejas x en 3x + 5 = 20?", "respuesta": "Restas 5 a ambos lados (3x = 15) y divides por 3: x = 5."},
            {"pregunta": "¿Cómo compruebas que x = 5 es correcto?", "respuesta": "Reemplazas en la ecuación original: 3·5 + 5 = 20, y se cumple."},
        ],
        "transcripcion_texto": "Bueno, chicos, hoy vamos a trabajar con ecuaciones. Piensen en una balanza en equilibrio: si saco peso de un lado, tengo que sacar lo mismo del otro...",
    },
    "Lenguaje": {
        "resumen": "Trabajamos el texto narrativo y sus elementos: narrador, personajes, ambiente y acción. Diferenciamos al narrador en primera persona, que cuenta lo que vive, del narrador omnisciente, que conoce los pensamientos de todos. Analizamos un cuento breve identificando el conflicto y cómo se resuelve.",
        "puntos_clave": "- El narrador es quien cuenta la historia; no es lo mismo que el autor.\n- Narrador en primera persona: participa y solo sabe lo que él vive.\n- Narrador omnisciente: conoce pensamientos y sentimientos de todos los personajes.\n- El conflicto es el problema que mueve la historia y se resuelve en el desenlace.",
        "hoja_repaso": "Elementos del texto narrativo: narrador, personajes (principales y secundarios), ambiente (lugar y tiempo) y acciones. Para identificar el narrador, fíjate en el verbo y el pronombre: 'yo caminé' indica primera persona; 'ella pensó que...' con acceso a su mente indica omnisciente. Por qué importa: el tipo de narrador cambia cuánto sabe el lector.",
        "tarjetas": [
            {"pregunta": "¿Cuál es la diferencia entre autor y narrador?", "respuesta": "El autor escribe la obra; el narrador es la voz que cuenta la historia dentro de ella."},
            {"pregunta": "¿Qué es un narrador omnisciente?", "respuesta": "Uno que conoce todo: los hechos y los pensamientos de todos los personajes."},
            {"pregunta": "¿Qué es el conflicto en un cuento?", "respuesta": "El problema o tensión que impulsa la acción hasta el desenlace."},
        ],
        "transcripcion_texto": "Vamos a abrir el cuento en la página doce. Antes de leer, ¿quién me dice quién cuenta la historia? No es lo mismo el autor que el narrador...",
    },
    "Ciencias": {
        "resumen": "Estudiamos la célula como unidad básica de los seres vivos y sus organelos principales. Comparamos la célula animal con la vegetal: ambas tienen núcleo, mitocondrias y membrana, pero la vegetal suma pared celular y cloroplastos. Relacionamos cada organelo con su función, como una fábrica con distintas áreas.",
        "puntos_clave": "- La célula es la unidad estructural y funcional de los seres vivos.\n- El núcleo guarda el material genético y controla la célula.\n- Las mitocondrias liberan la energía de los nutrientes.\n- La célula vegetal tiene pared celular y cloroplastos; la animal no.",
        "hoja_repaso": "Organelos y función: núcleo (control y ADN), mitocondria (energía), ribosomas (fabrican proteínas), membrana (regula lo que entra y sale), cloroplasto (fotosíntesis, solo vegetal), pared celular (soporte, solo vegetal). Por qué las plantas tienen cloroplastos: producen su propio alimento con la luz; los animales lo obtienen comiendo.",
        "tarjetas": [
            {"pregunta": "¿Qué organelo produce la energía de la célula?", "respuesta": "La mitocondria."},
            {"pregunta": "¿Qué tiene la célula vegetal que no tiene la animal?", "respuesta": "Pared celular y cloroplastos."},
            {"pregunta": "¿Para qué sirve el núcleo?", "respuesta": "Guarda el ADN y dirige las funciones de la célula."},
            {"pregunta": "¿Qué función cumple la membrana celular?", "respuesta": "Regula qué sustancias entran y salen de la célula."},
        ],
        "transcripcion_texto": "Imaginen la célula como una pequeña fábrica. El núcleo es la oficina del gerente, las mitocondrias son la central eléctrica...",
    },
    "Historia": {
        "resumen": "Revisamos las causas y consecuencias de la Revolución Industrial. Partimos por la mecanización del trabajo y la máquina a vapor, y vimos cómo las personas pasaron del campo a las ciudades. Discutimos las condiciones de los obreros y el origen de los primeros movimientos sindicales.",
        "puntos_clave": "- La Revolución Industrial comenzó en Gran Bretaña a fines del siglo XVIII.\n- La máquina a vapor permitió producir más y transportar más rápido.\n- Hubo una fuerte migración del campo a la ciudad.\n- Las duras condiciones laborales dieron origen a los sindicatos.",
        "hoja_repaso": "Causas: nuevas máquinas, disponibilidad de carbón y capital, aumento de la población. Consecuencias: crecimiento de las ciudades, nueva clase obrera, desigualdad y reformas laborales. Por qué empezó en Gran Bretaña: tenía carbón, hierro, colonias que compraban sus productos y estabilidad política.",
        "tarjetas": [
            {"pregunta": "¿Dónde y cuándo comenzó la Revolución Industrial?", "respuesta": "En Gran Bretaña, a fines del siglo XVIII."},
            {"pregunta": "¿Qué invento fue clave para la industria y el transporte?", "respuesta": "La máquina a vapor."},
            {"pregunta": "¿Qué surgió como respuesta a las malas condiciones laborales?", "respuesta": "Los sindicatos y las primeras leyes laborales."},
        ],
        "transcripcion_texto": "Hoy vamos a viajar a Inglaterra, año 1780. Imaginen que ustedes trabajan en el campo y de pronto aparecen las fábricas...",
    },
}

MATERIAL["Inglés"] = {
    "resumen": "Repasamos el presente simple y el presente continuo. El presente simple sirve para rutinas y hechos que son siempre ciertos; el continuo, para lo que está pasando justo ahora. Practicamos con oraciones sobre actividades diarias y las que estaban ocurriendo en la sala.",
    "puntos_clave": "- Presente simple: rutinas y hechos (She plays soccer on Fridays).\n- Presente continuo: acciones en este momento (She is playing soccer now).\n- El continuo se forma con am/is/are + verbo terminado en -ing.\n- En tercera persona singular, el presente simple lleva -s (he works).",
    "hoja_repaso": "Presente simple = hábitos y verdades generales; palabras señal: always, usually, every day. Presente continuo = acción en progreso; palabras señal: now, right now, at the moment. Por qué importa: elegir mal el tiempo cambia el significado de la oración.",
    "tarjetas": [
        {"pregunta": "¿Cuándo se usa el presente continuo?", "respuesta": "Para acciones que ocurren en este momento: She is reading now."},
        {"pregunta": "¿Cómo se forma el presente continuo?", "respuesta": "am/is/are + verbo con -ing."},
        {"pregunta": "¿Qué pasa con el verbo en tercera persona del presente simple?", "respuesta": "Lleva -s: he works, she plays."},
    ],
    "transcripcion_texto": "Okay class, let's start. Look at the board: 'I play soccer' and 'I am playing soccer'. What is the difference?...",
}

def sin_choques(base, otro):
    """Reparte las 6 clases de `otro` en los 6 bloques del día sin que un profesor coincida con el de `base`
    en el mismo bloque (un profesor no puede estar en dos cursos a la vez). Búsqueda con retroceso."""
    def buscar(i, usados):
        if i == len(base):
            return []
        for j, (asig, prof) in enumerate(otro):
            if j in usados or prof == base[i][1]:
                continue
            resto = buscar(i + 1, usados | {j})
            if resto is not None:
                return [otro[j]] + resto
        return None
    return buscar(0, set())


# Jornada larga de 3°M: de 8:30 a 18:15 (el viernes termina a las 15:45). Prueba que el horario no asume jornadas cortas.
JORNADA_LARGA = [
    (T(8, 30), T(9, 15), TipoBloque.CLASE),
    (T(9, 15), T(10, 0), TipoBloque.CLASE),
    (T(10, 0), T(10, 15), TipoBloque.RECREO),
    (T(10, 15), T(11, 0), TipoBloque.CLASE),
    (T(11, 0), T(11, 45), TipoBloque.CLASE),
    (T(11, 45), T(12, 0), TipoBloque.RECREO),
    (T(12, 0), T(12, 45), TipoBloque.CLASE),
    (T(12, 45), T(13, 30), TipoBloque.CLASE),
    (T(13, 30), T(14, 15), TipoBloque.ALMUERZO),
    (T(14, 15), T(15, 0), TipoBloque.CLASE),
    (T(15, 0), T(15, 45), TipoBloque.CLASE),
    (T(15, 45), T(16, 0), TipoBloque.RECREO),
    (T(16, 0), T(16, 45), TipoBloque.CLASE),
    (T(16, 45), T(17, 30), TipoBloque.CLASE),
    (T(17, 30), T(18, 15), TipoBloque.CLASE),
]
# (asignatura, índice del profesor de 3°M): 12 clases al día, cada asignatura una vez.
MATERIAS_LARGA = [
    ("Matemática", 0), ("Lenguaje", 1), ("Física", 0), ("Historia", 1), ("Química", 2), ("Inglés", 2),
    ("Biología", 2), ("Filosofía", 1), ("Matemática", 0), ("Taller PAES", 2), ("Lenguaje", 1), ("Educación Física", 2),
]

# 8°B lleva la semana de 8°A corrida un día, reordenada solo lo necesario para que ningún profesor choque.
HORARIO_8B = [sin_choques(SEMANA[d], SEMANA[(d + 1) % 5]) for d in range(5)]
assert all(HORARIO_8B), "no hay horario de 8°B sin choques de profesores"

# (curso, día, asignatura, semanas atrás, estado) -> clases de ejemplo.
#   publicada   = aprobada por el profesor
#   por_aprobar = material de hace 3 h: el profesor aún está a tiempo de revisarlo
#   provisoria  = material de hace 30 h sin revisar: ya se publicó con advertencia
#   retirada    = el profesor la ocultó
#   procesando  = todavía sin material
CLASES_DEMO = [
    ("8°A", 0, "Matemática", 0, "publicada"),
    ("8°A", 1, "Lenguaje", 0, "publicada"),
    ("8°A", 2, "Ciencias", 0, "por_aprobar"),
    ("8°A", 3, "Historia", 1, "publicada"),
    ("8°A", 4, "Inglés", 0, "provisoria"),
    ("8°A", 1, "Ciencias", 0, "procesando"),  # sin material todavía
    ("8°B", 0, "Lenguaje", 0, "publicada"),
    ("8°B", 1, "Matemática", 0, "por_aprobar"),
    ("8°B", 3, "Inglés", 1, "retirada"),
]
HORAS_GENERADO = {"por_aprobar": 3, "provisoria": 30, "retirada": 40}


def fecha_pasada(dia_semana: int, semanas_atras: int) -> datetime.date:
    """La fecha más reciente (anterior a hoy) que cae en ese día de la semana, retrocediendo más semanas si se pide."""
    d = datetime.date.today() - datetime.timedelta(days=1)
    while d.weekday() != dia_semana:
        d -= datetime.timedelta(days=1)
    return d - datetime.timedelta(weeks=semanas_atras)


def main() -> None:
    Base.metadata.drop_all(engine)  # la demo se regenera limpia cada vez
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        colegio = Colegio(nombre="Colegio San Martín (demo)")
        db.add(colegio)
        db.flush()

        def staff(num, nombre, rol):
            u = Usuario(rut=rut(num), nombre=nombre, colegio_id=colegio.id, password_hash=hashear_secreto(PASSWORD_STAFF))
            u.roles = [UsuarioRol(rol=rol)]
            db.add(u)
            return u

        utp = staff(11111111, "Carolina Rojas", RolNombre.UTP)
        profes = [
            staff(12345678, "Marcos Fuentes", RolNombre.PROFESOR),
            staff(13456789, "Paula Soto", RolNombre.PROFESOR),
            staff(14567890, "Andrés Vera", RolNombre.PROFESOR),
            staff(15678901, "Daniela Muñoz", RolNombre.PROFESOR),
        ]
        alumnos = []
        for num, nombre in [(21000001, "Sofía Contreras"), (21000002, "Matías Pizarro"), (21000003, "Valentina Araya")]:
            a = Usuario(rut=rut(num), nombre=nombre, colegio_id=colegio.id, pin_hash=hashear_secreto(PIN_ALUMNO))
            a.roles = [UsuarioRol(rol=RolNombre.ALUMNO)]
            db.add(a)
            alumnos.append(a)
        db.flush()

        cursos = {}
        for nombre, codigo in [("8°A", "DEMO8A"), ("8°B", "DEMO8B")]:
            c = Curso(nombre=nombre, colegio_id=colegio.id, codigo_invitacion=codigo)
            db.add(c)
            cursos[nombre] = c
        db.flush()

        por_clave = {}  # (curso, día, asignatura) -> primer Bloque así, para colgarle las clases de ejemplo
        for nombre, curso in cursos.items():
            sala = "Sala 12" if nombre == "8°A" else "Sala 14"
            for dia, clases in enumerate(SEMANA):
                clases = clases if nombre == "8°A" else HORARIO_8B[dia]
                it = iter(clases)
                for ini, fin, tipo in JORNADA:
                    if tipo is TipoBloque.CLASE:
                        asig, p = next(it)
                        b = Bloque(curso_id=curso.id, tipo=tipo, asignatura=asig, profesor_id=profes[p].id,
                                   sala=sala, dia_semana=dia, hora_inicio=ini, hora_fin=fin)
                        db.add(b)
                        por_clave.setdefault((nombre, dia, asig), b)
                    else:
                        db.add(Bloque(curso_id=curso.id, tipo=tipo, dia_semana=dia, hora_inicio=ini, hora_fin=fin))

        # 3°M: jornada larga, con su propio profesorado (así no choca con los otros cursos).
        largos = [
            staff(16789012, "Ricardo Lagos", RolNombre.PROFESOR),
            staff(17890123, "Carmen Ibáñez", RolNombre.PROFESOR),
            staff(18901234, "Tomás Bravo", RolNombre.PROFESOR),
        ]
        c3m = Curso(nombre="3°M", colegio_id=colegio.id, codigo_invitacion="DEMO3M")
        camila = Usuario(rut=rut(21000004), nombre="Camila Soto", colegio_id=colegio.id, pin_hash=hashear_secreto(PIN_ALUMNO))
        camila.roles = [UsuarioRol(rol=RolNombre.ALUMNO)]
        db.add_all([c3m, camila])
        db.flush()
        db.add(AlumnoCurso(usuario_id=camila.id, curso_id=c3m.id))
        for dia in range(5):
            n = 0
            for ini, fin, tipo in JORNADA_LARGA:
                if dia == 4 and fin > T(15, 45):
                    continue  # el viernes se sale antes
                if tipo is TipoBloque.CLASE:
                    asig, p = MATERIAS_LARGA[(n + 3 * dia) % len(MATERIAS_LARGA)]
                    n += 1
                    db.add(Bloque(curso_id=c3m.id, tipo=tipo, asignatura=asig, profesor_id=largos[p].id,
                                  sala="Sala 21", dia_semana=dia, hora_inicio=ini, hora_fin=fin))
                else:
                    db.add(Bloque(curso_id=c3m.id, tipo=tipo, dia_semana=dia, hora_inicio=ini, hora_fin=fin))
        db.flush()
        print(f"  Alumna 3°M {camila.rut}   PIN {PIN_ALUMNO}   (jornada de 8:30 a 18:15)")

        for a in alumnos[:2]:
            db.add(AlumnoCurso(usuario_id=a.id, curso_id=cursos["8°A"].id))
        db.add(AlumnoCurso(usuario_id=alumnos[2].id, curso_id=cursos["8°B"].id))
        db.flush()

        ahora = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        for curso, dia, asignatura, semanas, estado in CLASES_DEMO:
            bloque = por_clave[(curso, dia, asignatura)]
            clase = Clase(bloque_id=bloque.id, fecha=fecha_pasada(dia, semanas))
            if estado != "procesando":
                clase.contenido = ContenidoClase(
                    **MATERIAL[bloque.asignatura],
                    aprobado=(estado == "publicada"),
                    retirado=(estado == "retirada"),
                    generado_en=ahora - datetime.timedelta(hours=HORAS_GENERADO.get(estado, 24 * 7)),
                )
            db.add(clase)
        db.commit()

        print(f"Base de demostración: {engine.url}")
        print(f"  UTP        {utp.rut}   contraseña {PASSWORD_STAFF}")
        print(f"  Profesor   {profes[0].rut}   contraseña {PASSWORD_STAFF}")
        print(f"  Alumno 8°A {alumnos[0].rut}   PIN {PIN_ALUMNO}")
        print(f"  Alumno 8°B {alumnos[2].rut}   PIN {PIN_ALUMNO}")
        print("  Códigos de curso: DEMO8A, DEMO8B")
        # Comprobación: ningún profesor en dos bloques que se cruzan (la misma regla que aplica el editor del UTP).
        bloques = db.query(Bloque).filter(Bloque.profesor_id.isnot(None)).all()
        choques = [
            (a.id, b.id) for i, a in enumerate(bloques) for b in bloques[i + 1:]
            if a.profesor_id == b.profesor_id and a.dia_semana == b.dia_semana
            and a.hora_inicio < b.hora_fin and b.hora_inicio < a.hora_fin
        ]
        assert not choques, f"hay profesores en dos lugares a la vez: {choques[:3]}"
        print(f"  {len(CLASES_DEMO)} clases de ejemplo (publicada, por aprobar, provisoria, retirada y procesando)")


if __name__ == "__main__":
    main()
