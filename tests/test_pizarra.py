# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Fotos de la pizarra: el profesor las sube desde el celular, un modelo de visión las lee y solo queda el texto."""
import io

import pytest
from PIL import Image

from infraestructura.modelos_orm import FotoPizarra
from servicios import servicio_grabacion as sg
from servicios import servicio_pizarra as sp
from test_grabaciones import EQUIPO_A, _comando, _crear, _en_curso, _estado, _terminar_con_audio, _vigilar, g, tiempo  # noqa: F401


_leer_real = sp._leer  # el `entorno` de abajo lo reemplaza en cada prueba
_activadas_real = sp.activadas


def foto(ancho=2000, alto=1000, formato="JPEG", orientacion=None):
    im = Image.new("RGB", (ancho, alto), (250, 250, 250))
    salida = io.BytesIO()
    exif = Image.Exif()
    if orientacion:
        exif[0x0112] = orientacion
        exif[0x8825] = {1: "S"}  # un dato de ubicación, que no debe sobrevivir
    im.save(salida, formato, exif=exif if formato == "JPEG" else None)
    return salida.getvalue()


@pytest.fixture(autouse=True)
def entorno(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "activadas", lambda colegio: True)  # las pruebas parten con la función activada; las del final usan la real
    monkeypatch.setattr(sp, "CARPETA_FOTOS", tmp_path / "fotos")
    monkeypatch.setattr(sp, "esperar_memoria", lambda *a, **k: True)
    monkeypatch.setattr(sp.cliente_ollama, "descargar_modelo", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_leer", lambda ruta, url, reducida=False: "Hw: Student Book 3A")


def subir(g, gid, datos=None, quien="ana", segundo=0, tipo="image/jpeg"):
    return g["c"].post(f"/grabaciones/{gid}/fotos", params={"segundo": segundo}, content=foto() if datos is None else datos, headers={**g[quien], "Content-Type": tipo})


def archivos(tmp_path):
    return sorted(p.name for p in (tmp_path / "fotos").rglob("*.jpg"))


def test_el_profesor_sube_una_foto_y_queda_pendiente_con_nombre_puesto_por_el_servidor(g, tmp_path):
    gid = _en_curso(g)
    r = subir(g, gid, segundo=125)
    assert r.status_code == 201
    fotos = r.json()["fotos"]
    assert [(f["segundo"], f["estado"], f["texto"]) for f in fotos] == [(125, "pendiente", None)]
    assert archivos(tmp_path) == [f"{fotos[0]['id']}.jpg"]


def test_solo_el_profesor_de_la_clase_y_solo_desde_la_red_local(g, cliente_remoto):
    gid = _en_curso(g)
    assert subir(g, gid, quien="beta").status_code == 404
    assert subir(g, gid, quien="alumno").status_code == 403
    r = cliente_remoto.post(f"/grabaciones/{gid}/fotos", content=foto(), headers={**g["ana"], "Content-Type": "image/jpeg"})
    assert r.status_code == 403


def test_la_foto_se_reorienta_se_reduce_y_pierde_los_metadatos(g, tmp_path):
    gid = _en_curso(g)
    assert subir(g, gid, foto(2400, 1200, orientacion=6)).status_code == 201
    guardada = next((tmp_path / "fotos").rglob("*.jpg"))
    im = Image.open(guardada)
    assert max(im.size) == sp.LADO_MAXIMO and im.size[1] > im.size[0]  # girada a vertical (orientación 6) y reducida
    assert not im.getexif()  # sin la ubicación ni nada del celular


def test_rechaza_lo_que_no_es_una_foto_lo_vacio_y_lo_enorme(g, tmp_path, monkeypatch):
    gid = _en_curso(g)
    assert subir(g, gid, b"%PDF-1.4 no soy una foto").status_code == 415
    assert subir(g, gid, foto(formato="GIF")).status_code == 415
    assert subir(g, gid, b"").status_code == 413
    monkeypatch.setattr(sp, "MAX_BYTES", 1000)
    assert subir(g, gid, foto()).status_code == 413
    assert archivos(tmp_path) == []


def test_tope_de_fotos_por_clase(g, monkeypatch):
    gid = _en_curso(g)
    monkeypatch.setattr(sp, "MAX_FOTOS", 2)
    assert subir(g, gid).status_code == 201 and subir(g, gid).status_code == 201
    assert subir(g, gid).status_code == 409


def test_no_se_aceptan_fotos_si_la_clase_ya_se_proceso(g):
    gid = _en_curso(g)
    _terminar_con_audio(g, gid)
    assert _estado(g, gid)["estado"] == "terminada"
    assert subir(g, gid).status_code == 409


def test_el_texto_de_la_foto_llega_al_generador_y_la_imagen_se_borra(g, monkeypatch, tmp_path):
    recibido = []
    monkeypatch.setattr(sg, "generar_material", lambda t, asignatura=None, pizarra="": (recibido.append(pizarra), ("Resumen X", "- p", "h", [{"pregunta": "¿P?", "respuesta": "R"}]))[1])
    gid = _en_curso(g)
    subir(g, gid, segundo=600)
    s = _terminar_con_audio(g, gid)
    assert s["estado"] == "terminada"
    assert "Hw: Student Book 3A" in recibido[0] and "[Foto a los 10 min]" in recibido[0] and "Puede tener errores" in recibido[0]
    assert [(f["estado"], f["texto"]) for f in s["fotos"]] == [("leida", "Hw: Student Book 3A")]
    assert archivos(tmp_path) == []  # la imagen no se queda


def test_una_foto_que_no_se_puede_leer_no_frena_la_clase(g, monkeypatch, tmp_path):
    def falla(ruta, url, reducida=False):
        raise RuntimeError('model "qwen2.5vl:3b" not found, try pulling it first')

    monkeypatch.setattr(sp, "_leer", falla)
    gid = _en_curso(g)
    subir(g, gid)
    s = _terminar_con_audio(g, gid)
    assert s["estado"] == "terminada"
    assert s["fotos"][0]["estado"] == "error" and "el UTP puede descargarlo en Ajustes" in s["fotos"][0]["error"]
    assert archivos(tmp_path) == []


def test_sin_memoria_para_el_modelo_de_vision_la_clase_sigue_sin_las_fotos(g, monkeypatch):
    monkeypatch.setattr(sp, "esperar_memoria", lambda *a, **k: False)
    monkeypatch.setattr(sp, "_leer", lambda *a: pytest.fail("no debía leer sin memoria"))
    gid = _en_curso(g)
    subir(g, gid)
    s = _terminar_con_audio(g, gid)
    assert s["estado"] == "terminada" and "memoria" in s["fotos"][0]["error"]


def test_si_la_clase_no_se_pudo_procesar_las_fotos_sin_leer_se_descartan(g, monkeypatch, tmp_path):
    monkeypatch.setattr(sg, "transcribir", lambda ruta: ("   ", ""))  # sin voz: reintentar no lo arregla
    gid = _en_curso(g)
    subir(g, gid)
    s = _terminar_con_audio(g, gid)
    assert s["estado"] == "error" and s["fotos"][0]["estado"] == "error"
    assert archivos(tmp_path) == []


def test_cancelar_la_sesion_borra_sus_fotos(g, tmp_path):
    gid = _crear(g).json()["id"]  # cancelar solo se puede antes de empezar a grabar
    subir(g, gid)
    assert archivos(tmp_path)
    assert _comando(g, gid, "cancelar").status_code in (200, 204)
    assert archivos(tmp_path) == []


def test_al_arrancar_se_borran_las_imagenes_que_ya_no_hacen_falta_y_se_conservan_las_pendientes(g, tmp_path):
    gid = _en_curso(g)
    subir(g, gid)
    huerfana = tmp_path / "fotos" / "999" / "5.jpg"
    huerfana.parent.mkdir(parents=True)
    huerfana.write_bytes(b"x")
    with g["c"].sesion() as db:
        sp.limpiar_huerfanas(db)
    assert not huerfana.exists() and len(archivos(tmp_path)) == 1


def test_el_texto_para_el_material_va_en_orden_con_tope_y_sin_fotos_es_vacio(g):
    gid = _en_curso(g)
    with g["c"].sesion() as db:
        assert sp.texto_para_el_material(db, gid) == ""
        db.add_all([
            FotoPizarra(grabacion_id=gid, segundo=900, estado="leida", texto="segunda"),
            FotoPizarra(grabacion_id=gid, segundo=60, estado="leida", texto="primera"),
            FotoPizarra(grabacion_id=gid, segundo=500, estado="leida", texto="intermedia"),
            FotoPizarra(grabacion_id=gid, segundo=100, estado="error", error="x"),
            FotoPizarra(grabacion_id=gid, segundo=200, estado="leida", texto="   "),
        ])
        db.commit()
        t = sp.texto_para_el_material(db, gid)
        assert t.index("primera") < t.index("intermedia") < t.index("segunda") and "x" not in t.split("segunda")[1]
        db.add(FotoPizarra(grabacion_id=gid, segundo=1000, estado="leida", texto="z" * 10_000))
        db.commit()
        assert len(sp.texto_para_el_material(db, gid)) < sp.MAX_CARACTERES_AL_MATERIAL + 1000


def test_cada_imagen_se_borra_apenas_se_lee_sin_esperar_a_las_demas(g, monkeypatch, tmp_path):
    """Si el proceso muriera a mitad de la lectura, no deben quedar en disco las imágenes ya leídas."""
    gid = _en_curso(g)
    subir(g, gid, segundo=1), subir(g, gid, segundo=2)
    vistas = []

    def leer(ruta, url, reducida=False):
        vistas.append(len(archivos(tmp_path)))  # cuántas imágenes hay en disco al empezar a leer ésta
        return "texto"

    monkeypatch.setattr(sp, "_leer", leer)
    sp.leer_pendientes(gid, g["c"].sesion)
    assert vistas == [2, 1]


def test_las_fotos_se_leen_en_el_orden_de_la_clase_y_no_en_el_de_subida(g, monkeypatch):
    gid = _en_curso(g)
    subir(g, gid, segundo=900), subir(g, gid, segundo=60)
    leidas = []
    monkeypatch.setattr(sp, "_leer", lambda ruta, url, reducida=False: leidas.append(ruta.stem) or f"t{len(leidas)}")
    sp.leer_pendientes(gid, g["c"].sesion)
    with g["c"].sesion() as db:
        assert [(f.segundo, f.texto) for f in db.query(FotoPizarra).order_by(FotoPizarra.segundo)] == [(60, "t1"), (900, "t2")]


def test_el_servidor_limpia_las_imagenes_sobrantes_al_recuperarse(g, tmp_path):
    huerfana = tmp_path / "fotos" / "999" / "5.jpg"
    huerfana.parent.mkdir(parents=True)
    huerfana.write_bytes(b"x")
    with g["c"].sesion() as db:
        sg.recuperar_al_iniciar(db, g["c"].sesion)
    assert not huerfana.exists()


# --- Lo que encontró la prueba de punta a punta con el modelo de visión real ------------------------------------------------
# Con una pizarra de cálculo densa el modelo entró en un bucle y Ollama abortó («token repeat limit reached»); y a partir de ahí
# todas las fotos siguientes fallaban hasta que el modelo se recargaba. A 1280 px pasaba siempre; a 1024 no.

NL = chr(10)


def test_una_respuesta_que_se_repite_se_deja_una_sola_vez():
    bloque = ["$$X & ING 9920.3 9920.4$$", "U(x)=4620x-210x^2", "V(x)=4620x-9000-1300x"]
    repetido = NL.join(bloque * 4 + ["& texto cortado a la m"])
    limpio = sp.limpiar_repeticiones(repetido)
    assert limpio.splitlines()[:3] == bloque
    assert limpio.count("U(x)=4620x-210x^2") == 1


def test_un_texto_normal_no_se_toca_aunque_repita_algo_dos_veces_o_algo_corto():
    texto = NL.join(["Hw.: p. 44", "ejercicio 15 del libro", "- uno", "- uno", "ejercicio 15 del libro", "fin"])
    assert sp.limpiar_repeticiones(texto) == texto  # dos veces no es un bucle; las líneas cortas no cuentan


def test_la_foto_se_guarda_a_1024_px_que_es_con_lo_que_se_midio(g, tmp_path):
    gid = _en_curso(g)
    assert subir(g, gid, foto(3000, 2000)).status_code == 201
    assert max(Image.open(next((tmp_path / "fotos").rglob("*.jpg"))).size) == 1024 == sp.LADO_MAXIMO


def test_si_ollama_aborta_se_descarga_el_modelo_y_se_reintenta_con_la_foto_mas_chica(g, monkeypatch):
    llamadas, descargas = [], []
    monkeypatch.setattr(sp.cliente_ollama, "descargar_modelo", lambda *a, **k: descargas.append(1))

    def leer(ruta, url, reducida=False):
        llamadas.append(reducida)
        if not reducida:
            raise RuntimeError('Error de Ollama: {"error":"prediction aborted, token repeat limit reached"}')
        return "texto del segundo intento"

    monkeypatch.setattr(sp, "_leer", leer)
    gid = _en_curso(g)
    subir(g, gid)
    sp.leer_pendientes(gid, g["c"].sesion)
    with g["c"].sesion() as db:
        f = db.query(FotoPizarra).one()
        assert (f.estado, f.texto) == ("leida", "texto del segundo intento")
    assert llamadas == [False, True] and len(descargas) >= 1


def test_una_foto_que_falla_dos_veces_no_deja_mal_a_las_que_siguen(g, monkeypatch):
    """El modelo se descarga tras el fallo: la foto siguiente se lee con el modelo recargado."""
    eventos = []
    monkeypatch.setattr(sp.cliente_ollama, "descargar_modelo", lambda *a, **k: eventos.append("descarga"))

    def leer(ruta, url, reducida=False):
        eventos.append(f"lee {ruta.stem}")
        if ruta.stem == "1":
            raise RuntimeError("token repeat limit reached")
        return "bien"

    monkeypatch.setattr(sp, "_leer", leer)
    gid = _en_curso(g)
    subir(g, gid, segundo=1), subir(g, gid, segundo=2)
    sp.leer_pendientes(gid, g["c"].sesion)
    with g["c"].sesion() as db:
        assert [(f.segundo, f.estado) for f in db.query(FotoPizarra).order_by(FotoPizarra.segundo)] == [(1, "error"), (2, "leida")]
    # la primera se intentó dos veces, con una descarga entre medio y otra después de rendirse, antes de leer la segunda
    assert eventos[:5] == ["lee 1", "descarga", "lee 1", "descarga", "lee 2"]


def test_si_el_modelo_no_esta_instalado_no_se_reintenta(g, monkeypatch):
    intentos = []
    monkeypatch.setattr(sp.cliente_ollama, "descargar_modelo", lambda *a, **k: None)

    def leer(ruta, url, reducida=False):
        intentos.append(reducida)
        raise RuntimeError('model "qwen2.5vl:3b" not found, try pulling it first')

    monkeypatch.setattr(sp, "_leer", leer)
    gid = _en_curso(g)
    subir(g, gid)
    sp.leer_pendientes(gid, g["c"].sesion)
    assert intentos == [False]


def test_la_lectura_real_limpia_las_repeticiones_y_en_el_reintento_manda_la_foto_mas_chica(tmp_path, monkeypatch):
    enviado = []
    repetido = NL.join(["una linea larga repetida"] * 5 + ["fin"])
    monkeypatch.setattr(sp.cliente_ollama, "generate", lambda prompt, modelo, tope, url, **k: enviado.append(k) or repetido)
    ruta = tmp_path / "f.jpg"
    Image.new("RGB", (1024, 800), "white").save(ruta, "JPEG")
    assert _leer_real(ruta, "http://x") == NL.join(["una linea larga repetida", "fin"])
    assert _leer_real(ruta, "http://x", reducida=True)
    normal, reducida = enviado
    assert normal["opciones"]["repeat_penalty"] == 1.1 and reducida["opciones"]["repeat_penalty"] == 1.3
    import base64, io as _io
    tamano = lambda k: Image.open(_io.BytesIO(base64.b64decode(k["imagenes"][0]))).size
    assert max(tamano(normal)) == 1024 and max(tamano(reducida)) == sp.LADO_REINTENTO == 768


# --- Opcional: el UTP elige en «Ajustes» si el colegio tiene las fotos -----------------------------------------------------------


def test_sin_activar_las_fotos_el_servidor_las_rechaza_y_la_pantalla_lo_sabe(g, monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "activadas", _activadas_real)  # la función de verdad, que mira el ajuste del colegio
    gid = _en_curso(g)
    assert _estado(g, gid)["fotos_habilitadas"] is False  # un colegio nuevo la tiene apagada
    r = subir(g, gid)
    assert r.status_code == 403 and "no están activadas" in r.json()["detail"]
    assert archivos(tmp_path) == []

    # lo que hace el UTP en Ajustes (por la API, como lo hace la pantalla)
    assert g["c"].put("/ajustes/fotos-pizarra", json={"activada": True}, headers=g["utp"]).status_code == 200
    assert _estado(g, gid)["fotos_habilitadas"] is True  # ahora la pantalla de grabar muestra el botón
    assert subir(g, gid).status_code == 201
    g["c"].put("/ajustes/fotos-pizarra", json={"activada": False}, headers=g["utp"])
    assert subir(g, gid).status_code == 403 and _estado(g, gid)["fotos_habilitadas"] is False  # y si lo apaga, deja de aceptarlas


def test_la_funcion_depende_del_colegio_y_sin_colegio_esta_apagada():
    class Colegio:
        fotos_pizarra = True

    assert _activadas_real(Colegio()) is True
    Colegio.fotos_pizarra = False
    assert _activadas_real(Colegio()) is False
    assert _activadas_real(None) is False


def test_la_direccion_de_ollama_usa_127_0_0_1_y_respeta_una_remota(monkeypatch):
    """`localhost` en Windows prueba IPv6 primero y, con Ollama cerrado, cada consulta tarda el doble (medido)."""
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setattr(sp.app_config, "get_param", lambda clave: "http://localhost:11434")
    assert sp.url_ollama() == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_URL", "http://servidor-ia.colegio:11434")
    assert sp.url_ollama() == "http://servidor-ia.colegio:11434"
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:9999")
    assert sp.url_ollama() == "http://127.0.0.1:9999"
