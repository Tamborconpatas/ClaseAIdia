"""Material de estudio de una clase larga: la ventana de contexto de Ollama y la condensación por niveles.
(Salió de una clase real de 92 minutos: el prompt final no cabía en la ventana por defecto, Ollama le recortaba las
instrucciones y el material salía sin hoja de repaso ni tarjetas.)"""
from infraestructura import cliente_ollama
from servicios import servicio_material_estudio as m


def test_la_ventana_crece_con_el_prompt_y_tiene_minimo_y_tope():
    assert cliente_ollama.ventana_necesaria("hola", 512) == 4096  # mínimo
    prompt_de_clase_real = "x" * 20_825  # el que falló con la clase de 92 min
    v = cliente_ollama.ventana_necesaria(prompt_de_clase_real, 2048)
    assert v > 20_825 // 3 + 2048  # cabe el prompt y la respuesta
    assert v % 1024 == 0 and v <= 16384
    assert cliente_ollama.ventana_necesaria("x" * 500_000, 2048) == 16384  # tope


def test_el_cliente_le_pide_a_ollama_esa_ventana(monkeypatch):
    enviados = []

    class Respuesta:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(cliente_ollama.requests, "post", lambda url, json, timeout: enviados.append(json) or Respuesta())
    cliente_ollama.generate("x" * 20_825, model="m", max_tokens=2048)
    assert enviados[0]["options"]["num_ctx"] == cliente_ollama.ventana_necesaria("x" * 20_825, 2048)
    assert enviados[0]["options"]["num_predict"] == 2048


def _con_modelo_falso(monkeypatch, tamano_de_cada_resumen):
    llamadas = []

    def falso(prompt, model, max_tokens, ollama_url="x"):
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


def test_una_clase_larga_llega_a_la_pasada_final_con_lo_que_cabe(monkeypatch):
    """Lo que falló: la pasada final recibía ~20 mil caracteres + instrucciones sin que cupieran."""
    prompts = []

    def falso(prompt, model, max_tokens, ollama_url="x"):
        prompts.append(prompt)
        if "bloque" in prompt[:80].lower():
            return "resumen parcial " * 120
        return "##RESUMEN##\nr\n##PUNTOS_CLAVE##\n- p\n##HOJA_DE_REPASO##\nh\n##TARJETAS_ESTUDIO##\nP: a\nR: b"

    monkeypatch.setattr(m.ollama_client, "generate", falso)
    parametros = {"ollama_model": "m", "ollama_max_tokens": 2048, "ollama_url": "u", "ollama_chunk_chars": 6000}
    monkeypatch.setattr(m.app_config, "get_param", lambda k: parametros[k])
    resumen, puntos, hoja, tarjetas = m.generate_study_material("Esto es una frase de clase. " * 4000)  # ~110 mil caracteres
    assert hoja and tarjetas == [{"pregunta": "a", "respuesta": "b"}]
    assert len(prompts[-1]) < m._MAX_CARACTERES_FINAL + 3000  # instrucciones + material condensado


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
