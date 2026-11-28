# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Quién está conectado y desde qué equipo (sin IP ni teléfono), y el origen de las cuentas con nombre por revisar."""
import datetime
import json

from infraestructura.modelos_orm import Dispositivo, Usuario
from servicios import servicio_conexiones as sc

PIXEL = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
PC_FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
CODIGO_A, CODIGO_B = "a1b2c3d4e5f60718", "ffeeddccbbaa9988"


def equipo(codigo, ua):
    return {"X-Dispositivo": codigo, "User-Agent": ua}


def test_resumen_del_dispositivo_solo_tipo_sistema_y_navegador():
    assert sc.resumen_dispositivo(PIXEL) == "Teléfono · Android · Chrome"
    assert sc.resumen_dispositivo(IPHONE) == "Teléfono · iOS · Safari"
    assert sc.resumen_dispositivo(PC_FIREFOX) == "Computador · Windows · Firefox"
    assert sc.resumen_dispositivo("Mozilla/5.0 (Linux; Android 13; SM-T500) Chrome/120.0 Safari/537.36") == "Tablet · Android · Chrome"
    assert sc.resumen_dispositivo(None) == "Computador · otro sistema · otro navegador"


def test_cuentas_conectadas_y_origen_de_un_nombre_por_revisar(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()

    def unirse(nombre, rut, cabeceras, confirmar=False):
        return cliente.post("/cursos/unirse", json={"codigo_invitacion": curso["codigo_invitacion"], "rut": rut, "nombre": nombre, "pin": "482915", "confirmar_nombre": confirmar}, headers=cabeceras)

    # Un teléfono crea una cuenta con un nombre que suena a broma; el mismo teléfono entra luego con otra cuenta normal.
    broma = unirse("Armando Casas", "21000001-1", equipo(CODIGO_A, PIXEL), confirmar=True)
    normal = unirse("Juan Soto", "21000002-K", equipo(CODIGO_A, PIXEL))
    otro = unirse("Pedro Pérez", "21000003-8", equipo(CODIGO_B, PC_FIREFOX))
    for r in (broma, normal, otro):
        assert r.status_code == 200
    # Estar conectado = hacer algo con la sesión desde ese equipo.
    for r, cab in ((broma, equipo(CODIGO_A, PIXEL)), (normal, equipo(CODIGO_A, PIXEL)), (otro, equipo(CODIGO_B, PC_FIREFOX))):
        assert cliente.get("/auth/me", headers={**cab, "Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200

    estado = cliente.get("/estado", headers=headers_utp).json()["conexiones"]
    por_nombre = {c["nombre"]: c for c in estado["conectados"]}
    assert por_nombre["Armando Casas"]["dispositivo"] == "Teléfono · Android · Chrome" and por_nombre["Armando Casas"]["rol"] == "ALUMNO"
    assert por_nombre["Armando Casas"]["codigo"] == CODIGO_A[-4:].upper()
    assert por_nombre["Pedro Pérez"]["dispositivo"] == "Computador · Windows · Firefox"
    assert estado["dispositivos_conectados"] == 2  # 3 personas, 2 equipos
    # El nombre por revisar dice desde qué equipo salió y quién más lo usó.
    assert [(n["alumno"], n["dispositivo"], n["otras_cuentas"], n["cursos"]) for n in estado["nombres_por_revisar"]] == [("Armando Casas", "Teléfono · Android · Chrome", ["Juan Soto"], ["8A"])]
    # Nada de IP ni de datos del navegador fuera del resumen.
    texto = json.dumps(cliente.get("/estado", headers=headers_utp).json())
    assert "127.0.0.1" not in texto and "Mozilla" not in texto and CODIGO_A not in texto

    # Cuando el nombre se revisa, se olvida desde dónde se creó.
    armando = next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["nombre"] == "Armando Casas")
    assert cliente.post(f"/usuarios/{armando}/nombre-revisado", headers=headers_utp).status_code == 200
    assert cliente.get("/estado", headers=headers_utp).json()["conexiones"]["nombres_por_revisar"] == []
    with cliente.sesion() as db:
        assert db.get(Usuario, armando).registro_dispositivo_id is None


def test_un_codigo_inventado_no_se_guarda_y_sin_codigo_solo_se_anota_la_conexion(cliente, colegio_id, headers_utp):
    for malo in ("no-es-un-codigo", "A" * 8, "x" * 20, "a1b2c3d4e5f60718' OR 1=1"):
        assert cliente.get("/auth/me", headers={**headers_utp, "X-Dispositivo": malo, "User-Agent": PIXEL}).status_code == 200
    with cliente.sesion() as db:
        assert db.query(Dispositivo).count() == 0
    conectados = cliente.get("/estado", headers=headers_utp).json()["conexiones"]
    assert [(c["rol"], c["dispositivo"]) for c in conectados["conectados"]] == [("UTP", None)]


def test_los_equipos_sin_uso_se_borran_a_los_30_dias(cliente, colegio_id, headers_utp):
    cliente.get("/auth/me", headers={**headers_utp, **equipo(CODIGO_A, PIXEL)})
    with cliente.sesion() as db:
        utp = db.query(Usuario).first()
        assert utp.dispositivo_id is not None and utp.visto_en is not None
        sc.limpiar(db, sc.ahora_utc() + datetime.timedelta(days=sc.DIAS_RASTRO - 1))
        assert db.query(Dispositivo).count() == 1  # aún dentro del plazo
        sc.limpiar(db, sc.ahora_utc() + datetime.timedelta(days=sc.DIAS_RASTRO + 1))
        db.refresh(utp)
        assert db.query(Dispositivo).count() == 0 and utp.dispositivo_id is None and utp.visto_en is None


def test_el_panel_es_solo_del_utp_y_de_su_colegio(cliente, colegio_id, headers_utp, otro_colegio):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    r = cliente.post("/cursos/unirse", json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "21000001-1", "nombre": "Juan Soto", "pin": "482915"}, headers=equipo(CODIGO_A, PIXEL))
    alumno = {"Authorization": f"Bearer {r.json()['access_token']}", **equipo(CODIGO_A, PIXEL)}
    assert cliente.get("/estado", headers=alumno).status_code == 403
    assert cliente.get("/estado").status_code == 401
    ajeno = cliente.get("/estado", headers=otro_colegio[1]).json()["conexiones"]
    assert [c["nombre"] for c in ajeno["conectados"]] == ["UTP B"] and ajeno["dispositivos_conectados"] == 0


def test_dos_pedidos_a_la_vez_con_el_mismo_equipo_nuevo_no_fallan(cliente, colegio_id, monkeypatch):
    """Al abrir la aplicación un equipo nuevo manda varios pedidos juntos: si otro ya lo creó entre la consulta y la inserción, se usa ese en vez de dar error 500."""
    import types

    pedido = types.SimpleNamespace(headers={"x-dispositivo": CODIGO_A, "user-agent": PIXEL})
    with cliente.sesion() as db:
        db.add(Dispositivo(colegio_id=colegio_id, codigo=CODIGO_A, resumen="viejo", ultima_vez=datetime.datetime(2026, 1, 1)))
        db.commit()
        buscar = sc._buscar
        llamadas = []
        monkeypatch.setattr(sc, "_buscar", lambda *a: None if not llamadas.append(1) and len(llamadas) == 1 else buscar(*a))  # la primera consulta «no lo ve»: la carrera
        d = sc.dispositivo_de(db, colegio_id, pedido)
        assert d is not None and d.resumen == "Teléfono · Android · Chrome"  # se actualizó el que ya existía
        db.commit()
        assert db.query(Dispositivo).filter_by(colegio_id=colegio_id, codigo=CODIGO_A).count() == 1
