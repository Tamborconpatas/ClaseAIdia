# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

import re
import unicodedata

# shortcut: lista corta de palabras (por palabra entera, no por trozo, para no vetar apellidos reales);
# un doble sentido o un apodo que no esté acá pasa. Ampliarla con lo que vaya apareciendo en el piloto.
PALABRAS_VETADAS = frozenset(
    """
    weon huevon hueon aweonao culiao conchetumare conchesumadre ctm puta puto putas putos mierda caca pico pene verga
    vagina teta tetas culo culos poto pichula pichi chucha chuchas maricon marica maraco mraco zorra perra cagon cagado
    coño concha follar coger pajero paja pajera sexo sexy porno pornografia gay lesbiana hitler nazi satan diablo
    admin administrador profesor profe tonto tonta idiota imbecil estupido estupida gordo gorda feo fea
    anonimo anonima test prueba asdf qwerty fulano mengano
    """.split()
)
_LEET = str.maketrans("0134578@$", "oieastbas")


def _forma_simple(palabra: str) -> str:
    """Sin tildes, sin trucos de escritura (w3on, hueeeon) para compararla con la lista."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", palabra.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"(.)\1+", r"\1", sin_tildes.translate(_LEET))


def nombre_de_persona_aceptable(nombre: str) -> str | None:
    """None si el nombre sirve; si no, el motivo en palabras para quien lo escribió."""
    partes = nombre.split()
    if not all(re.fullmatch(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", p) for p in partes):
        return "El nombre solo puede llevar letras (sin números, símbolos ni emojis)."
    vetadas = {_forma_simple(p) for p in PALABRAS_VETADAS}
    if any(_forma_simple(p) in vetadas for p in partes):
        return "Ese nombre no es válido: escribe tu nombre real, como en tu carnet."
    return None


# Combinaciones nombre+apellido que suenan a otra cosa. shortcut: lista corta y conocida; una broma que no esté
# acá pasa sin aviso. Ampliarla con lo que aparezca en el piloto (se escriben tal cual, sin importar tildes ni b/v).
BROMAS = (
    "El Zapato", "Armando Casas", "Aquiles Baeza", "Rosa Melo", "Alan Brito", "Débora", "Elba Lazo", "Susana Oria",
    "Zoila Vaca", "Aitor Tilla", "Estela Gartija", "Armando Paredes", "Elsa Pato", "Dolores Delano", "Aquiles Brinco",
    "Ernesto Pajares", "Elvis Tek", "Lola Mento", "Aida Pelo",
)


def _fonetica(texto: str) -> str:
    """Letras que suenan igual quedan iguales: s/z/c, b/v, ll/y, qu/k, sin h ni tildes ni espacios."""
    t = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z]", "", t).replace("ll", "y").replace("h", "")
    t = re.sub(r"c(?=[ei])", "s", t).replace("qu", "k").replace("c", "k").replace("z", "s").replace("v", "b")
    return re.sub(r"(.)\1+", r"\1", t)


_FONETICAS_DE_BROMAS = frozenset(_fonetica(b) for b in BROMAS)


def suena_a_broma(nombre: str) -> bool:
    """Alerta, no bloqueo: ¿alguna tanda de palabras seguidas del nombre, unidas, suena a una broma conocida?"""
    palabras = nombre.split()
    return any(
        _fonetica("".join(palabras[i:j])) in _FONETICAS_DE_BROMAS
        for i in range(len(palabras))
        for j in range(i + 1, len(palabras) + 1)
    )
