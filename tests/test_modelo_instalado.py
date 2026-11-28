# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""El resumen se escribe siempre con un modelo que esté descargado. Un resumen con otro de los modelos de la aplicación es mejor que una clase sin resumen.
Lo encontró una prueba real: en un equipo con GPU el modo automático pide `llama3.2:3b`, y si el colegio solo descargó el `gemma4:e2b` que le ofrecía
la pantalla, todas las clases fallaban y el panel «Estado» decía que estaba todo bien."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infraestructura.modelos_orm import Base
from nucleo import modelos_ia
from servicios import servicio_ajustes, servicio_estado as se
from servicios import servicio_material_estudio as m
from servicios import servicio_modelos as sm

GEMMA, LLAMA3, LLAMA1 = modelos_ia.MODELO_CPU, modelos_ia.MODELO_GPU, modelos_ia.MODELO_MINIMO


@pytest.fixture()
def equipo(monkeypatch):
    """Un equipo con memoria de sobra, sin lo que eligió el UTP y con `ollama_model` en automático; devuelve cómo ponerle modelos instalados y GPU."""
    monkeypatch.setattr(m, "memoria_libre_gb", lambda: 64.0)
    monkeypatch.delenv(modelos_ia.VARIABLE_DEL_TRABAJADOR, raising=False)
    monkeypatch.delenv("OLLAMA_DISPOSITIVO", raising=False)
    monkeypatch.setattr("nucleo.configuracion.get_param", lambda k: "auto")

    def poner(instalados, gpu=False):
        monkeypatch.setattr(m, "_modelos_instalados", lambda url: None if instalados is None else set(instalados))
        monkeypatch.setattr(m.hardware, "detect_gpu_vendor", lambda: "nvidia" if gpu else "none")

    return poner


def test_sin_gpu_el_automatico_es_gemma_si_esta_instalado(equipo):
    equipo({GEMMA, LLAMA3, LLAMA1})
    assert m._modelo_a_usar("u") == GEMMA


def test_con_gpu_el_automatico_es_llama_3b_si_esta_instalado(equipo):
    equipo({GEMMA, LLAMA3, LLAMA1}, gpu=True)
    assert m._modelo_a_usar("u") == LLAMA3


def test_con_gpu_y_solo_gemma_instalado_se_resume_con_gemma_en_vez_de_fallar(equipo, capsys):
    equipo({GEMMA}, gpu=True)  # lo que la pantalla le dijo al colegio que descargara
    assert m._modelo_a_usar("u") == GEMMA
    assert "no está instalado: se usa gemma4:e2b" in capsys.readouterr().out


def test_sin_gpu_y_solo_el_liviano_instalado_se_resume_con_el_liviano(equipo):
    equipo({LLAMA1})
    assert m._modelo_a_usar("u") == LLAMA1


def test_si_no_hay_ninguno_de_la_aplicacion_se_deja_el_que_corresponde_y_falla_con_su_motivo(equipo):
    equipo({"otro:7b"}, gpu=True)
    assert m._modelo_a_usar("u") == LLAMA3


def test_con_ollama_cerrado_no_se_puede_saber_y_se_deja_el_que_corresponde(equipo):
    equipo(None, gpu=True)
    assert m._modelo_a_usar("u") == LLAMA3


def test_lo_que_eligio_el_utp_se_usa_si_esta_instalado(equipo, monkeypatch):
    equipo({GEMMA, LLAMA1})
    monkeypatch.setenv(modelos_ia.VARIABLE_DEL_TRABAJADOR, LLAMA1)
    assert m._modelo_a_usar("u") == LLAMA1


def test_si_lo_que_eligio_el_utp_desaparecio_se_usa_el_automatico_y_se_avisa(equipo, monkeypatch, capsys):
    equipo({GEMMA})
    monkeypatch.setenv(modelos_ia.VARIABLE_DEL_TRABAJADOR, LLAMA1)
    assert m._modelo_a_usar("u") == GEMMA
    assert "elegido en «Ajustes» (llama3.2:1b) no está instalado" in capsys.readouterr().out


def test_con_ollama_cerrado_lo_que_eligio_el_utp_se_respeta(equipo, monkeypatch):
    equipo(None)
    monkeypatch.setenv(modelos_ia.VARIABLE_DEL_TRABAJADOR, LLAMA1)
    assert m._modelo_a_usar("u") == LLAMA1


def test_un_modelo_fijado_por_quien_administra_el_servidor_se_respeta_aunque_no_este(equipo, monkeypatch):
    equipo({GEMMA})
    monkeypatch.setattr("nucleo.configuracion.get_param", lambda k: "qwen2.5:7b")
    assert m._modelo_a_usar("u") == "qwen2.5:7b"  # no se cambia a escondidas lo que fijó un administrador


# --- El panel «Estado» ------------------------------------------------------------------------------------------------------------------


def _db():
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    return Session(motor)


@pytest.fixture()
def ollama_con(monkeypatch):
    def poner(instalados):
        monkeypatch.setattr(sm, "modelos_instalados", lambda url: None if instalados is None else set(instalados))

    return poner


def test_el_panel_dice_con_cual_se_resume_mientras_falta_el_modelo_automatico(ollama_con):
    ollama_con({LLAMA1})
    o = se._ollama(_db())
    assert o["modelo_texto_instalado"] is False and o["modelo_de_respaldo"] == LLAMA1


def test_el_panel_no_propone_respaldo_para_un_modelo_fijado_por_quien_administra_el_servidor(ollama_con, monkeypatch):
    ollama_con({GEMMA})
    monkeypatch.setattr("nucleo.configuracion.get_param", lambda k: "qwen2.5:7b")
    o = se._ollama(_db())
    assert o["modelo_texto_instalado"] is False and o["modelo_de_respaldo"] is None  # sin él no hay resumen


def test_el_panel_propone_respaldo_si_falta_lo_que_eligio_el_utp(ollama_con, monkeypatch):
    db = _db()
    ollama_con({GEMMA, LLAMA1})
    servicio_ajustes.cambiar_modelo_de_resumen(db, LLAMA1, True)
    ollama_con({GEMMA})  # el elegido se desinstaló
    o = se._ollama(db)
    assert o["modelo_texto"] == LLAMA1 and o["modelo_texto_instalado"] is False and o["modelo_de_respaldo"] == GEMMA


def test_con_el_modelo_instalado_no_hay_respaldo_ni_alerta(ollama_con):
    ollama_con({GEMMA})
    assert se._ollama(_db())["modelo_de_respaldo"] is None
