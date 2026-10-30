# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Un disco lleno corrompe la base y pierde clases: con poco espacio no se empieza a grabar, no se acepta más audio y no se procesa."""
import os
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from infraestructura.modelos_orm import EstadoGrabacion as E, Grabacion
from nucleo import disco
from servicios import servicio_estado as se
from servicios import servicio_grabacion as sg
from test_grabaciones import EQUIPO_A, _comando, _crear, _en_curso, _estado, _terminar_con_audio, _trozo, g, tiempo  # noqa: F401
from test_trabajador import _con_hijo, _estado as _estado_de, sesion_procesando  # noqa: F401


ESPACIO_LIBRE_REAL = sg.espacio_libre_gb  # conftest lo reemplaza en cada test por un disco con espacio


def con_espacio(monkeypatch, gb):
    monkeypatch.setattr(sg, "espacio_libre_gb", lambda: gb)


# --- Medir el disco ----------------------------------------------------------------------------


def test_una_carpeta_que_aun_no_existe_se_mide_en_el_disco_de_su_padre(tmp_path):
    assert disco.ancestro_existente(tmp_path / "audio" / "1" / "mas") == tmp_path.resolve()
    assert disco.ancestro_existente(tmp_path) == tmp_path.resolve()


def test_el_espacio_en_disco_es_libre_y_total_en_gb(tmp_path):
    libre, total = disco.espacio_en_disco(tmp_path / "no_existe_todavia")
    uso = shutil.disk_usage(tmp_path)
    assert abs(libre - uso.free / 1e9) < 0.5 and abs(total - uso.total / 1e9) < 0.5 and 0 < libre <= total


def test_si_no_se_puede_medir_no_se_bloquea_nada(tmp_path, monkeypatch):
    def falla(ruta):
        raise OSError("disco desconectado")

    monkeypatch.setattr(disco.shutil, "disk_usage", falla)
    assert disco.espacio_en_disco(tmp_path) == (float("inf"), float("inf"))


@pytest.mark.skipif(os.name != "nt", reason="las letras de unidad son de Windows")
def test_un_disco_que_no_existe_se_da_por_desconocido_en_vez_de_girar_para_siempre():
    """Una unidad externa desconectada (donde podrían estar los respaldos): no hay carpeta por encima que exista."""
    libre = next(f"{c}:/" for c in reversed(string.ascii_uppercase) if not Path(f"{c}:/").exists())
    assert disco.ancestro_existente(Path(libre) / "respaldos" / "x") is None
    assert disco.espacio_en_disco(Path(libre) / "respaldos") == (float("inf"), float("inf"))


def test_el_espacio_libre_que_mira_el_servicio_es_el_del_disco_del_audio(tmp_path, monkeypatch):
    medidos = []
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    monkeypatch.setattr(sg, "espacio_en_disco", lambda ruta: medidos.append(ruta) or (12.0, 99.0))
    assert ESPACIO_LIBRE_REAL() == 12.0  # lo libre, no lo total
    assert medidos == [tmp_path / "audio"]


# --- No se empieza a grabar sin espacio ------------------------------------------------------------


def test_con_poco_espacio_no_se_puede_empezar_a_grabar_y_se_dice_por_que(g, monkeypatch):
    con_espacio(monkeypatch, 1.9)
    r = _crear(g)
    assert r.status_code == 409 and "casi no tiene espacio libre (1.9 GB)" in r.json()["detail"] and "Avisa al UTP" in r.json()["detail"]
    hoy = g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]
    assert hoy["puede_grabar"] is False and "casi no tiene espacio" in hoy["motivo"] and hoy["grabacion"] is None  # no se creó nada


def test_el_borde_del_espacio_minimo_para_grabar(g, monkeypatch):
    con_espacio(monkeypatch, sg.DISCO_MINIMO_PARA_GRABAR_GB)
    assert _crear(g).status_code == 201  # justo en el mínimo se puede
    assert sg.DISCO_MINIMO_PARA_GRABAR_GB == 2.0


def test_el_horario_manda_sobre_el_disco_en_el_motivo(g, monkeypatch):
    con_espacio(monkeypatch, 0.1)
    r = _crear(g, bloque="bloque_martes")  # no es de hoy
    assert r.status_code == 409 and "no es de hoy" in r.json()["detail"]


def test_una_grabacion_en_curso_sigue_cuando_el_disco_se_llena(g, monkeypatch):
    gid = _en_curso(g)
    con_espacio(monkeypatch, 0.5)  # por debajo del mínimo para empezar, pero aún sobre el de seguir subiendo
    hoy = g["c"].get("/grabaciones/hoy", headers=g["ana"]).json()[0]
    assert hoy["puede_grabar"] is True  # una sesión en curso siempre se puede retomar
    assert _trozo(g, gid, 0).status_code == 200
    assert _comando(g, gid, "terminar").status_code == 200


# --- No se acepta más audio con el disco al límite ---------------------------------------------------


def test_con_el_disco_al_limite_el_audio_se_rechaza_con_507_y_se_acepta_al_volver_el_espacio(g, monkeypatch):
    gid = _en_curso(g)
    con_espacio(monkeypatch, 0.29)
    r = _trozo(g, gid, 0)
    assert r.status_code == 507 and "disco del servidor está lleno" in r.json()["detail"]
    assert _estado(g, gid)["trozos"] == 0  # no se guardó nada
    con_espacio(monkeypatch, 0.3)  # el UTP liberó espacio: el mismo trozo, reintentado por el equipo grabador, entra
    assert _trozo(g, gid, 0).status_code == 200
    assert _estado(g, gid)["trozos"] == 1


def test_un_trozo_malo_se_rechaza_por_lo_suyo_aunque_haya_poco_disco(g, monkeypatch):
    gid = _en_curso(g)
    con_espacio(monkeypatch, 0.1)
    assert _trozo(g, gid, 0, datos=b"no es audio").status_code == 415  # el motivo real, no el disco


# --- No se procesa sin espacio -----------------------------------------------------------------------


def test_sin_espacio_para_procesar_se_reintenta_mas_tarde_y_el_audio_se_conserva(sesion_procesando, monkeypatch):
    con_espacio(monkeypatch, 0.9)
    monkeypatch.setattr(sg, "esperar_memoria", lambda *a, **k: True)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía lanzar el trabajador")))
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    estado, error = _estado_de(sesion_procesando)
    assert estado == E.ERROR and "casi no tiene espacio libre (0.9 GB)" in error and "Se reintentará sola" in error
    assert (sesion_procesando["carpeta"] / "000000.parte").exists()  # el reintento lo necesita
    with sesion_procesando["fabrica"]() as db:
        assert db.get(Grabacion, sesion_procesando["id"]).reintento_en is not None


def test_con_el_espacio_justo_si_se_procesa(sesion_procesando, monkeypatch):
    con_espacio(monkeypatch, sg.DISCO_MINIMO_PARA_PROCESAR_GB)
    _con_hijo(monkeypatch, "import sys; sys.exit(0)")
    sg._trabajar_aparte("clase", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert _estado_de(sesion_procesando)[0] == E.PROCESANDO  # el hijo de mentira no deja resultado, pero se lanzó (no hubo error de disco)


def test_regenerar_solo_el_material_no_exige_disco(sesion_procesando, monkeypatch):
    con_espacio(monkeypatch, 0.0)
    _con_hijo(monkeypatch, "import sys; sys.exit(0)")
    sg._trabajar_aparte("generacion", sesion_procesando["id"], sesion_procesando["fabrica"])
    assert "espacio" not in (_estado_de(sesion_procesando)[1] or "")


# --- El panel habla del mismo disco y del mismo número --------------------------------------------------


def test_el_panel_avisa_con_el_mismo_numero_con_que_se_bloquea_y_mide_el_disco_del_audio(tmp_path, monkeypatch):
    assert se.DISCO_CRITICO_GB == sg.DISCO_MINIMO_PARA_GRABAR_GB
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    medidos = []
    monkeypatch.setattr(se, "espacio_en_disco", lambda ruta: medidos.append(ruta) or (12.3, 100.0))
    d = se._disco()
    assert medidos == [tmp_path / "audio"] and (d["libre_gb"], d["total_gb"]) == (12.3, 100.0)
