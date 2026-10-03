"""Panel de estado del UTP: qué se procesa, qué falló y si el equipo está sano. Las alertas ya vienen en palabras de persona."""
import datetime
import os
import types

import pytest

from infraestructura.modelos_orm import Clase, EstadoGrabacion as E, Grabacion
from servicios import servicio_estado as se
from servicios import servicio_grabacion as sg
from servicios import servicio_modelos as sm
from test_clases import _clase, esc  # noqa: F401


def sano(**cambios):
    """Un servidor sin ningún problema; cada test cambia solo lo que quiere probar."""
    e = {
        "procesamiento": {"en_vivo": [], "procesando": [], "con_reintento": [], "con_error": [], "terminadas_24h": 0},
        "ollama": {"responde": True, "modelo_texto": "llama3.2:3b", "modelo_texto_instalado": True},
        "disco": {"libre_gb": 100.0, "total_gb": 500.0, "audio_temporal_mb": 0, "fotos_temporales_mb": 0, "base_de_datos_mb": 3.0},
        "respaldos": {"carpeta": "r", "cantidad": 3, "mb": 9.0, "ultimo": datetime.date.today(), "hace_dias": 0, "en_el_mismo_disco": False},
        "memoria": {"total_gb": 16.0, "libre_gb": 8.0},
        "vigilancia": {"ultima_pasada": None, "activa": True},
    }
    for clave, valor in cambios.items():
        e[clave] = {**e[clave], **valor}
    return e


def test_un_servidor_sano_no_avisa_nada():
    assert se.construir_alertas(sano()) == []


# (qué cambia, nivel esperado, algo que el aviso debe decir). Los bordes están a ambos lados de cada umbral.
CASOS = [
    ({"disco": {"libre_gb": 5.0}}, None, None),
    ({"disco": {"libre_gb": 4.9}}, "aviso", "4.9 GB libres"),
    ({"disco": {"libre_gb": 2.0}}, "aviso", "2.0 GB libres"),
    ({"disco": {"libre_gb": 1.9}}, "critico", "1.9 GB libres"),
    ({"disco": {"audio_temporal_mb": 1500}}, None, None),
    ({"disco": {"audio_temporal_mb": 2000}}, "aviso", "2.0 GB de audio"),
    ({"disco": {"audio_temporal_mb": 2000}, "procesamiento": {"procesando": [{}]}}, None, None),  # lo está usando una clase
    ({"disco": {"audio_temporal_mb": 2000}, "procesamiento": {"en_vivo": [{}]}}, None, None),
    ({"disco": {"audio_temporal_mb": 2000}, "procesamiento": {"con_reintento": [{}]}}, None, None),
    ({"ollama": {"responde": False, "modelo_texto_instalado": False}}, "aviso", "Ollama) no responde"),
    ({"ollama": {"modelo_texto_instalado": False}}, "critico", "Falta el modelo que escribe los resúmenes (llama3.2:3b)"),
    ({"respaldos": {"cantidad": 0, "ultimo": None, "hace_dias": None}}, "aviso", "ningún respaldo"),
    ({"respaldos": {"hace_dias": 2}}, None, None),
    ({"respaldos": {"hace_dias": 3}}, "critico", "hace 3 días"),
    ({"respaldos": {"en_el_mismo_disco": True}}, "aviso", "mismo disco que la base de datos"),
    ({"respaldos": {"en_el_mismo_disco": None}}, None, None),  # no se pudo saber: no se acusa
    ({"memoria": {"libre_gb": 1.5}}, None, None),
    ({"memoria": {"libre_gb": 1.4}}, "aviso", "1.4 GB"),
    ({"memoria": {"libre_gb": None, "total_gb": None}}, None, None),
    ({"vigilancia": {"activa": False}}, "critico", "vigilancia automática no responde"),
    ({"vigilancia": {"activa": None}}, None, None),  # apagada en este servidor (pruebas): no hay latido que exigir
    ({"procesamiento": {"con_error": [{}]}}, "critico", "1 clase con error sin reintento"),
    ({"procesamiento": {"con_error": [{}, {}]}}, "critico", "2 clases con error sin reintento"),
]


@pytest.mark.parametrize("cambios,nivel,texto", CASOS)
def test_cada_problema_da_su_aviso_en_palabras_de_persona(cambios, nivel, texto):
    alertas = se.construir_alertas(sano(**cambios))
    if nivel is None:
        assert alertas == []
    else:
        assert [a["nivel"] for a in alertas] == [nivel]
        assert texto in alertas[0]["texto"]
        seccion = next(iter(cambios))  # el aviso apunta a la parte del panel que cambió
        assert alertas[0]["tema"] == {"procesamiento": "clases"}.get(seccion, seccion)


def test_varios_problemas_dan_varios_avisos_a_la_vez():
    alertas = se.construir_alertas(sano(disco={"libre_gb": 1.0}, ollama={"responde": False}, vigilancia={"activa": False}))
    assert sorted(a["nivel"] for a in alertas) == ["aviso", "critico", "critico"]


def test_lo_urgente_va_primero_y_dentro_de_cada_nivel_se_respeta_el_orden():
    alertas = se.construir_alertas(sano(disco={"libre_gb": 4.0}, respaldos={"en_el_mismo_disco": True}, ollama={"modelo_texto_instalado": False}, vigilancia={"activa": False}))
    assert [(a["nivel"], a["tema"]) for a in alertas] == [("critico", "ollama"), ("critico", "vigilancia"), ("aviso", "disco"), ("aviso", "respaldos")]


def test_la_carpeta_de_respaldos_se_muestra_completa_y_con_su_ultimo_respaldo(tmp_path, monkeypatch):
    carpeta = tmp_path / "copias"
    carpeta.mkdir()
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    (carpeta / f"escuela-{ayer}.db").write_bytes(b"x" * 1000)
    monkeypatch.setenv("CARPETA_RESPALDOS", str(carpeta))
    monkeypatch.chdir(tmp_path)  # un nombre relativo no le dice nada al UTP: se muestra la ruta completa
    d = se._respaldos()
    assert d["carpeta"] == str(carpeta.resolve())
    monkeypatch.setenv("CARPETA_RESPALDOS", "copias")
    assert se._respaldos()["carpeta"] == str(carpeta.resolve()) and os.path.isabs(se._respaldos()["carpeta"])
    assert (d["cantidad"], d["ultimo"], d["hace_dias"]) == (1, ayer, 1)


def test_ollama_apagado_no_se_confunde_con_modelo_faltante():
    # si no responde no se sabe si el modelo está: un solo aviso, no dos
    alertas = se.construir_alertas(sano(ollama={"responde": False, "modelo_texto_instalado": False}))
    assert len(alertas) == 1


# --- piezas sueltas --------------------------------------------------------------------------------


def test_modelo_de_texto_en_auto_acepta_el_1b_o_el_3b_y_uno_configurado_solo_ese(monkeypatch):
    monkeypatch.setattr(se.app_config, "get_param", lambda k: "auto")
    monkeypatch.setattr(sm, "modelos_instalados", lambda url: {"llama3.2:1b"})
    assert se._ollama() == {"responde": True, "modelo_texto": "llama3.2:1b o llama3.2:3b", "modelo_texto_instalado": True}
    monkeypatch.setattr(se.app_config, "get_param", lambda k: "qwen3:8b")
    d = se._ollama()
    assert d["modelo_texto"] == "qwen3:8b" and d["modelo_texto_instalado"] is False  # el 1b instalado no cuenta
    monkeypatch.setattr(sm, "modelos_instalados", lambda url: None)
    assert se._ollama()["responde"] is False and se._ollama()["modelo_texto_instalado"] is False


def test_misma_unidad(tmp_path, monkeypatch):
    (tmp_path / "base.db").write_text("x")
    assert se._misma_unidad(tmp_path / "respaldos" / "que" / "no" / "existe", tmp_path / "base.db") is True  # sube hasta lo que exista
    real = os.stat
    monkeypatch.setattr(se.os, "stat", lambda p, *a, **k: types.SimpleNamespace(st_dev=real(p, *a, **k).st_dev + (1 if "externo" in str(p) else 0)))
    (tmp_path / "externo").mkdir()
    assert se._misma_unidad(tmp_path / "externo", tmp_path / "base.db") is False


def test_el_audio_y_las_fotos_se_miden_en_mb(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "a.webm").write_bytes(b"x" * 2_000_000)
    (tmp_path / "2.bin").write_bytes(b"x" * 500_000)
    assert se._mb(tmp_path) == 2.5
    assert se._mb(tmp_path / "2.bin") == 0.5
    assert se._mb(tmp_path / "no_existe") == 0.0


# --- la ruta ---------------------------------------------------------------------------------------


@pytest.fixture()
def equipo(monkeypatch, tmp_path):
    """El equipo del colegio, sano: Ollama con su modelo, disco y respaldos al día, memoria de sobra."""
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    monkeypatch.setattr(se.app_config, "get_param", lambda k: "auto")
    monkeypatch.setattr(sm, "modelos_instalados", lambda url: {"llama3.2:3b"})
    monkeypatch.setattr(se, "_disco", lambda: sano()["disco"])
    monkeypatch.setattr(se, "_respaldos", lambda: sano()["respaldos"])
    monkeypatch.setattr(se, "memoria_total_gb", lambda: 15.64)
    monkeypatch.setattr(se, "memoria_libre_gb", lambda: 9.26)


def _grabacion(db, clase_id, estado, **campos):
    ahora = datetime.datetime.now()
    db.add(Grabacion(clase_id=clase_id, estado=estado, corte_en=ahora + datetime.timedelta(hours=1), **campos))


def ver(cliente, headers):
    return cliente.get("/estado", headers=headers)


def test_solo_el_utp_ve_el_estado_del_servidor(cliente, esc, equipo):
    assert cliente.get("/estado").status_code == 401
    for quien in ("ana", "alumno"):
        assert ver(cliente, esc[quien]).status_code == 403
    assert ver(cliente, esc["utp"]).status_code == 200


def test_un_servidor_sano_y_ocioso_se_ve_asi(cliente, esc, equipo):
    d = ver(cliente, esc["utp"]).json()
    assert d["alertas"] == []
    assert d["procesamiento"] == {"en_vivo": [], "procesando": [], "con_reintento": [], "con_error": [], "terminadas_24h": 0}
    assert d["ollama"] == {"responde": True, "modelo_texto": "llama3.2:1b o llama3.2:3b", "modelo_texto_instalado": True}
    assert d["memoria"] == {"total_gb": 15.6, "libre_gb": 9.3}
    assert d["vigilancia"]["activa"] is None  # el servidor de pruebas no enciende la vigilancia
    assert d["generado_en"].endswith(("Z", "+00:00"))


def test_cada_clase_aparece_en_su_grupo_con_el_curso_y_la_asignatura(cliente, esc, equipo):
    i = esc["ids"]
    ahora = sg.ahora_utc()
    with cliente.sesion() as db:
        extra_error = _clase(db, esc["bloques"]["mat"], 20)
        extra_lista = _clase(db, esc["bloques"]["mat"], 21)
        extra_antigua = _clase(db, esc["bloques"]["mat"], 40)  # el plazo más cercano de las que esperan
        extra_urgente = _clase(db, esc["bloques"]["mat"], 3)
        db.get(Clase, extra_urgente).prioritaria = True  # el profesor la marcó: pasa por delante de todas
        db.get(Clase, i["por_aprobar"]).prioritaria = True  # esta ya está en marcha: el aviso lo dice igual
        _grabacion(db, i["publicada"], E.GRABANDO)
        _grabacion(db, i["por_aprobar"], E.PROCESANDO, iniciada_en=ahora - datetime.timedelta(minutes=7, seconds=5))  # ya la tomó un trabajador
        _grabacion(db, i["procesando"], E.PROCESANDO)  # esperan su turno
        _grabacion(db, extra_antigua, E.PROCESANDO)
        _grabacion(db, extra_urgente, E.PROCESANDO)
        _grabacion(db, i["publicada_8b"], E.ERROR, intentos=1, reintento_en=ahora + datetime.timedelta(minutes=15), error="Ollama apagado")
        _grabacion(db, extra_error, E.ERROR, error="No se oyó voz")
        _grabacion(db, extra_lista, E.TERMINADA)
        db.commit()

    p = ver(cliente, esc["utp"]).json()["procesamiento"]
    assert [(c["clase_id"], c["estado"], c["curso"], c["asignatura"]) for c in p["en_vivo"]] == [(i["publicada"], "grabando", "8A", "Matemática")]
    # primero la que ya está en marcha, luego la cola en el orden en que se va a procesar
    assert [(c["clase_id"], c["turno"], c["minutos"], c["posicion"], c["prioritaria"]) for c in p["procesando"]] == [
        (i["por_aprobar"], "ahora", 7, None, True),
        (extra_urgente, "espera", None, 1, True),
        (extra_antigua, "espera", None, 2, False),
        (i["procesando"], "espera", None, 3, False),
    ]
    assert [(c["clase_id"], c["intentos"], c["error"], c["curso"], c["asignatura"]) for c in p["con_reintento"]] == [(i["publicada_8b"], 2, "Ollama apagado", "8B", "Historia")]
    assert p["con_reintento"][0]["reintento_en"].endswith(("Z", "+00:00"))
    assert [(c["clase_id"], c["error"]) for c in p["con_error"]] == [(extra_error, "No se oyó voz")]
    assert p["terminadas_24h"] == 1


def test_una_terminada_de_hace_mas_de_un_dia_ya_no_cuenta(cliente, esc, equipo):
    with cliente.sesion() as db:
        vieja, reciente = _clase(db, esc["bloques"]["mat"], 30), _clase(db, esc["bloques"]["mat"], 31)
        _grabacion(db, vieja, E.TERMINADA, creada_en=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=25))
        _grabacion(db, reciente, E.TERMINADA, creada_en=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=23))
        db.commit()
    assert ver(cliente, esc["utp"]).json()["procesamiento"]["terminadas_24h"] == 1


def test_un_utp_no_ve_las_clases_de_otro_colegio(cliente, esc, equipo, otro_colegio):
    with cliente.sesion() as db:
        _grabacion(db, esc["ids"]["publicada"], E.GRABANDO)
        _grabacion(db, esc["ids"]["por_aprobar"], E.ERROR, error="x")
        _grabacion(db, esc["ids"]["procesando"], E.TERMINADA)
        db.commit()
    mio = ver(cliente, esc["utp"]).json()["procesamiento"]
    assert (len(mio["en_vivo"]), len(mio["con_error"]), mio["terminadas_24h"]) == (1, 1, 1)
    ajeno = ver(cliente, otro_colegio[1]).json()
    assert ajeno["procesamiento"] == {"en_vivo": [], "procesando": [], "con_reintento": [], "con_error": [], "terminadas_24h": 0}
    assert ajeno["alertas"] == []  # tampoco le llega el aviso de un error que no es suyo


def test_una_clase_con_error_sin_reintento_enciende_la_alerta_critica(cliente, esc, equipo):
    with cliente.sesion() as db:
        _grabacion(db, esc["ids"]["por_aprobar"], E.ERROR, error="No se oyó voz")
        db.commit()
    alertas = ver(cliente, esc["utp"]).json()["alertas"]
    assert [a["nivel"] for a in alertas] == ["critico"] and "1 clase con error" in alertas[0]["texto"]


def test_una_clase_con_reintento_programado_no_es_alerta(cliente, esc, equipo):
    with cliente.sesion() as db:
        _grabacion(db, esc["ids"]["por_aprobar"], E.ERROR, error="Ollama apagado", reintento_en=sg.ahora_utc() + datetime.timedelta(minutes=5))
        db.commit()
    assert ver(cliente, esc["utp"]).json()["alertas"] == []  # se arregla sola: no se alarma a nadie


def test_las_alertas_llegan_por_la_ruta(cliente, esc, equipo, monkeypatch):
    monkeypatch.setattr(se, "_disco", lambda: sano(disco={"libre_gb": 1.2})["disco"])
    monkeypatch.setattr(sm, "modelos_instalados", lambda url: None)
    alertas = ver(cliente, esc["utp"]).json()["alertas"]
    assert sorted(a["nivel"] for a in alertas) == ["aviso", "critico"]


# --- el latido de la vigilancia -----------------------------------------------------------------


def _estado(cliente, esc, vigilando):
    with cliente.sesion() as db:
        return se.estado_del_servidor(db, 1, vigilando=vigilando)["vigilancia"]


def test_el_latido_se_renueva_en_cada_pasada_de_la_vigilancia(cliente, equipo, monkeypatch):
    monkeypatch.setattr(sg, "ultima_vigilancia", None)
    with cliente.sesion() as db:
        sg.vigilar(db, cliente.sesion)
    assert sg.ultima_vigilancia is not None
    assert (sg.ahora_utc() - sg.ultima_vigilancia).total_seconds() < 5


def test_si_la_pasada_falla_a_medias_el_latido_no_se_renueva(equipo, monkeypatch):
    monkeypatch.setattr(sg, "ultima_vigilancia", None)

    class Roto:
        def query(self, *a, **k):
            raise RuntimeError("base bloqueada")

    with pytest.raises(RuntimeError):
        sg.vigilar(Roto(), None)
    assert sg.ultima_vigilancia is None  # el panel lo ve: el pulso no avanzó


@pytest.mark.parametrize(
    "ultimo,arranque_hace_s,activa",
    [
        (59, 9999, True),  # latió hace menos de un minuto
        (61, 9999, False),  # hace más de un minuto: algo se colgó
        (None, 10, True),  # recién encendido, aún no le toca la primera pasada
        (None, 61, False),  # lleva más de un minuto encendido y nunca latió
    ],
)
def test_la_vigilancia_se_da_por_caida_pasado_un_minuto_sin_latir(cliente, esc, equipo, monkeypatch, ultimo, arranque_hace_s, activa):
    ahora = sg.ahora_utc()
    monkeypatch.setattr(sg, "ultima_vigilancia", ahora - datetime.timedelta(seconds=ultimo) if ultimo is not None else None)
    monkeypatch.setattr(sg, "ARRANQUE", ahora - datetime.timedelta(seconds=arranque_hace_s))
    v = _estado(cliente, esc, vigilando=True)
    assert v["activa"] is activa
    assert _estado(cliente, esc, vigilando=False)["activa"] is None
