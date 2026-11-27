# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Ajustes del colegio que decide el UTP desde la aplicación (no un archivo de configuración): las fotos de la pizarra y el modelo
que escribe los resúmenes."""
import datetime
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nucleo import modelos_ia
from servicios import servicio_ajustes as sa
from servicios import servicio_grabacion as sg
from servicios import servicio_modelos as sm
from servicios import servicio_pizarra as sp
from test_clases import esc  # noqa: F401


@pytest.fixture(autouse=True)
def ollama(monkeypatch):
    """Ollama de mentira: responde, sin el modelo instalado, y no baja nada de verdad."""
    sm._descargas.clear()
    estado = {"instalado": False, "responde": True, "pedidos": []}
    monkeypatch.setattr(sm, "instalado", lambda modelo, url: (estado["instalado"] if estado["responde"] else None))
    monkeypatch.setattr(sm, "_correr", lambda modelo, url: estado["pedidos"].append((modelo, url)))
    monkeypatch.setattr(sm.threading, "Thread", type("H", (), {"__init__": lambda self, target, args=(), **k: setattr(self, "t", (target, args)), "start": lambda self: self.t[0](*self.t[1])}))
    monkeypatch.setattr("interfaz.api.rutas_ajustes.memoria_total_gb", lambda: 15.64)
    yield estado
    sm._descargas.clear()


def ver(cliente, headers):
    return cliente.get("/ajustes/fotos-pizarra", headers=headers)


def test_un_colegio_nuevo_las_tiene_apagadas_y_el_utp_ve_lo_que_necesita_para_decidir(cliente, esc):
    r = ver(cliente, esc["utp"])
    assert r.status_code == 200
    d = r.json()
    assert d["activada"] is False and d["modelo"] == sp.MODELO_VISION
    assert d["ollama_responde"] is True and d["modelo_instalado"] is False
    assert d["memoria_total_gb"] == 15.6 and d["memoria_recomendada_gb"] == sp.MEMORIA_RECOMENDADA_GB
    assert d["descarga"] is None


def test_el_utp_las_activa_y_las_desactiva_y_se_recuerda(cliente, esc):
    assert cliente.put("/ajustes/fotos-pizarra", json={"activada": True}, headers=esc["utp"]).json()["activada"] is True
    assert ver(cliente, esc["utp"]).json()["activada"] is True  # quedó guardado en la base, no en memoria
    assert cliente.put("/ajustes/fotos-pizarra", json={"activada": False}, headers=esc["utp"]).json()["activada"] is False
    assert ver(cliente, esc["utp"]).json()["activada"] is False


def test_solo_el_utp_puede_ver_y_cambiar_los_ajustes(cliente, esc):
    url, cuerpo = "/ajustes/fotos-pizarra", {"activada": True}
    assert cliente.get(url).status_code == 401
    for quien in ("ana", "alumno"):  # un profesor y un alumno
        assert ver(cliente, esc[quien]).status_code == 403
        assert cliente.put(url, json=cuerpo, headers=esc[quien]).status_code == 403
        assert cliente.post(url + "/modelo", headers=esc[quien]).status_code == 403
    assert ver(cliente, esc["utp"]).json()["activada"] is False  # nada cambió


def test_cada_colegio_decide_por_su_cuenta(cliente, esc, otro_colegio):
    cliente.put("/ajustes/fotos-pizarra", json={"activada": True}, headers=esc["utp"])
    assert ver(cliente, otro_colegio[1]).json()["activada"] is False
    assert ver(cliente, esc["utp"]).json()["activada"] is True


def test_el_ajuste_vive_en_el_colegio_y_la_funcion_lo_lee_de_ahi(cliente, esc):
    from infraestructura.modelos_orm import Colegio

    with cliente.sesion() as db:
        colegio = db.query(Colegio).first()
        assert sp.activadas(colegio) is False
        colegio.fotos_pizarra = True
        db.commit()
        assert sp.activadas(colegio) is True


def test_descargar_el_modelo_arranca_la_descarga_y_el_estado_la_muestra(cliente, esc, ollama):
    r = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert r.status_code == 200
    assert ollama["pedidos"] == [(sp.MODELO_VISION, sp.url_ollama())]
    assert r.json()["descarga"]["estado"] == "descargando"
    assert ver(cliente, esc["utp"]).json()["descarga"]["estado"] == "descargando"


def test_no_se_baja_dos_veces_ni_lo_que_ya_esta_instalado(cliente, esc, ollama):
    assert cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"]).status_code == 200
    segundo = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert segundo.status_code == 409 and "Ya se está descargando" in segundo.json()["detail"]
    sm._descargas.clear()
    ollama["instalado"] = True
    ya = cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"])
    assert ya.status_code == 409 and "ya está instalado" in ya.json()["detail"]
    assert ver(cliente, esc["utp"]).json()["modelo_instalado"] is True


def test_si_ollama_no_responde_el_estado_lo_dice_sin_fallar(cliente, esc, ollama):
    ollama["responde"] = False
    d = ver(cliente, esc["utp"]).json()
    assert d["ollama_responde"] is False and d["modelo_instalado"] is False


def test_si_no_se_puede_medir_la_memoria_no_se_inventa(cliente, esc, monkeypatch):
    monkeypatch.setattr("interfaz.api.rutas_ajustes.memoria_total_gb", lambda: None)
    assert ver(cliente, esc["utp"]).json()["memoria_total_gb"] is None


def test_pedir_la_descarga_le_pregunta_una_sola_vez_a_ollama(cliente, esc, monkeypatch):
    """Cada pregunta a un Ollama cerrado cuesta ~2 s en Windows: el botón no puede hacer dos."""
    preguntas = []
    monkeypatch.setattr(sm, "instalado", lambda modelo, url: preguntas.append(1) or False)
    assert cliente.post("/ajustes/fotos-pizarra/modelo", headers=esc["utp"]).status_code == 200
    assert preguntas == [1]


# --- El modelo que escribe los resúmenes: se baja desde la aplicación, sin consola ---

TEXTO, BAJAR_TEXTO = "/ajustes/modelo-texto", "/ajustes/modelo-texto/descargar"


def test_el_utp_ve_el_modelo_que_escribe_los_resumenes_y_lo_que_hace_falta(cliente, esc):
    d = cliente.get(TEXTO, headers=esc["utp"]).json()
    assert d["modelo"] == modelos_ia.MODELO_CPU
    assert d["ollama_responde"] is True and d["modelo_instalado"] is False
    assert d["memoria_total_gb"] == 15.6 and d["memoria_minima_gb"] == modelos_ia.MEMORIA_MINIMA_GB
    assert d["descarga"] is None and d["tamano_gb"] == 4.6


def test_si_quien_administra_el_servidor_fijo_un_modelo_se_ofrece_ese(cliente, esc, monkeypatch):
    monkeypatch.setattr("interfaz.api.rutas_ajustes.app_config.get_param", lambda k: "qwen2.5:7b")
    d = cliente.get(TEXTO, headers=esc["utp"]).json()
    assert d["modelo"] == "qwen2.5:7b" and d["tamano_gb"] is None  # de otro modelo no se sabe cuánto pesa


def test_el_utp_baja_el_modelo_de_resumenes_y_mientras_se_baja_no_se_pide_dos_veces(cliente, esc, ollama):
    r = cliente.post(BAJAR_TEXTO, headers=esc["utp"])
    assert r.status_code == 200 and r.json()["descarga"]["estado"] == "descargando"
    assert [m for m, _ in ollama["pedidos"]] == [modelos_ia.MODELO_CPU]
    assert cliente.post(BAJAR_TEXTO, headers=esc["utp"]).status_code == 409  # ya se está descargando
    assert cliente.get(TEXTO, headers=esc["utp"]).json()["descarga"]["estado"] == "descargando"


def test_si_el_modelo_ya_esta_instalado_no_se_vuelve_a_bajar(cliente, esc, ollama):
    ollama["instalado"] = True
    assert cliente.get(TEXTO, headers=esc["utp"]).json()["modelo_instalado"] is True
    assert cliente.post(BAJAR_TEXTO, headers=esc["utp"]).status_code == 409
    assert ollama["pedidos"] == []


def test_con_ollama_cerrado_igual_se_puede_pedir_porque_la_app_lo_abre_sola(cliente, esc, ollama):
    ollama["responde"] = False
    assert cliente.get(TEXTO, headers=esc["utp"]).json()["ollama_responde"] is False
    assert cliente.post(BAJAR_TEXTO, headers=esc["utp"]).status_code == 200


def test_solo_el_utp_ve_y_baja_el_modelo_de_resumenes(cliente, esc, ollama):
    assert cliente.get(TEXTO).status_code == 401 and cliente.post(BAJAR_TEXTO).status_code == 401
    for quien in ("ana", "alumno"):
        assert cliente.get(TEXTO, headers=esc[quien]).status_code == 403
        assert cliente.post(BAJAR_TEXTO, headers=esc[quien]).status_code == 403
    assert ollama["pedidos"] == []


def test_el_servidor_web_no_carga_pytorch_para_ofrecer_la_descarga():
    """`infraestructura.hardware` importa torch: si las rutas de ajustes lo arrastraran, el servidor web cargaría cientos de MB de más."""
    codigo = "import sys, interfaz.api.rutas_ajustes, servicios.servicio_estado; assert 'torch' not in sys.modules, 'se cargó torch'"
    r = subprocess.run([sys.executable, "-c", codigo], cwd=Path(__file__).resolve().parent.parent, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]


# --- Plazo de revisión y corte automático (por colegio) ---

CLASES = "/ajustes/clases"


def poner_clases(cliente, headers, horas, minutos):
    return cliente.put(CLASES, json={"horas_revision": horas, "minutos_corte": minutos}, headers=headers)


def test_sin_tocar_nada_valen_los_predeterminados_de_siempre(cliente, esc):
    d = cliente.get(CLASES, headers=esc["utp"]).json()
    assert (d["horas_revision"], d["minutos_corte"]) == (sa.HORAS_REVISION_POR_DEFECTO, sa.MINUTOS_CORTE_POR_DEFECTO)
    assert (d["horas_revision_por_defecto"], d["minutos_corte_por_defecto"]) == (sa.HORAS_REVISION_POR_DEFECTO, sa.MINUTOS_CORTE_POR_DEFECTO)
    assert d["rango_horas_revision"] == [1, 168] and d["rango_minutos_corte"] == [0, 120]


def test_el_utp_cambia_el_plazo_y_el_corte_se_recuerda_y_se_puede_volver_al_predeterminado(cliente, esc):
    d = poner_clases(cliente, esc["utp"], 48, 5).json()
    assert (d["horas_revision"], d["minutos_corte"]) == (48, 5)
    assert cliente.get(CLASES, headers=esc["utp"]).json()["minutos_corte"] == 5  # quedó en la base
    d = poner_clases(cliente, esc["utp"], None, None).json()
    assert (d["horas_revision"], d["minutos_corte"]) == (sa.HORAS_REVISION_POR_DEFECTO, sa.MINUTOS_CORTE_POR_DEFECTO)


def test_cero_minutos_de_corte_es_valido_y_cero_horas_de_revision_no(cliente, esc):
    assert poner_clases(cliente, esc["utp"], None, 0).json()["minutos_corte"] == 0  # se corta justo al terminar el bloque
    r = poner_clases(cliente, esc["utp"], 0, None)
    assert r.status_code == 422 and "Plazo de revisión" in r.json()["detail"]


@pytest.mark.parametrize("horas,minutos", [(0, 15), (169, 15), (-5, 15), (24, -1), (24, 121)])
def test_un_valor_fuera_de_rango_se_rechaza_con_un_motivo_y_no_se_guarda_nada(cliente, esc, horas, minutos):
    poner_clases(cliente, esc["utp"], 30, 10)
    r = poner_clases(cliente, esc["utp"], horas, minutos)
    assert r.status_code == 422 and "número entero" in r.json()["detail"]
    d = cliente.get(CLASES, headers=esc["utp"]).json()
    assert (d["horas_revision"], d["minutos_corte"]) == (30, 10)  # ni siquiera el que sí era válido


def test_los_numeros_con_formato_raro_dan_error_del_cliente_nunca_500(cliente, esc):
    for cuerpo in ({"horas_revision": "mucho", "minutos_corte": None}, {"horas_revision": 1.5, "minutos_corte": None}, {"horas_revision": None}, {}):
        assert cliente.put(CLASES, json=cuerpo, headers=esc["utp"]).status_code == 422


def test_cada_colegio_tiene_su_propio_plazo_y_corte(cliente, esc, otro_colegio):
    poner_clases(cliente, esc["utp"], 72, 30)
    d = cliente.get(CLASES, headers=otro_colegio[1]).json()
    assert (d["horas_revision"], d["minutos_corte"]) == (sa.HORAS_REVISION_POR_DEFECTO, sa.MINUTOS_CORTE_POR_DEFECTO)
    assert cliente.get(CLASES, headers=esc["utp"]).json()["horas_revision"] == 72


def test_el_corte_automatico_usa_los_minutos_del_colegio(cliente, esc):
    from infraestructura.modelos_orm import Bloque

    hoy = datetime.date(2026, 9, 28)

    def corte():
        with cliente.sesion() as db:
            return sg._corte_de(db.get(Bloque, esc["bloques"]["mat"]), hoy)

    con_el_predeterminado = corte()
    poner_clases(cliente, esc["utp"], None, 0)
    assert corte() == con_el_predeterminado - datetime.timedelta(minutes=sa.MINUTOS_CORTE_POR_DEFECTO)
    poner_clases(cliente, esc["utp"], None, 60)
    assert corte() == con_el_predeterminado + datetime.timedelta(minutes=60 - sa.MINUTOS_CORTE_POR_DEFECTO)


# --- Respaldo diario (de todo el servidor) ---

RESPALDOS = "/ajustes/respaldos"


def poner_respaldos(cliente, headers, carpeta, dias):
    return cliente.put(RESPALDOS, json={"carpeta": carpeta, "dias": dias}, headers=headers)


def test_sin_tocar_nada_el_respaldo_usa_la_variable_de_entorno_y_14_dias(cliente, esc, tmp_path, monkeypatch):
    monkeypatch.setenv("CARPETA_RESPALDOS", str(tmp_path / "del_entorno"))
    d = cliente.get(RESPALDOS, headers=esc["utp"]).json()
    assert d["carpeta"] == d["carpeta_por_defecto"] == str((tmp_path / "del_entorno").resolve())
    assert d["dias"] == d["dias_por_defecto"] == sa.DIAS_RESPALDO_POR_DEFECTO and d["rango_dias"] == [1, 365]


def test_el_utp_elige_la_carpeta_y_los_dias_y_se_recuerdan(cliente, esc, tmp_path):
    destino = tmp_path / "discoB"
    d = poner_respaldos(cliente, esc["utp"], str(destino), 30).json()
    assert d["carpeta"] == str(destino) and d["dias"] == 30
    assert destino.is_dir()  # se creó (un nivel) y se comprobó que se puede escribir
    assert list(destino.iterdir()) == []  # el archivo de prueba no queda
    d = cliente.get(RESPALDOS, headers=esc["utp"]).json()
    assert d["carpeta"] == str(destino) and d["dias"] == 30
    d = poner_respaldos(cliente, esc["utp"], None, None).json()  # de vuelta al predeterminado
    assert d["carpeta"] == d["carpeta_por_defecto"] and d["dias"] == sa.DIAS_RESPALDO_POR_DEFECTO


@pytest.mark.parametrize("dias", [0, 366, -3])
def test_los_dias_fuera_de_rango_se_rechazan_y_no_cambian_la_carpeta(cliente, esc, tmp_path, dias):
    antes = cliente.get(RESPALDOS, headers=esc["utp"]).json()["carpeta"]
    r = poner_respaldos(cliente, esc["utp"], str(tmp_path / "nueva"), dias)
    assert r.status_code == 422 and "Días de respaldo" in r.json()["detail"]
    assert cliente.get(RESPALDOS, headers=esc["utp"]).json()["carpeta"] == antes


def test_una_carpeta_que_no_sirve_se_rechaza_con_un_motivo_claro(cliente, esc, tmp_path):
    archivo = tmp_path / "un_archivo.txt"
    archivo.write_text("x")
    casos = {
        "": "ruta completa", "   ": "ruta completa", "relativa/respaldos": "ruta completa", "con\0nulo": "ruta completa",
        str(archivo): "archivo, no una carpeta",
        str(tmp_path / "no_existe" / "dentro"): "no existe",
        str(Path(tmp_path.anchor)): "raíz del disco",
    }
    for carpeta, motivo in casos.items():
        r = poner_respaldos(cliente, esc["utp"], carpeta.replace("\\0", "\0"), None)
        assert r.status_code == 422 and motivo in r.json()["detail"], (carpeta, r.json())


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="como administrador siempre se puede escribir")
def test_una_carpeta_donde_no_se_puede_escribir_se_rechaza_antes_de_guardarla(cliente, esc, tmp_path):
    cerrada = tmp_path / "cerrada"
    cerrada.mkdir()
    cerrada.chmod(0o500)
    try:
        r = poner_respaldos(cliente, esc["utp"], str(cerrada), None)
        assert r.status_code == 422 and "No se puede guardar nada" in r.json()["detail"]
    finally:
        cerrada.chmod(0o700)


def test_solo_el_utp_ve_y_cambia_los_ajustes_de_clases_y_de_respaldo(cliente, esc, tmp_path):
    for url, cuerpo in ((CLASES, {"horas_revision": 1, "minutos_corte": 1}), (RESPALDOS, {"carpeta": str(tmp_path / "x"), "dias": 5})):
        assert cliente.get(url).status_code == 401 and cliente.put(url, json=cuerpo).status_code == 401
        for quien in ("ana", "alumno"):
            assert cliente.get(url, headers=esc[quien]).status_code == 403
            assert cliente.put(url, json=cuerpo, headers=esc[quien]).status_code == 403
    assert not (tmp_path / "x").exists()  # un rechazo no deja carpetas creadas
    assert cliente.get(CLASES, headers=esc["utp"]).json()["horas_revision"] == sa.HORAS_REVISION_POR_DEFECTO
