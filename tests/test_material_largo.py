# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Material de estudio de una clase larga: la ventana de contexto de Ollama, la condensación por niveles y la
generación por secciones.
(Salió de una clase real de 92 minutos: el prompt final no cabía en la ventana por defecto, Ollama le recortaba las
instrucciones, y el material salía sin hoja de repaso ni tarjetas, o con un resumen de pocos cientos de caracteres.)"""
import pytest

from infraestructura import cliente_ollama
from servicios import servicio_material_estudio as m


def test_la_ventana_crece_con_el_prompt_y_tiene_minimo_y_tope():
    assert cliente_ollama.ventana_necesaria("hola", 512) == 4096  # mínimo
    prompt_de_clase_real = "x" * 20_825  # el que falló con la clase de 92 min
    v = cliente_ollama.ventana_necesaria(prompt_de_clase_real, 2048)
    assert v > 20_825 // 3 + 2048  # cabe el prompt y la respuesta
    assert v % 1024 == 0 and v <= 16384
    assert cliente_ollama.ventana_necesaria("x" * 500_000, 2048) == 16384  # tope


def test_el_cliente_le_pide_a_ollama_esa_ventana_y_una_temperatura_baja(monkeypatch):
    enviados = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(cliente_ollama.requests, "post", lambda url, json, timeout: enviados.append(json) or Respuesta())
    cliente_ollama.generate("x" * 20_825, model="m", max_tokens=2048)
    opciones = enviados[0]["options"]
    assert opciones["num_ctx"] == cliente_ollama.ventana_necesaria("x" * 20_825, 2048)
    assert opciones["num_predict"] == 2048
    assert opciones["temperature"] == 0.3  # resumir fielmente: sin la creatividad por defecto (0,8)


def test_una_ventana_fijada_a_mano_manda_sobre_la_calculada(monkeypatch):
    """Varias llamadas seguidas piden la misma: si cambia entre una y otra, Ollama recarga el modelo."""
    enviados = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(cliente_ollama.requests, "post", lambda url, json, timeout: enviados.append(json) or Respuesta())
    cliente_ollama.generate("corto", model="m", max_tokens=100, ventana=12288)
    assert enviados[0]["options"]["num_ctx"] == 12288


def _con_modelo_falso(monkeypatch, tamano_de_cada_resumen):
    llamadas = []

    def falso(prompt, model, max_tokens, ollama_url="x", ventana=None):
        llamadas.append(len(prompt))
        return "r" * tamano_de_cada_resumen

    monkeypatch.setattr(m.ollama_client, "generate", falso)
    return llamadas


def test_si_lo_condensado_cabe_se_condensa_una_sola_vez(monkeypatch):
    llamadas = _con_modelo_falso(monkeypatch, 100)
    salida = m._condense_until_fits(["a" * 6000] * 4, "m", "u", 6000)
    assert len(llamadas) == 4 and salida.count("[Parte") == 4


def test_si_lo_condensado_no_cabe_se_vuelve_a_condensar(monkeypatch):
    llamadas = _con_modelo_falso(monkeypatch, 2500)  # 13 partes de ~2500 = más de 24 mil caracteres
    salida = m._condense_until_fits(["a" * 6000] * 13, "m", "u", 6000)
    assert len(llamadas) > 13  # hubo un segundo nivel
    assert len(salida) <= m._MAX_CARACTERES_FINAL


def test_hay_un_tope_de_niveles_aunque_el_modelo_no_resuma_nada(monkeypatch):
    llamadas = _con_modelo_falso(monkeypatch, 6000)  # nunca reduce: no debe girar para siempre
    m._condense_until_fits(["a" * 6000] * 13, "m", "u", 6000)
    assert 13 < len(llamadas) < 13 * 8 * m._MAX_NIVELES


class _ModeloFalso:
    """Un Ollama de mentira que anota cada llamada y contesta según lo que se le pide."""

    def __init__(self):
        self.llamadas = []

    def __call__(self, prompt, model, max_tokens, ollama_url="x", ventana=None):
        self.llamadas.append({"prompt": prompt, "max_tokens": max_tokens, "ventana": ventana})
        if prompt.startswith("Este es el bloque"):
            return "resumen parcial " * 120
        if "resumen claro y completo" in prompt:
            return "Primer párrafo del resumen. Segundo párrafo del resumen. Y se discutió que el desarrollo"  # cortado
        if "lista con viñetas" in prompt:
            return "- punto uno.\n- punto dos.\n- punto tres que se cort"
        if "hoja de repaso" in prompt:
            return "Hoja de repaso."
        return "P: ¿a?\nR: b\n\n2. P: ¿c?\nR: d"


def _clase_larga(monkeypatch, asignatura="Aplicaciones de IA"):
    falso = _ModeloFalso()
    monkeypatch.setattr(m.ollama_client, "generate", falso)
    parametros = {"ollama_model": "m", "ollama_max_tokens": 2048, "ollama_url": "u", "ollama_chunk_chars": 6000}
    monkeypatch.setattr(m.app_config, "get_param", lambda k: parametros[k])
    return falso, m.generate_study_material("Esto es una frase de clase. " * 4000, asignatura)  # ~110 mil caracteres


def _de_secciones(falso):
    return [c for c in falso.llamadas if not c["prompt"].startswith("Este es el bloque")]


def test_una_clase_larga_se_genera_en_cuatro_llamadas_una_por_seccion(monkeypatch):
    """Lo que falló: pedir las cuatro secciones juntas dejaba un resumen cortito, y con el prompt más largo que la
    ventana de Ollama se perdían la hoja de repaso y las tarjetas."""
    falso, (resumen, puntos, hoja, tarjetas) = _clase_larga(monkeypatch)
    secciones = _de_secciones(falso)
    assert len(secciones) == 4
    assert len({c["ventana"] for c in secciones}) == 1 and secciones[0]["ventana"]  # la misma ventana: no recargar el modelo
    assert [c["max_tokens"] for c in secciones] == [t for _, t, _ in m._SECCIONES]
    assert all(len(c["prompt"]) < m._MAX_CARACTERES_FINAL + 3000 for c in secciones)
    assert hoja == "Hoja de repaso." and tarjetas == [{"pregunta": "¿a?", "respuesta": "b"}, {"pregunta": "¿c?", "respuesta": "d"}]


def test_el_contenido_va_primero_y_la_instruccion_al_final(monkeypatch):
    """Con el mismo principio en las cuatro llamadas Ollama reutiliza lo ya leído; y si algo se recortara, que no sea la instrucción."""
    falso, _ = _clase_larga(monkeypatch)
    secciones = [c["prompt"] for c in _de_secciones(falso)]
    base = secciones[0][: secciones[0].index("---\n")]
    assert all(p.startswith(base) for p in secciones)
    assert secciones[0].rstrip().endswith("Responde solo con eso, sin encabezados.")


def test_el_modelo_sabe_la_materia_y_que_la_transcripcion_tiene_errores(monkeypatch):
    """Los resúmenes parciales (13 en la clase real) y las cuatro secciones llevan el contexto."""
    falso, _ = _clase_larga(monkeypatch, asignatura="Aplicaciones de IA")
    assert len(falso.llamadas) > 4
    for c in falso.llamadas:
        assert "«Aplicaciones de IA»" in c["prompt"]
        assert "errores" in c["prompt"] and "Ignora los saludos" in c["prompt"]


def test_sin_materia_el_contexto_sigue_pidiendo_corregir_y_ignorar_la_charla(monkeypatch):
    falso, _ = _clase_larga(monkeypatch, asignatura=None)
    for c in falso.llamadas:
        assert "materia «" not in c["prompt"]
        assert "errores" in c["prompt"] and "Ignora los saludos" in c["prompt"]


def test_una_oracion_cortada_por_falta_de_tokens_se_quita(monkeypatch):
    _, (resumen, puntos, hoja, tarjetas) = _clase_larga(monkeypatch)
    assert resumen == "Primer párrafo del resumen. Segundo párrafo del resumen."
    assert puntos == "- punto uno.\n- punto dos."


def test_sin_cola_incompleta_no_toca_lo_que_esta_completo_ni_borra_casi_todo():
    assert m._sin_cola_incompleta("Una frase completa.") == "Una frase completa."
    largo = "Una frase larga y completa que ocupa buen espacio. Otra frase también larga y completa."
    assert m._sin_cola_incompleta(largo + " Tres que se cort") == largo
    sin_punto = "Un texto largo sin ningún punto que se cortó a la mitad"
    assert m._sin_cola_incompleta(sin_punto) == sin_punto
    casi_todo = "Hola. y luego un texto larguísimo que ocupa casi todo lo escrito y se cortó"
    assert m._sin_cola_incompleta(casi_todo) == casi_todo  # cortar dejaría solo «Hola.»


def test_si_el_modelo_repite_el_encabezado_de_la_seccion_se_quita():
    assert m._texto_de_seccion("**RESUMEN**\nLa clase trató de X.", "resumen") == "La clase trató de X."
    assert m._texto_de_seccion("La clase trató de X.", "resumen") == "La clase trató de X."
    # Una oración que empieza con la palabra del encabezado no es un encabezado: no se le come el principio.
    assert m._texto_de_seccion("Resumen de la clase: se vio X.", "resumen") == "Resumen de la clase: se vio X."
    assert m._texto_de_seccion("Hoja de repaso.", "hoja_repaso") == "Hoja de repaso."
    # ...ni siquiera cuando la respuesta sigue en más líneas.
    assert m._texto_de_seccion("Resumen de la clase: se vio X.\nY después se vio Z.", "resumen") == "Resumen de la clase: se vio X.\nY después se vio Z."


# --- Formato de la respuesta del modelo (visto en la clase real) --------------------------------------


def test_los_encabezados_con_negritas_no_dejan_asteriscos_en_el_resumen():
    crudo = "**RESUMEN**\nLa clase trató de X.\n\n**PUNTOS CLAVE:**\n- uno\n- dos\n\n**HOJA DE REPASO**\nrepaso\n\n**TARJETAS DE ESTUDIO**\nP: a\nR: b"
    partes = m._split_study_material(crudo)
    assert partes["resumen"] == "La clase trató de X."
    assert partes["puntos_clave"].startswith("- uno") and partes["hoja_repaso"] == "repaso" and partes["tarjetas"].startswith("P: a")


def test_las_tarjetas_numeradas_son_tarjetas_distintas():
    """El 3B escribió «2. P: ...» pese a que se le pidió no numerar, y las 11 tarjetas se fundían en una sola."""
    crudo = "P: ¿Qué es A?\nR: Es A.\n\n2. P: ¿Qué es B?\nR: Es B.\n\n3) P: ¿Qué es C?\nR: Es C."
    assert m._parse_flashcards(crudo) == [
        {"pregunta": "¿Qué es A?", "respuesta": "Es A."},
        {"pregunta": "¿Qué es B?", "respuesta": "Es B."},
        {"pregunta": "¿Qué es C?", "respuesta": "Es C."},
    ]


def test_las_tarjetas_sin_numerar_o_con_p1_siguen_funcionando():
    assert len(m._parse_flashcards("P: a\nR: b\nP: c\nR: d")) == 2
    assert len(m._parse_flashcards("P1: a\nR1: b\nP2: c\nR2: d")) == 2


# --- Un modelo chico (llama3.2:1b, el que se usa sin GPU) escribe las tarjetas de otra forma -----------


def test_tarjetas_en_una_sola_linea_sin_saltos():
    """Lo que escribió el 1B en la clase real: `P: ... R: ... P: ... R: ...` todo seguido. Antes daba 0 tarjetas en silencio."""
    crudo = "P: ¿Qué es la IA? R: Un campo de estudio. P: ¿Qué es el aprendizaje supervisado? R: Aprender con etiquetas. P: ¿Y la regresión? R: Predecir un valor continuo."
    assert m._parse_flashcards(crudo) == [
        {"pregunta": "¿Qué es la IA?", "respuesta": "Un campo de estudio."},
        {"pregunta": "¿Qué es el aprendizaje supervisado?", "respuesta": "Aprender con etiquetas."},
        {"pregunta": "¿Y la regresión?", "respuesta": "Predecir un valor continuo."},
    ]


def test_una_palabra_que_termina_en_r_o_p_dentro_del_texto_no_parte_una_tarjeta():
    crudo = "P: ¿Qué es aprender: memorizar o entender?\nR: Entender: es lo que importa en la ESP: la práctica.\nP: ¿Otra?\nR: Sí."
    tarjetas = m._parse_flashcards(crudo)
    assert [t["pregunta"] for t in tarjetas] == ["¿Qué es aprender: memorizar o entender?", "¿Otra?"]
    assert tarjetas[0]["respuesta"] == "Entender: es lo que importa en la ESP: la práctica."


def test_una_seccion_que_sale_vacia_se_pide_una_vez_mas(monkeypatch):
    llamadas = []

    def falso(prompt, model, max_tokens, ollama_url="x", ventana=None):
        llamadas.append(prompt)
        if prompt.startswith("Este es el bloque"):
            return "resumen parcial " * 50
        if "tarjetas de estudio" in prompt:  # el primer intento no trae ninguna tarjeta que se entienda
            return "P: ¿a? R: b" if "al pie de la letra" in prompt else "Aquí tienes algunas ideas sobre la clase."
        return "Texto de la sección."

    monkeypatch.setattr(m.ollama_client, "generate", falso)
    parametros = {"ollama_model": "m", "ollama_max_tokens": 2048, "ollama_url": "u", "ollama_chunk_chars": 6000}
    monkeypatch.setattr(m.app_config, "get_param", lambda k: parametros[k])
    _, _, _, tarjetas = m.generate_study_material("Esto es una frase de clase. " * 4000, "X")
    assert tarjetas == [{"pregunta": "¿a?", "respuesta": "b"}]
    assert sum("tarjetas de estudio" in p for p in llamadas) == 2


def test_si_tras_el_segundo_intento_sigue_sin_haber_tarjetas_no_se_pide_una_tercera_vez(monkeypatch):
    llamadas = []

    def falso(prompt, model, max_tokens, ollama_url="x", ventana=None):
        llamadas.append(prompt)
        return "resumen parcial " * 50 if prompt.startswith("Este es el bloque") else "Nada con formato."

    monkeypatch.setattr(m.ollama_client, "generate", falso)
    parametros = {"ollama_model": "m", "ollama_max_tokens": 2048, "ollama_url": "u", "ollama_chunk_chars": 6000}
    monkeypatch.setattr(m.app_config, "get_param", lambda k: parametros[k])
    _, _, _, tarjetas = m.generate_study_material("Esto es una frase de clase. " * 4000, "X")
    assert tarjetas == []
    assert sum("tarjetas de estudio" in p for p in llamadas) == 2  # tope de dos intentos por sección


# --- La memoria de Ollama en un equipo modesto 24/7 -------------------------------------------------


def test_ollama_suelta_el_modelo_al_minuto_y_no_a_los_cinco(monkeypatch):
    enviados = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(cliente_ollama.requests, "post", lambda url, json, timeout: enviados.append(json) or Respuesta())
    cliente_ollama.generate("hola", model="m", max_tokens=10)
    assert enviados[0]["keep_alive"] == "60s"


@pytest.mark.parametrize(
    "modelo,libre,es_auto,esperado",
    [
        ("llama3.2:3b", 10.0, True, "llama3.2:3b"),  # cabe
        ("llama3.2:3b", 5.0, True, "llama3.2:3b"),  # justo lo que necesita: cabe
        ("llama3.2:3b", 3.0, True, "llama3.2:1b"),  # no cabe y lo eligió la aplicación: el liviano
        ("llama3.2:3b", 3.0, False, "llama3.2:3b"),  # lo eligió la persona: se respeta
        ("llama3.2:1b", 1.0, True, "llama3.2:1b"),  # ya es el liviano
        ("llama3.2:3b", None, True, "llama3.2:3b"),  # no se puede medir: no se cambia nada
        ("otro:70b", 3.0, True, "llama3.2:1b"),  # un modelo que no se conoce se supone grande
        ("otro:70b", 7.0, True, "otro:70b"),
    ],
)
def test_si_el_modelo_elegido_por_la_aplicacion_no_cabe_se_usa_el_liviano(monkeypatch, modelo, libre, es_auto, esperado):
    monkeypatch.setattr(m, "memoria_libre_gb", lambda: libre)
    assert m._modelo_que_cabe(modelo, es_auto) == esperado


def test_generate_study_material_elige_el_modelo_segun_la_memoria(monkeypatch):
    usados = []

    def falso(prompt, model, max_tokens, ollama_url="x", ventana=None):
        usados.append(model)
        return "##RESUMEN##\nr\n##PUNTOS_CLAVE##\n- p\n##HOJA_DE_REPASO##\nh\n##TARJETAS_ESTUDIO##\nP: a\nR: b"

    monkeypatch.setattr(m.ollama_client, "generate", falso)
    monkeypatch.setattr(m.hardware, "detect_gpu_vendor", lambda: "nvidia")  # con GPU, auto elegiría el de 3B
    monkeypatch.setattr(m, "memoria_libre_gb", lambda: 3.0)
    parametros = {"ollama_model": "auto", "ollama_max_tokens": 2048, "ollama_url": "u", "ollama_chunk_chars": 6000}
    monkeypatch.setattr(m.app_config, "get_param", lambda k: parametros[k])
    m.generate_study_material("Una clase corta.")
    assert usados == ["llama3.2:1b"]
