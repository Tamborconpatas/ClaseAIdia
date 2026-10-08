"""Ataques contra la API, como los haría alguien con Postman, curl o un script.

Recorre TODAS las rutas (se descubren solas: si mañana se agrega una, entra en estas pruebas sin tocar nada):
- sin sesión, con sesión falsa y con el rol equivocado;
- inyección SQL, XSS y otros textos maliciosos en cada campo, parámetro y cabecera;
- cuerpos mal formados, números gigantes, textos enormes, JSON anidado, tipos cambiados;
- campos de más (mass assignment) y acceso a datos de otro colegio (IDOR);
- subidas de audio y fotos maliciosas.
Lo que se exige siempre: nunca un error 500, nunca un texto de error de la base de datos o un traceback en la respuesta,
y la base de datos intacta.
"""
import datetime
import json
import re

import jwt
import pytest
from fastapi.testclient import TestClient

from infraestructura import seguridad
from infraestructura.modelos_orm import Base, Clase, ContenidoClase, RolNombre, Usuario
from interfaz.api import limites, rutas_ajustes, rutas_auth, rutas_bloques, rutas_clases, rutas_colegios, rutas_cursos, rutas_estado, rutas_grabaciones, rutas_usuarios
from interfaz.api.aplicacion import crear_app
from nucleo.limitador import LimitadorDeFallos
from servicios import servicio_grabacion as sg

CLAVE = "clave-segura-123"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
EQUIPO = "equipo-sala-0001"
LUNES_0930 = datetime.datetime(2026, 9, 28, 9, 30)

# --- Inventario de rutas -----------------------------------------------------------------------------------------------

MODULOS = (rutas_ajustes, rutas_auth, rutas_bloques, rutas_clases, rutas_colegios, rutas_cursos, rutas_estado, rutas_grabaciones, rutas_usuarios)
PUBLICAS = {
    ("GET", "/auth/estado"), ("POST", "/auth/setup"), ("POST", "/auth/login/staff"), ("POST", "/auth/login/alumno"),
    ("POST", "/auth/restablecer-pin"), ("POST", "/auth/restablecer-password"), ("POST", "/cursos/unirse"), ("GET", "/salud"),
}


def _roles_exigidos(dependant) -> set[str]:
    roles = set()
    for d in dependant.dependencies:
        if getattr(d.call, "__qualname__", "").startswith("requiere_rol"):
            for celda in d.call.__closure__ or ():
                if isinstance(celda.cell_contents, tuple):
                    roles |= {r.value for r in celda.cell_contents}
        roles |= _roles_exigidos(d)
    return roles


def _pide_sesion(dependant) -> bool:
    return any(getattr(d.call, "__name__", "") == "usuario_actual" or _pide_sesion(d) for d in dependant.dependencies)


def _inventario():
    rutas = []
    for modulo in MODULOS:
        for r in modulo.router.routes:
            for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
                rutas.append({"metodo": metodo, "ruta": r.path, "roles": _roles_exigidos(r.dependant), "con_sesion": _pide_sesion(r.dependant)})
    return rutas


RUTAS = _inventario() + [{"metodo": "GET", "ruta": "/salud", "roles": set(), "con_sesion": False}]  # /salud está en aplicacion.py, no en un router
PRIVADAS = [r for r in RUTAS if (r["metodo"], r["ruta"]) not in PUBLICAS]
CON_ROLES = [r for r in PRIVADAS if r["roles"]]
ID = lambda r: f"{r['metodo']} {r['ruta']}"  # noqa: E731


def test_el_inventario_cubre_todas_las_rutas_de_la_api():
    """Si se agrega un router y no entra en MODULOS, estas pruebas no lo verían: esto lo detecta."""
    del_esquema = {(m.upper(), p) for p, ops in crear_app().openapi()["paths"].items() for m in ops}
    assert del_esquema == {(r["metodo"], r["ruta"]) for r in RUTAS}


def test_toda_ruta_que_no_es_publica_exige_sesion():
    sin_proteccion = [ID(r) for r in PRIVADAS if not r["con_sesion"] and not r["roles"]]
    assert sin_proteccion == []


# --- Mundo de prueba ---------------------------------------------------------------------------------------------------


def _con(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def m(cliente, colegio_id, headers_utp, tmp_path, monkeypatch):
    """Un colegio con UTP, una profesora (Ana), un alumno (Luis), un curso, un bloque, una clase con material y una
    grabación en curso; más un segundo colegio con su UTP. Con límites altos: aquí se prueba la API, no el freno por IP."""
    monkeypatch.setattr(limites, "por_ip", LimitadorDeFallos(10**9, 600))
    monkeypatch.setattr(sg, "ahora_local", lambda: LUNES_0930)
    monkeypatch.setattr(sg, "ahora_utc", lambda: datetime.datetime(2026, 9, 28, 12, 30))
    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    r = cliente.post("/usuarios", json={"rut": "5126663-3", "nombre": "Ana", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, headers=headers_utp)
    ana_id = r.json()["id"]
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    bloque = {"tipo": "CLASE", "asignatura": "Matemática", "profesor_id": ana_id, "sala": "S1", "dia_semana": 0, "hora_inicio": "09:00", "hora_fin": "10:00"}
    bloque_id = cliente.post(f"/cursos/{curso['id']}/bloques", json=bloque, headers=headers_utp).json()["id"]
    luis = cliente.post("/cursos/unirse", json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "Luis", "pin": "482915"})
    ana = cliente.post("/auth/login/staff", json={"rut": "5126663-3", "password": CLAVE}).json()["access_token"]
    grabacion = cliente.post("/grabaciones", json={"bloque_id": bloque_id}, headers=_con(ana)).json()
    with cliente.sesion() as db:
        clase_id = db.query(Clase).filter_by(bloque_id=bloque_id).first().id
        db.get(Clase, clase_id).contenido = ContenidoClase(resumen="r", puntos_clave="- p", hoja_repaso="h", tarjetas=[], transcripcion_texto="t", aprobado=True)
        db.commit()
        ids_usuarios = {u.rut: u.id for u in db.query(Usuario).all()}
    otro_colegio_id, otro_utp = _segundo_colegio(cliente)
    return {
        "c": cliente, "tmp": tmp_path, "colegio_id": colegio_id, "curso": curso, "curso_id": curso["id"], "bloque_id": bloque_id, "bloque": bloque,
        "clase_id": clase_id, "grabacion_id": grabacion["id"], "ana_id": ana_id, "luis_id": ids_usuarios["11222333-9"], "utp_id": ids_usuarios["7654321-6"],
        "utp": headers_utp, "ana": _con(ana), "luis": _con(luis.json()["access_token"]), "otro_utp": otro_utp, "otro_colegio_id": otro_colegio_id,
    }


def _segundo_colegio(cliente):
    from infraestructura.modelos_orm import Colegio, UsuarioRol
    from infraestructura.seguridad import hashear_secreto

    with cliente.sesion() as db:
        colegio = Colegio(nombre="Otro Colegio")
        utp = Usuario(rut="1000005-K", nombre="UTP B", colegio=colegio, password_hash=hashear_secreto(CLAVE))
        utp.roles = [UsuarioRol(rol=RolNombre.UTP)]
        db.add(utp)
        db.commit()
        cid = colegio.id
    r = cliente.post("/auth/login/staff", json={"rut": "1000005-K", "password": CLAVE})
    return cid, _con(r.json()["access_token"])


def _llenar(ruta: str, m, valor=None) -> str:
    """Pone ids reales (o `valor`) en los parámetros de la ruta."""
    ids = {"colegio_id": m["colegio_id"], "curso_id": m["curso_id"], "bloque_id": m["bloque_id"], "clase_id": m["clase_id"], "grabacion_id": m["grabacion_id"],
           "usuario_id": m["luis_id"], "foto_id": 1, "n": 0}
    return re.sub(r"\{(\w+)\}", lambda k: str(valor if valor is not None else ids[k.group(1)]), ruta)


def _pedir(c, metodo, url, **kw):
    return c.request(metodo, url, **kw)


# --- Sin sesión, sesión falsa y rol equivocado -------------------------------------------------------------------------


def test_sin_sesion_ninguna_ruta_privada_responde(m):
    fallas = []
    for r in PRIVADAS:
        resp = _pedir(m["c"], r["metodo"], _llenar(r["ruta"], m))
        if resp.status_code not in (401, 403):
            fallas.append(f"{ID(r)} -> {resp.status_code} {resp.text[:80]}")
    assert fallas == [], "\n".join(fallas)


CABECERAS_FALSAS = [
    "Bearer", "Bearer ", "Bearer x", "Bearer a.b.c", "Basic YWRtaW46YWRtaW4=", "Bearer null", "Bearer undefined", "token", "Bearer " + "A" * 5000,
    "Bearer ' OR '1'='1", "Bearer eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxIiwiZXhwIjo0MTAyNDQ0ODAwfQ.",
]


def test_una_sesion_inventada_no_abre_ninguna_ruta(m):
    fallas = []
    for r in PRIVADAS:
        for cabecera in CABECERAS_FALSAS:
            resp = _pedir(m["c"], r["metodo"], _llenar(r["ruta"], m), headers={"Authorization": cabecera})
            if resp.status_code not in (401, 403):
                fallas.append(f"{ID(r)} con {cabecera[:30]!r} -> {resp.status_code} {resp.text[:80]}")
    assert fallas == [], "\n".join(fallas[:15])


def test_cada_ruta_rechaza_a_los_roles_que_no_le_tocan(m):
    fallas = []
    for r in CON_ROLES:
        for quien, rol in (("luis", "ALUMNO"), ("ana", "PROFESOR"), ("utp", "UTP")):
            if rol in r["roles"]:
                continue
            resp = _pedir(m["c"], r["metodo"], _llenar(r["ruta"], m), headers=m[quien], json={})
            if resp.status_code != 403:
                fallas.append(f"{quien} ({rol}) llegó a {ID(r)}: {resp.status_code} {resp.text[:100]}")
    assert fallas == [], "\n".join(fallas)


def test_un_token_con_roles_inventados_no_da_poder_los_roles_salen_de_la_base(m):
    """Firmado con la clave de verdad pero con `roles` y `colegio_id` falsos: el servidor mira la base, no el token."""
    payload = {"sub": str(m["luis_id"]), "rut": "11222333-9", "roles": ["UTP", "PROFESOR"], "colegio_id": m["otro_colegio_id"], "exp": 4102444800, "v": 0}
    falso = jwt.encode(payload, seguridad.JWT_SECRET_KEY, algorithm="HS256")
    assert m["c"].get("/usuarios", headers=_con(falso)).status_code == 403
    assert m["c"].post("/cursos", json={"nombre": "X", "colegio_id": m["colegio_id"]}, headers=_con(falso)).status_code == 403


def test_un_token_de_un_usuario_que_ya_no_existe_o_con_sub_raro_no_pasa(m):
    for sub in ("999999", "0", "-1", "abc", "1; DROP TABLE usuarios", "1.5", "", "99999999999999999999", "-9223372036854775809", str(2**63), "1" * 5000, None, 5, [1], {"a": 1}):
        t = jwt.encode({"sub": sub, "exp": 4102444800}, seguridad.JWT_SECRET_KEY, algorithm="HS256")
        resp = m["c"].get("/auth/me", headers=_con(t))
        assert resp.status_code == 401, (str(sub)[:20], resp.status_code)


def test_un_token_con_la_clave_equivocada_o_alterado_no_pasa(m):
    bueno = m["utp"]["Authorization"].split()[1]
    cab, carga, firma = bueno.split(".")
    for malo in (f"{cab}.{carga}.{firma[:-2]}AA", f"{cab}.{carga}.", f"{cab}.{carga[:-3]}AAA.{firma}",
                 jwt.encode(jwt.decode(bueno, options={"verify_signature": False}), "otra-clave-" * 5, algorithm="HS256")):
        assert m["c"].get("/auth/me", headers=_con(malo)).status_code == 401


# --- Inyección SQL y otros textos maliciosos ---------------------------------------------------------------------------

PAYLOADS = [
    "' OR '1'='1", "' OR 1=1--", "\" OR \"\"=\"", "') OR ('1'='1", "admin'--", "' UNION SELECT 1,2,3--",
    "' UNION SELECT name,sql,3 FROM sqlite_master--", "'; DROP TABLE usuarios;--", "1; DROP TABLE clases", "'; DELETE FROM usuarios WHERE '1'='1",
    "1' AND SLEEP(5)--", "' AND 1=randomblob(500000000)--", "'||(SELECT load_extension('x'))||'", "1 OR 1=1", "-1 UNION SELECT NULL--",
    "%27%20OR%201%3D1--", "\\'; --", "'; ATTACH DATABASE '/tmp/x.db' AS x;--", "'; PRAGMA writable_schema=1;--", "\x00", "a\x00b' OR '1'='1",
    "<script>alert(1)</script>", "\"><img src=x onerror=alert(1)>", "javascript:alert(1)", "{{7*7}}", "${7*7}", "%s%s%s%s%s%n", "{0.__class__}",
    "../../../../etc/passwd", "..\\..\\windows\\win.ini", "%2e%2e%2f%2e%2e%2fetc%2fpasswd", "file:///etc/passwd", "http://169.254.169.254/latest/meta-data/",
    "a\r\nSet-Cookie: x=1", "a\r\n\r\n<html>", "$(id)", "`id`", "; ls -la", "| cat /etc/passwd", "{\"$ne\": null}", "[]", "{}", "null", "true", "‮evil",
    "🔥" * 50, "A" * 10_000,
]
ERRORES_DE_BASE = re.compile(r"sqlite|sqlalchemy|syntax error|near \"|OperationalError|IntegrityError|ProgrammingError|Traceback|File \"|\.py\", line|psycopg|no such (table|column)|unrecognized token", re.I)


def filtra_error(resp, enviado: str = "") -> bool:
    """¿La respuesta trae un texto de error de la base o un traceback? El propio texto enviado, devuelto como dato guardado, no cuenta."""
    texto = resp.text
    for variante in {enviado, json.dumps(enviado)[1:-1], json.dumps(enviado, ensure_ascii=False)[1:-1]}:
        if variante:
            texto = texto.replace(variante, "")
    return bool(ERRORES_DE_BASE.search(texto))


def _hojas_de_texto(valor, ruta=()):
    """Cada texto dentro de un cuerpo JSON, con su camino."""
    if isinstance(valor, str):
        yield ruta
    elif isinstance(valor, dict):
        for k, v in valor.items():
            yield from _hojas_de_texto(v, ruta + (k,))
    elif isinstance(valor, list):
        for i, v in enumerate(valor):
            yield from _hojas_de_texto(v, ruta + (i,))


def _con_valor(cuerpo, ruta, valor):
    copia = json.loads(json.dumps(cuerpo))
    destino = copia
    for k in ruta[:-1]:
        destino = destino[k]
    destino[ruta[-1]] = valor
    return copia


def _cuerpos(m):
    """Un cuerpo válido por cada ruta que lo lleva, con su cabecera de quien puede llamarla."""
    b = dict(m["bloque"])
    return [
        ("POST", "/cursos", {"nombre": "9B", "colegio_id": m["colegio_id"]}, "utp"),
        ("PUT", f"/cursos/{m['curso_id']}", {"nombre": "8A-bis"}, "utp"),
        ("POST", f"/cursos/{m['curso_id']}/bloques", {**b, "dia_semana": 3, "hora_inicio": "11:00", "hora_fin": "12:00"}, "utp"),
        ("PUT", f"/bloques/{m['bloque_id']}", b, "utp"),
        ("POST", "/usuarios", {"rut": "6000000-K", "nombre": "Beto", "colegio_id": m["colegio_id"], "roles": ["PROFESOR"], "password": CLAVE}, "utp"),
        ("PUT", f"/clases/{m['clase_id']}/contenido", {"resumen": "r", "puntos_clave": "- p", "hoja_repaso": "h", "tarjetas": [{"pregunta": "¿P?", "respuesta": "R"}]}, "ana"),
        ("PUT", f"/clases/{m['clase_id']}/mapa", {"relaciones": [{"de": "A", "relacion": "causa", "a": "B"}]}, "ana"),
        ("PUT", f"/clases/{m['clase_id']}/pizarra/1", {"texto": "x"}, "ana"),
        ("POST", f"/grabaciones/{m['grabacion_id']}/grabador", {"dispositivo": EQUIPO, "forzar": False}, "ana"),
        ("POST", f"/grabaciones/{m['grabacion_id']}/latido", {"dispositivo": EQUIPO, "segundos": 1, "nivel": 0.2}, "ana"),
        ("POST", f"/grabaciones/{m['grabacion_id']}/finalizar", {"dispositivo": EQUIPO}, "ana"),
        ("POST", f"/grabaciones/{m['grabacion_id']}/comando", {"accion": "pausar"}, "ana"),
        ("PUT", "/ajustes/fotos-pizarra", {"activada": False}, "utp"),
        ("POST", "/cursos/unirse", {"codigo_invitacion": m["curso"]["codigo_invitacion"], "rut": "13579246-7", "nombre": "Nuevo", "pin": "482915"}, None),
        ("POST", "/auth/login/staff", {"rut": "5126663-3", "password": CLAVE}, None),
        ("POST", "/auth/login/alumno", {"rut": "11222333-9", "pin": "482915"}, None),
        ("POST", "/auth/restablecer-pin", {"rut": "11222333-9", "codigo": "ABCDEF", "pin": "739158"}, None),
        ("POST", "/auth/restablecer-password", {"rut": "5126663-3", "codigo": "ABCDEF", "password": "otra-clave-segura-9"}, None),
        ("POST", "/auth/setup", {"colegio_nombre": "Otro", "rut": "12345678-5", "nombre": "X", "password": CLAVE}, None),
    ]


def _estado_de_la_base(m):
    with m["c"].sesion() as db:
        from sqlalchemy import text  # solo para mirar la base desde la prueba

        tablas = sorted(f[0] for f in db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")))
        cuentas = {t: db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in ("usuarios", "colegios", "cursos", "bloques", "clases", "contenido_clases")}
        roles = sorted(db.execute(text("SELECT usuario_id, rol FROM usuario_roles")).fetchall())
    return tablas, cuentas, roles


def test_ningun_texto_malicioso_en_ningun_campo_rompe_ni_filtra_nada(m):
    antes_tablas, _, antes_roles = _estado_de_la_base(m)
    fallas = []
    enviados = 0
    for metodo, ruta, cuerpo, quien in _cuerpos(m):
        cab = m[quien] if quien else {}
        for hoja in _hojas_de_texto(cuerpo):
            for p in PAYLOADS:
                resp = m["c"].request(metodo, ruta, json=_con_valor(cuerpo, hoja, p), headers=cab)
                enviados += 1
                if resp.status_code >= 500 or filtra_error(resp, p):
                    fallas.append(f"{metodo} {ruta} campo={hoja} payload={p[:30]!r} -> {resp.status_code} {resp.text[:140]}")
                if resp.status_code == 200 and ruta.startswith("/auth/login") and hoja[0] in ("rut", "password", "pin"):
                    fallas.append(f"LOGIN ACEPTADO con {p[:30]!r} en {hoja}")
    tablas, cuentas, roles = _estado_de_la_base(m)
    assert tablas == antes_tablas, "cambió el esquema de la base"
    assert antes_roles == [r for r in roles if r in antes_roles], "se perdieron roles"
    assert enviados > 1500
    assert fallas == [], "\n".join(fallas[:15])


def test_ningun_texto_malicioso_en_la_url_ni_en_los_parametros_rompe_nada(m):
    fallas = []
    for r in RUTAS:
        for p in PAYLOADS[:30]:
            for lugar in ("ruta", "query"):
                if lugar == "ruta":
                    if "{" not in r["ruta"]:
                        continue
                    url, params = _llenar(r["ruta"], m, valor=p), None
                else:
                    url, params = _llenar(r["ruta"], m), {"dispositivo": p, "segundo": p, "curso_id": p, "fecha": p, "q": p}
                cab = m["utp"] if r["roles"] == {"UTP"} else m["ana"] if "PROFESOR" in r["roles"] else m["luis"]
                try:
                    resp = m["c"].request(r["metodo"], url, params=params, headers=cab, content=b"" if r["metodo"] in ("PUT", "POST") else None)
                except Exception as e:  # una URL imposible para el cliente no es un hallazgo del servidor
                    if "InvalidURL" in type(e).__name__ or "LocalProtocol" in type(e).__name__:
                        continue
                    raise
                if resp.status_code >= 500 or filtra_error(resp, p):
                    fallas.append(f"{ID(r)} {lugar}={p[:25]!r} -> {resp.status_code} {resp.text[:120]}")
    assert fallas == [], "\n".join(fallas[:15])


def test_texto_malicioso_en_las_cabeceras_no_rompe_nada(m):
    for cabecera in ("User-Agent", "Referer", "X-Forwarded-For", "X-IP-Cliente", "Origin", "Accept-Language", "Cookie", "X-Real-IP", "Host"):
        for p in PAYLOADS[:20]:
            if "\r" in p or "\n" in p or "\x00" in p:
                continue
            resp = m["c"].get("/auth/me", headers={**m["utp"], cabecera: p})
            assert resp.status_code < 500 and not filtra_error(resp, p), (cabecera, p, resp.status_code)


def test_un_texto_guardado_con_comillas_vuelve_igual_y_no_se_ejecuta(m):
    raro = "Robert'); DROP TABLE usuarios;-- <b>x</b>"
    r = m["c"].post("/cursos", json={"nombre": raro, "colegio_id": m["colegio_id"]}, headers=m["utp"])
    assert r.status_code == 201 and r.json()["nombre"] == raro
    assert raro in {c["nombre"] for c in m["c"].get("/cursos", headers=m["utp"]).json()}
    assert m["c"].get("/usuarios", headers=m["utp"]).status_code == 200  # la tabla sigue ahí
    assert m["c"].get("/estado", headers=m["utp"]).status_code == 200


# --- Cuerpos mal formados, tipos cambiados, tamaños y números imposibles -----------------------------------------------

CON_CUERPO = [(me, ru, cu, qu) for me, ru, cu, qu in [("POST", "/usuarios", {}, "utp")]]  # se rellena abajo


def _rutas_con_cuerpo(m):
    return [(me, ru, cu, qu) for me, ru, cu, qu in _cuerpos(m)]


FORMAS_ROTAS = [
    ("json invalido", b"{", "application/json"), ("vacio", b"", "application/json"), ("llaves sin cerrar", b'{"a":', "application/json"),
    ("comillas simples", b"{'a': 1}", "application/json"), ("lista", b"[]", "application/json"), ("numero", b"123", "application/json"),
    ("texto", b'"hola"', "application/json"), ("null", b"null", "application/json"), ("bytes basura", bytes(range(256)), "application/json"),
    ("utf8 invalido", b'{"nombre": "\xff\xfe"}', "application/json"), ("texto plano", b'{"nombre":"x"}', "text/plain"),
    ("formulario", b"nombre=x&colegio_id=1", "application/x-www-form-urlencoded"), ("xml", b"<a><b>x</b></a>", "application/xml"),
    ("multipart roto", b"--x\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n1\r\n--x--", "multipart/form-data; boundary=x"),
    ("NaN", b'{"nombre": NaN}', "application/json"), ("Infinity", b'{"segundos": Infinity, "nivel": -Infinity}', "application/json"),
    ("anidado 100000", b"[" * 100_000 + b"]" * 100_000, "application/json"), ("objeto anidado", b'{"a":' * 20_000 + b"1" + b"}" * 20_000, "application/json"),
    ("claves duplicadas", b'{"nombre":"a","nombre":"b","colegio_id":1,"colegio_id":2}', "application/json"),
    ("charset raro", b"{}", "application/json; charset=utf-16"), ("sin content-type", b"{}", ""),
]


def test_cuerpos_mal_formados_dan_error_del_cliente_nunca_500(m):
    fallas = []
    for metodo, ruta, _cuerpo, quien in _rutas_con_cuerpo(m):
        cab = m[quien] if quien else {}
        for nombre, datos, tipo in FORMAS_ROTAS:
            h = {**cab, **({"Content-Type": tipo} if tipo else {})}
            resp = m["c"].request(metodo, ruta, content=datos, headers=h)
            if resp.status_code >= 500 or ERRORES_DE_BASE.search(resp.text):
                fallas.append(f"{metodo} {ruta} [{nombre}] -> {resp.status_code} {resp.text[:100]}")
    assert fallas == [], "\n".join(fallas[:15])


NUMEROS_IMPOSIBLES = [0, -1, 2**31, 2**63, 2**64, -(2**63) - 1, 10**30, 10**400, 1.5, 1e308, "1", "abc", None, True, [], {}]


def test_numeros_y_tipos_imposibles_en_cada_campo_dan_error_del_cliente_nunca_500(m):
    fallas = []

    def hojas(valor, ruta=()):
        if isinstance(valor, dict):
            for k, v in valor.items():
                yield from hojas(v, ruta + (k,))
        elif isinstance(valor, list):
            for i, v in enumerate(valor):
                yield from hojas(v, ruta + (i,))
        else:
            yield ruta

    for metodo, ruta, cuerpo, quien in _rutas_con_cuerpo(m):
        cab = m[quien] if quien else {}
        for hoja in hojas(cuerpo):
            for valor in NUMEROS_IMPOSIBLES:
                try:
                    datos = json.dumps(_con_valor(cuerpo, hoja, valor)).encode()
                except (ValueError, OverflowError):
                    continue
                resp = m["c"].request(metodo, ruta, content=datos, headers={**cab, "Content-Type": "application/json"})
                if resp.status_code >= 500 or ERRORES_DE_BASE.search(resp.text):
                    fallas.append(f"{metodo} {ruta} {hoja}={str(valor)[:20]} -> {resp.status_code} {resp.text[:90]}")
    assert fallas == [], "\n".join(fallas[:20])


GIGANTES = [-(2**63) - 1, 2**63, 2**64, 10**30, 10**400]


def test_ids_gigantes_en_la_url_no_dan_500(m):
    fallas = []
    for r in [r for r in RUTAS if "{" in r["ruta"]]:
        cab = m["utp"] if r["roles"] == {"UTP"} or not r["roles"] else m["ana"]
        for g in GIGANTES:
            resp = m["c"].request(r["metodo"], _llenar(r["ruta"], m, valor=g), headers=cab, content=b"{}" if r["metodo"] in ("PUT", "POST") else None)
            if resp.status_code >= 500:
                fallas.append(f"{ID(r)} con {str(g)[:12]}: {resp.status_code} {resp.text[:80]}")
    assert fallas == [], "\n".join(fallas[:15])


TEXTOS_ENORMES = [
    ("POST", "/cursos", "nombre"), ("POST", "/usuarios", "nombre"), ("POST", "/usuarios", "password"), ("PUT", "/cursos/{curso_id}", "nombre"),
    ("POST", "/cursos/unirse", "nombre"), ("POST", "/cursos/{curso_id}/bloques", "asignatura"), ("POST", "/cursos/{curso_id}/bloques", "sala"),
    ("POST", "/auth/login/staff", "rut"), ("POST", "/auth/login/alumno", "pin"),
]


def test_un_texto_enorme_se_rechaza_o_se_acota_no_se_guarda_entero(m):
    fallas = []
    for metodo, ruta, campo in TEXTOS_ENORMES:
        url = _llenar(ruta, m)
        _, _, cuerpo, quien = next(c for c in _cuerpos(m) if c[0] == metodo and c[1] == url)
        for tamano in (100_000, 2_000_000):
            resp = m["c"].request(metodo, url, json={**cuerpo, campo: "A" * tamano}, headers=m[quien] if quien else {})
            if resp.status_code not in (400, 413, 422):
                fallas.append(f"{metodo} {ruta} {campo} de {tamano}: {resp.status_code}")
    assert fallas == [], "\n".join(fallas)


# --- Campos de más (mass assignment) y acceso a datos ajenos ------------------------------------------------------------


def test_campos_de_mas_al_crear_cuentas_se_ignoran_o_se_rechazan(m):
    c = m["c"]
    # Un alumno que se une no puede ponerse roles, colegio, ni dejarse sin bloqueo.
    r = c.post("/cursos/unirse", json={"codigo_invitacion": m["curso"]["codigo_invitacion"], "rut": "13579246-7", "nombre": "Mala", "pin": "482915",
                                       "roles": ["UTP"], "rol": "UTP", "colegio_id": m["otro_colegio_id"], "activo": True, "id": 1, "version_sesion": 99,
                                       "password_hash": "x", "password": "otra-clave-segura-9", "is_admin": True})
    assert r.status_code in (200, 201, 422)
    if r.status_code in (200, 201):
        assert r.json()["roles"] == ["ALUMNO"] and r.json()["colegio_id"] == m["colegio_id"]
        assert c.get("/usuarios", headers=_con(r.json()["access_token"])).status_code == 403
        assert c.post("/auth/login/staff", json={"rut": "13579246-7", "password": "otra-clave-segura-9"}).status_code == 401
    # El UTP crea una cuenta con campos que no existen: no se cuelan al modelo.
    r = c.post("/usuarios", json={"rut": "6000000-K", "nombre": "Beto", "colegio_id": m["colegio_id"], "roles": ["PROFESOR"], "password": CLAVE,
                                  "id": 999, "version_sesion": 50, "activo": False, "pin_hash": "x", "intentos_fallidos": -100}, headers=m["utp"])
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert r.json()["id"] != 999 and r.json()["activo"] is True
        with c.sesion() as db:
            u = db.query(Usuario).filter_by(rut="6000000-K").one()
            assert (u.version_sesion, u.pin_hash, u.intentos_fallidos) == (0, None, 0)


def test_un_utp_no_crea_cuentas_ni_cursos_en_otro_colegio(m):
    c = m["c"]
    r = c.post("/usuarios", json={"rut": "6000000-K", "nombre": "Beto", "colegio_id": m["otro_colegio_id"], "roles": ["PROFESOR"], "password": CLAVE}, headers=m["utp"])
    assert r.status_code in (403, 404)
    r = c.post("/cursos", json={"nombre": "Ajeno", "colegio_id": m["otro_colegio_id"]}, headers=m["utp"])
    assert r.status_code in (403, 404)


def test_el_segundo_colegio_no_ve_ni_toca_nada_del_primero(m):
    """Cada ruta con ids del colegio A, llamada con el UTP del colegio B: nunca un 2xx con datos de A."""
    fallas = []
    for r in PRIVADAS:
        if r["ruta"].startswith(("/grabaciones",)):  # solo profesor, y B no tiene profesor: ya lo cubre la matriz de roles
            continue
        url = _llenar(r["ruta"], m)
        resp = m["c"].request(r["metodo"], url, headers=m["otro_utp"], json={"nombre": "x", "texto": "x", "relaciones": [], "resumen": "x", "puntos_clave": "x", "hoja_repaso": "x", "tarjetas": [], "activada": True})
        if resp.status_code < 300 and r["ruta"] not in ("/auth/me", "/auth/cerrar-sesiones", "/cursos", "/clases", "/usuarios", "/estado", "/ajustes/fotos-pizarra") and r["ruta"] not in ("/cursos/{curso_id}/bloques",):
            fallas.append(f"{ID(r)} -> {resp.status_code} {resp.text[:100]}")
        if resp.status_code < 300 and r["metodo"] == "GET" and r["ruta"] in ("/cursos", "/clases", "/usuarios"):
            assert all(x.get("colegio_id", m["otro_colegio_id"]) == m["otro_colegio_id"] for x in resp.json()), ID(r)
            assert m["curso_id"] not in {x["id"] for x in resp.json()} or r["ruta"] != "/cursos"
    assert fallas == [], "\n".join(fallas)
    # y lo de A sigue intacto
    assert m["c"].get(f"/cursos/{m['curso_id']}", headers=m["utp"]).json()["nombre"] == "8A"


def test_un_alumno_no_ve_datos_de_otros_usuarios_ni_de_otros_cursos(m):
    c = m["c"]
    assert c.get(f"/usuarios/{m['ana_id']}", headers=m["luis"]).status_code == 404
    assert c.get(f"/usuarios/{m['utp_id']}", headers=m["luis"]).status_code == 404
    assert c.get(f"/cursos/{m['curso_id']}/alumnos", headers=m["luis"]).status_code == 403
    assert c.get(f"/cursos/{m['curso_id']}/codigo", headers=m["luis"]).status_code == 403
    assert c.get(f"/usuarios/{m['luis_id']}", headers=m["luis"]).status_code == 200  # el suyo, sí


def test_ningun_dato_secreto_sale_en_ninguna_respuesta(m):
    """Hashes, códigos de reseteo y datos internos no viajan por la API."""
    vistos = []
    for r in RUTAS:
        if r["metodo"] != "GET" or r["roles"] - {"UTP"} and "UTP" not in r["roles"]:
            continue
        resp = m["c"].get(_llenar(r["ruta"], m), headers=m["utp"])
        vistos.append(resp.text)
    cuerpo = " ".join(vistos).lower()
    for prohibido in ("password_hash", "pin_hash", "codigo_reset_hash", "$argon2", "jwt_secret", "version_sesion", "intentos_fallidos"):
        assert prohibido not in cuerpo, prohibido


# --- Subidas de audio y fotos ------------------------------------------------------------------------------------------


def _iniciar_grabacion(m):
    c, gid = m["c"], m["grabacion_id"]
    assert c.post(f"/grabaciones/{gid}/grabador", json={"dispositivo": EQUIPO, "forzar": False}, headers=m["ana"]).status_code == 200
    assert c.post(f"/grabaciones/{gid}/comando", json={"accion": "iniciar"}, headers=m["ana"]).status_code == 200
    return gid


def _trozo(m, n, datos, tipo="audio/webm", dispositivo=EQUIPO):
    return m["c"].put(f"/grabaciones/{m['grabacion_id']}/trozos/{n}", params={"dispositivo": dispositivo}, content=datos, headers={**m["ana"], "Content-Type": tipo})


def test_un_trozo_de_audio_demasiado_grande_se_rechaza(m):
    _iniciar_grabacion(m)
    resp = _trozo(m, 0, WEBM + b"\x00" * (sg.MAX_TROZO_BYTES + 1))
    assert resp.status_code in (400, 413, 422)


def test_un_trozo_con_contenido_o_tipo_falso_no_da_500(m):
    _iniciar_grabacion(m)
    casos = [
        (b"MZ\x90\x00" + b"\x00" * 200, "audio/webm"), (b"#!/bin/sh\nrm -rf /\n", "audio/webm"), (b"<?php system($_GET['c']); ?>", "audio/webm"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 200, "audio/webm"), (b"", "audio/webm"), (b"\x00", "audio/webm"), (WEBM, "text/html"), (WEBM, "application/x-sh"),
    ]
    for datos, tipo in casos:
        resp = _trozo(m, 0, datos, tipo=tipo)
        assert resp.status_code < 500, (datos[:10], tipo, resp.text[:100])


def test_el_numero_de_trozo_no_permite_escribir_fuera_de_la_carpeta(m):
    _iniciar_grabacion(m)
    for n in (-1, 10**12, 2**63, "../../etc/passwd", "..%2f..%2fetc", "0/../1", "a", "1.5", " 1"):
        resp = m["c"].put(f"/grabaciones/{m['grabacion_id']}/trozos/{n}", params={"dispositivo": EQUIPO}, content=WEBM, headers={**m["ana"], "Content-Type": "audio/webm"})
        assert resp.status_code < 500, (n, resp.status_code, resp.text[:100])
    assert [p for p in m["tmp"].parent.rglob("passwd")] == []


def test_el_nombre_del_equipo_no_se_usa_para_armar_rutas(m):
    _iniciar_grabacion(m)
    for dispositivo in ("../../etc/passwd", "a" * 5000, "equipo con espacios", "x;rm -rf /", "' OR 1=1--", "%00", ""):
        resp = _trozo(m, 0, WEBM, dispositivo=dispositivo)
        assert resp.status_code < 500 and not filtra_error(resp, dispositivo), (dispositivo[:20], resp.status_code)


def _png(ancho, alto):
    import struct, zlib
    def trozo(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)) + trozo(b"IDAT", zlib.compress(b"\x00" * 30)) + trozo(b"IEND", b"")


def test_una_foto_maliciosa_no_da_500_ni_cuelga_el_servidor(m):
    _iniciar_grabacion(m)
    casos = [
        ("bomba de descompresion 100000x100000", _png(100_000, 100_000), "image/png"), ("png de 1x1 sin datos reales", _png(1, 1), "image/png"),
        ("ejecutable", b"MZ\x90\x00" + b"\x00" * 100, "image/png"), ("html", b"<html><script>alert(1)</script></html>", "image/png"),
        ("svg con script", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "image/svg+xml"),
        ("vacio", b"", "image/png"), ("jpeg cortado", b"\xff\xd8\xff\xe0" + b"\x00" * 10, "image/jpeg"), ("tipo raro", _png(1, 1), "text/html"),
    ]
    for nombre, datos, tipo in casos:
        resp = m["c"].post(f"/grabaciones/{m['grabacion_id']}/fotos", params={"segundo": 5}, content=datos, headers={**m["ana"], "Content-Type": tipo})
        assert resp.status_code < 500, f"{nombre}: {resp.status_code} {resp.text[:120]}"


def test_una_foto_mas_grande_que_el_tope_se_rechaza(m):
    _iniciar_grabacion(m)
    resp = m["c"].post(f"/grabaciones/{m['grabacion_id']}/fotos", params={"segundo": 5}, content=_png(1, 1) + b"\x00" * (16 * 1024 * 1024), headers={**m["ana"], "Content-Type": "image/png"})
    assert resp.status_code in (400, 413, 422)


# --- Tope al tamaño de lo que se envía ---------------------------------------------------------------------------------


def test_un_json_gigante_se_corta_por_su_largo_declarado(m):
    r = m["c"].post("/cursos", content=b'{"nombre":"' + b"A" * 2_000_000 + b'"}', headers={**m["utp"], "Content-Type": "application/json"})
    assert r.status_code == 413


def test_un_cuerpo_enviado_por_partes_sin_largo_declarado_tambien_se_corta(m):
    def trozos():
        yield b'{"nombre":"'
        for _ in range(40):
            yield b"A" * 100_000

    r = m["c"].post("/cursos", content=trozos(), headers={**m["utp"], "Content-Type": "application/json"})
    assert r.status_code == 413


def test_los_trozos_y_fotos_tienen_un_tope_mayor_que_el_json_pero_no_infinito(m):
    _iniciar_grabacion(m)
    assert _trozo(m, 0, WEBM + b"\x00" * (2 * 1024 * 1024)).status_code < 400  # 2 MB de audio: normal
    assert _trozo(m, 1, b"\x00" * (21 * 1024 * 1024)).status_code == 413
    assert m["c"].post(f"/grabaciones/{m['grabacion_id']}/fotos", content=b"\x00" * (21 * 1024 * 1024), headers={**m["ana"], "Content-Type": "image/png"}).status_code == 413


def test_un_cuerpo_normal_no_se_ve_afectado_por_el_tope(m):
    r = m["c"].post("/cursos", json={"nombre": "9B", "colegio_id": m["colegio_id"]}, headers=m["utp"])
    assert r.status_code == 201


# --- Verbos, rutas raras y cabeceras de respuesta ----------------------------------------------------------------------


def test_verbos_raros_no_dan_500_ni_acceso(m):
    for metodo in ("TRACE", "CONNECT", "PATCH", "PROPFIND", "DEBUG", "FOO"):
        for ruta in ("/usuarios", "/cursos", "/auth/me", "/clases", "/estado", "/salud"):
            resp = m["c"].request(metodo, ruta, headers=m["utp"])
            assert resp.status_code in (404, 405, 400, 501), (metodo, ruta, resp.status_code)


def test_archivos_y_rutas_sensibles_no_se_sirven(m):
    for ruta in ("/../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "//usuarios", "/usuarios/", "/usuarios/../auth/me", "/.env", "/.git/config", "/escuela.db", "/api.py",
                 "/alembic.ini", "/requirements.txt", "/transcriptor-env/pyvenv.cfg", "/static/../.env", "/docs", "/redoc", "/openapi.json", "/%00", "/" + "a" * 20000):
        resp = m["c"].get(ruta)
        assert resp.status_code in (404, 307, 308, 401, 403, 414, 400, 405), (ruta[:40], resp.status_code, resp.text[:80])
        assert "JWT_SECRET" not in resp.text and "sqlite" not in resp.text.lower() and "password_hash" not in resp.text


def test_los_errores_no_muestran_codigo_ni_rutas_del_servidor(m):
    respuestas = [
        m["c"].get("/clases/abc", headers=m["utp"]), m["c"].post("/cursos", content=b"{", headers={**m["utp"], "Content-Type": "application/json"}),
        m["c"].get("/cursos/999999", headers=m["utp"]), m["c"].get("/ruta-que-no-existe"), m["c"].post("/auth/login/staff", json={"rut": "x"}),
    ]
    for r in respuestas:
        assert not ERRORES_DE_BASE.search(r.text) and "/home/" not in r.text and "site-packages" not in r.text, r.text[:200]


def test_cors_no_deja_pasar_a_un_sitio_ajeno(m):
    r = m["c"].options("/usuarios", headers={"Origin": "https://sitio-malo.example", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers} or r.headers["access-control-allow-origin"] != "*"
    assert r.headers.get("access-control-allow-origin") != "https://sitio-malo.example"
    r = m["c"].get("/auth/me", headers={**m["utp"], "Origin": "https://sitio-malo.example"})
    assert r.headers.get("access-control-allow-origin") != "https://sitio-malo.example"
    assert r.headers.get("access-control-allow-credentials") != "true" or r.headers.get("access-control-allow-origin") not in (None, "*")
