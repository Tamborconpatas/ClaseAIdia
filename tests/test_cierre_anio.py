# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Cierre del año escolar en dos tiempos. Al terminar las clases: se borra el material del año y las grabaciones quedan en pausa (los alumnos siguen donde están).
Cuando las grabaciones están por activarse de nuevo (febrero): cada curso pasa a otro o egresa, cada alumno pasa, repite o se fue; se borran las cuentas que ya
no son del colegio, los códigos cambian y se reactivan las grabaciones. El horario se conserva."""
import datetime
import sqlite3

import pytest

from infraestructura.modelos_orm import AlumnoCurso, Bloque, Clase, Colegio, ContenidoClase, Curso, EstadoGrabacion as E, Grabacion, Usuario
from interfaz.api import rutas_cierre_anio
from nucleo.validadores import validar_rut
from servicios import servicio_ajustes, servicio_cierre_anio as sc

CLAVE = "clave-segura-123"
HOY = datetime.date(2026, 11, 27)


def rut(n: int) -> str:
    return next(f"{n}-{dv}" for dv in "0123456789K" if validar_rut(f"{n}-{dv}"))


@pytest.fixture()
def a(cliente, colegio_id, headers_utp):
    """7A, 8A y 4M con alumnos, un horario y clases con material. Devuelve ids y ayudas."""
    utp = headers_utp
    cursos = {n: cliente.post("/cursos", json={"nombre": n, "colegio_id": colegio_id}, headers=utp).json() for n in ("7A", "8A", "4M")}
    prof = cliente.post("/usuarios", json={"rut": "5126663-3", "nombre": "Ana", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, headers=utp).json()["id"]
    bloques = {}
    for dia, (n, c) in enumerate(cursos.items()):  # un día distinto por curso: una profesora no puede estar en dos cursos a la vez
        r = cliente.post(f"/cursos/{c['id']}/bloques", json={"tipo": "CLASE", "asignatura": "Matemática", "profesor_id": prof, "sala": "S1", "dia_semana": dia, "hora_inicio": "08:00", "hora_fin": "08:45"}, headers=utp)
        bloques[n] = r.json()["id"]
    alumnos, k = {}, 0
    for n, nombres in {"7A": ["Sofía", "Tomás"], "8A": ["Valentina", "Matías", "Camila"], "4M": ["Diego", "Javiera"]}.items():
        for nombre in nombres:
            k += 1
            r = cliente.post("/cursos/unirse", json={"codigo_invitacion": cursos[n]["codigo_invitacion"], "rut": rut(21000000 + 37 * k + 1), "nombre": nombre, "pin": "482915"})
            assert r.status_code == 200, r.text
            alumnos[nombre] = cliente.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["id"]
    with cliente.sesion() as db:
        for n, b in bloques.items():
            for d in (400, 30):
                db.add(Clase(bloque_id=b, fecha=HOY - datetime.timedelta(days=d), contenido=ContenidoClase(resumen="R", puntos_clave="- a", hoja_repaso="H", tarjetas=[], transcripcion_texto="t", aprobado=True)))
        db.commit()
    return {"c": cliente, "utp": utp, "cursos": {n: c["id"] for n, c in cursos.items()}, "codigos": {n: c["codigo_invitacion"] for n, c in cursos.items()}, "alumnos": alumnos, "prof": prof, "bloques": bloques}


def plan(a, **extra):
    """7A pasa a 8A, 8A pasa a un 9A nuevo y 4M egresa: el caso normal de fin de año."""
    p = {"cursos": [{"curso_id": a["cursos"]["7A"], "destino_id": a["cursos"]["8A"]}, {"curso_id": a["cursos"]["8A"], "destino_nuevo": "9A"}, {"curso_id": a["cursos"]["4M"], "egresa": True}],
         "repiten": [], "se_van": []}
    p.update(extra)
    return p


def previa(a, p, headers=None):
    return a["c"].post("/cierre-anio/anio-nuevo/vista-previa", json=p, headers=headers or a["utp"])


def cerrar_clases(a, headers=None, confirmo=True):
    """Primer tiempo: al terminar las clases."""
    return a["c"].post("/cierre-anio/cerrar", json={"confirmo": confirmo}, headers=headers or a["utp"])


def cerrar(a, p, headers=None, confirmo=True):
    """Segundo tiempo: el año nuevo (en febrero). Quien llama debe haber cerrado el año antes."""
    return a["c"].post("/cierre-anio/anio-nuevo", json={**p, "confirmo": confirmo}, headers=headers or a["utp"])


def donde(a):
    """nombre del alumno -> nombre de su curso (o None si ya no existe su cuenta)."""
    with a["c"].sesion() as db:
        salida = {}
        for nombre, uid in a["alumnos"].items():
            i = db.query(AlumnoCurso).filter_by(usuario_id=uid).first()
            salida[nombre] = db.get(Curso, i.curso_id).nombre if i else None
        return salida


@pytest.fixture()
def sin_respaldo_real(monkeypatch, tmp_path):
    """La base de las pruebas es de memoria: el respaldo previo se prueba aparte, con un archivo de verdad."""
    monkeypatch.setattr(rutas_cierre_anio, "_base", lambda: None)
    monkeypatch.setattr(servicio_ajustes, "carpeta_de_respaldos", lambda db: tmp_path / "respaldos")


@pytest.fixture()
def b(a, sin_respaldo_real):
    """El año ya está cerrado (primer tiempo hecho): lo que sigue es preparar el año nuevo."""
    assert cerrar_clases(a).status_code == 200
    return a


# --- primer tiempo: cerrar el año al terminar las clases ---------------------------------------------------------------


def test_solo_el_utp_puede_ver_cerrar_o_preparar(a, sin_respaldo_real):
    prof = {"Authorization": "Bearer " + a["c"].post("/auth/login/staff", json={"rut": "5126663-3", "password": CLAVE}).json()["access_token"]}
    p = plan(a)
    assert a["c"].get("/cierre-anio/estado").status_code == 401
    assert a["c"].get("/cierre-anio/estado", headers=prof).status_code == 403
    assert a["c"].post("/cierre-anio/cerrar", json={"confirmo": True}, headers=prof).status_code == 403
    for url in ("/cierre-anio/anio-nuevo/vista-previa", "/cierre-anio/anio-nuevo"):
        assert a["c"].post(url, json={**p, "confirmo": True}).status_code == 401
        assert a["c"].post(url, json={**p, "confirmo": True}, headers=prof).status_code == 403


def test_antes_de_cerrar_el_estado_dice_cuantas_clases_se_borrarian(a, sin_respaldo_real):
    r = a["c"].get("/cierre-anio/estado", headers=a["utp"]).json()
    assert r == {"anio_cerrado": False, "clases_a_borrar": 6, "problemas": []}
    assert donde(a)["Sofía"] == "7A"  # mirar no cambia nada


def test_cerrar_el_anio_borra_las_clases_pausa_las_grabaciones_y_los_alumnos_siguen_donde_estan(a, sin_respaldo_real):
    antes = donde(a)
    codigos = {n: c for n, c in a["codigos"].items()}
    assert cerrar_clases(a, confirmo=False).status_code == 422  # sin confirmar no se hace
    r = cerrar_clases(a)
    assert r.status_code == 200 and r.json()["clases_borradas"] == 6
    assert donde(a) == antes  # los alumnos siguen en su curso: pasan en febrero, no ahora
    with a["c"].sesion() as db:
        assert db.query(Clase).count() == 0 and db.query(ContenidoClase).count() == 0
        assert db.query(Bloque).count() == 3  # el horario se conserva
        assert {c.nombre: c.codigo_invitacion for c in db.query(Curso).all()} == codigos  # y los códigos tampoco cambian todavía
        assert db.query(Colegio).first().anio_cerrado is True
    assert a["c"].get("/ajustes/grabaciones", headers=a["utp"]).json() == {"activas": False, "hasta": None, "anio_cerrado": True}
    assert a["c"].get("/cierre-anio/estado", headers=a["utp"]).json()["anio_cerrado"] is True


def test_el_anio_no_se_cierra_dos_veces(b):
    r = cerrar_clases(b)
    assert r.status_code == 409 and "ya está cerrado" in r.json()["detail"]


def test_con_una_clase_grabandose_o_procesandose_no_se_cierra_el_anio(a, sin_respaldo_real):
    with a["c"].sesion() as db:
        db.add(Grabacion(clase=db.query(Clase).first(), estado=E.PROCESANDO, corte_en=datetime.datetime(2026, 1, 1)))
        db.commit()
    est = a["c"].get("/cierre-anio/estado", headers=a["utp"]).json()
    assert any("grabándose o procesándose" in x for x in est["problemas"])
    r = cerrar_clases(a)
    assert r.status_code == 409 and "grabándose o procesándose" in r.json()["detail"]
    with a["c"].sesion() as db:
        assert db.query(Clase).count() == 6  # no se borró nada


# --- con el año cerrado no se puede volver a grabar sin preparar el año nuevo ---------------------------------------------


def test_con_el_anio_cerrado_las_grabaciones_no_se_reactivan_a_mano(b):
    r = b["c"].put("/ajustes/grabaciones", json={"activas": True}, headers=b["utp"])
    assert r.status_code == 409 and "preparar el año nuevo" in r.json()["detail"]
    assert b["c"].get("/ajustes/grabaciones", headers=b["utp"]).json()["activas"] is False
    # ponerles una fecha de regreso sí se puede: sirve de recordatorio, no las reactiva
    regreso = datetime.date.today() + datetime.timedelta(days=30)
    assert b["c"].put("/ajustes/grabaciones", json={"activas": False, "hasta": regreso.isoformat()}, headers=b["utp"]).status_code == 200


def test_la_fecha_de_regreso_no_reactiva_sola_con_el_anio_cerrado_y_el_panel_avisa(b):
    regreso = datetime.date.today() + datetime.timedelta(days=30)
    b["c"].put("/ajustes/grabaciones", json={"activas": False, "hasta": regreso.isoformat()}, headers=b["utp"])
    with b["c"].sesion() as db:
        assert servicio_ajustes.reactivar_si_toca(db, regreso + datetime.timedelta(days=1)) == 0  # llegó la fecha y no se reactiva
        assert db.query(Colegio).first().grabaciones_activas is False
    alertas = b["c"].get("/estado", headers=b["utp"]).json()["alertas"]
    assert any(x["tema"] == "grabaciones" and x["nivel"] == "aviso" and "prepara el año nuevo" in x["texto"] for x in alertas)
    # el día que llega la fecha, el aviso pasa a urgente
    with b["c"].sesion() as db:
        db.query(Colegio).first().grabaciones_hasta = datetime.date.today()
        db.commit()
    alertas = b["c"].get("/estado", headers=b["utp"]).json()["alertas"]
    assert any(x["tema"] == "grabaciones" and x["nivel"] == "critico" and "Llegó la fecha de regreso" in x["texto"] for x in alertas)


# --- segundo tiempo: preparar el año nuevo (los alumnos cambian de curso en febrero) --------------------------------------


def test_sin_haber_cerrado_el_anio_no_se_puede_preparar_el_nuevo(a, sin_respaldo_real):
    antes = donde(a)
    r = cerrar(a, plan(a))
    assert r.status_code == 409 and "Primero hay que cerrar el año" in r.json()["detail"]
    assert donde(a) == antes


def test_la_vista_previa_no_cambia_nada_y_cuenta_lo_que_pasaria(b):
    antes = donde(b)
    r = previa(b, plan(b, repiten=[b["alumnos"]["Matías"]], se_van=[b["alumnos"]["Camila"]])).json()
    assert r["problemas"] == []
    # 7A: 2 pasan a 8A; 8A: Valentina pasa a 9A, Matías repite, Camila se fue; 4M: 2 egresan
    assert r["resumen"] == {"pasan": 3, "repiten": 1, "se_van": 1, "egresan": 2, "cuentas_a_borrar": 3, "cursos_nuevos": ["9A"], "codigos_nuevos": 4}
    assert {c["curso"]: c["destino"] for c in r["cursos"]} == {"7A": "8A", "8A": "9A", "4M": "Egresan"}
    assert donde(b) == antes
    with b["c"].sesion() as db:
        assert db.query(Curso).count() == 3 and db.query(Colegio).first().anio_cerrado is True


def test_preparar_el_anio_pasa_repite_borra_reactiva_y_deja_el_horario(b):
    r = cerrar(b, plan(b, repiten=[b["alumnos"]["Matías"]], se_van=[b["alumnos"]["Camila"]]))
    assert r.status_code == 200, r.text
    # el movimiento se calcula con la foto de antes: 7A→8A y 8A→9A a la vez no se pisan
    assert donde(b) == {"Sofía": "8A", "Tomás": "8A", "Valentina": "9A", "Matías": "8A", "Camila": None, "Diego": None, "Javiera": None}
    with b["c"].sesion() as db:
        assert db.query(Bloque).count() == 3  # el horario se conserva
        assert db.query(Curso).filter_by(nombre="9A").one().cupo == 45
        assert db.query(Usuario).filter(Usuario.id.in_([b["alumnos"]["Camila"], b["alumnos"]["Diego"]])).count() == 0  # cuentas borradas
        assert db.query(Colegio).first().anio_cerrado is False
    assert b["c"].get("/ajustes/grabaciones", headers=b["utp"]).json() == {"activas": True, "hasta": None, "anio_cerrado": False}  # ya se puede grabar


def test_los_codigos_nuevos_se_entregan_y_el_viejo_ya_no_sirve(b):
    r = cerrar(b, plan(b)).json()
    with b["c"].sesion() as db:
        en_base = {c.nombre: c.codigo_invitacion for c in db.query(Curso).all()}
    assert {x["curso"]: x["codigo"] for x in r["codigos"]} == en_base  # incluidos los cursos nuevos
    assert set(en_base) == {"7A", "8A", "4M", "9A"} and all(en_base[n] != b["codigos"][n] for n in ("7A", "8A", "4M"))
    viejo = b["c"].post("/cursos/unirse", json={"codigo_invitacion": b["codigos"]["8A"], "rut": rut(22000007), "nombre": "Intruso", "pin": "482915"})
    assert viejo.status_code in (400, 404, 422)
    nuevo = b["c"].post("/cursos/unirse", json={"codigo_invitacion": en_base["8A"], "rut": rut(22000007), "nombre": "Nuevo", "pin": "482915"})
    assert nuevo.status_code == 200  # un alumno nuevo del año se inscribe con el código nuevo


def test_la_cuenta_borrada_ya_no_entra_y_la_de_quien_pasa_sigue_funcionando(b):
    tokens = {n: b["c"].post("/auth/login/alumno", json={"rut": rut(21000000 + 37 * k + 1), "pin": "482915"}).json()["access_token"] for k, n in enumerate(b["alumnos"], 1)}
    cerrar(b, plan(b, se_van=[b["alumnos"]["Matías"]]))
    h = lambda n: {"Authorization": f"Bearer {tokens[n]}"}  # noqa: E731
    assert b["c"].get("/clases", headers=h("Diego")).status_code == 401  # egresó: su sesión abierta ya no sirve
    assert b["c"].get("/clases", headers=h("Matías")).status_code == 401  # se fue del colegio
    assert b["c"].get("/clases", headers=h("Sofía")).status_code == 200  # pasó de curso: sigue entrando


def test_un_alumno_que_repite_en_el_ultimo_curso_se_queda_y_egresan_los_demas(b):
    cerrar(b, plan(b, repiten=[b["alumnos"]["Javiera"]]))
    assert donde(b)["Javiera"] == "4M" and donde(b)["Diego"] is None


def test_un_curso_puede_pasar_a_uno_que_ya_existe_y_dos_cursos_a_uno_nuevo(b):
    p = {"cursos": [{"curso_id": b["cursos"]["7A"], "destino_nuevo": "Mixto"}, {"curso_id": b["cursos"]["8A"], "destino_nuevo": "mixto"}, {"curso_id": b["cursos"]["4M"], "egresa": True}], "repiten": [], "se_van": []}
    assert cerrar(b, p).status_code == 200
    with b["c"].sesion() as db:
        assert db.query(Curso).filter(Curso.nombre.in_(["Mixto", "mixto"])).count() == 1  # un solo curso nuevo
    assert {v for k, v in donde(b).items() if k in ("Sofía", "Tomás", "Valentina", "Matías", "Camila")} == {"Mixto"}


@pytest.mark.parametrize("mal, texto", [
    ("falta", "Falta decidir"),
    ("mismo", "no puede pasar a sí mismo"),
    ("dos", "Elige un solo destino"),
    ("ninguno", "Elige un solo destino"),
    ("existe", "Ya existe un curso llamado"),
    ("ajeno", "no es de este colegio"),
    ("repite_y_se_fue", "repetir y a la vez"),
    ("desconocido", "no está en ningún curso"),
    ("personal", "no está en ningún curso"),
    ("personal_inscrito", "no es alumno"),
])
def test_un_plan_con_problemas_no_se_puede_aplicar_y_no_cambia_nada(b, mal, texto):
    p, c = plan(b), b["cursos"]
    s = b["alumnos"]["Sofía"]
    if mal == "falta":
        p["cursos"].pop()  # sin decidir 4M
    elif mal == "mismo":
        p["cursos"][0]["destino_id"] = c["7A"]
    elif mal == "dos":
        p["cursos"][0]["egresa"] = True
    elif mal == "ninguno":
        p["cursos"][0] = {"curso_id": c["7A"]}
    elif mal == "existe":
        p["cursos"][1] = {"curso_id": c["8A"], "destino_nuevo": "7a"}
    elif mal == "ajeno":
        p["cursos"][0]["destino_id"] = 999999
    elif mal == "repite_y_se_fue":
        p["repiten"], p["se_van"] = [s], [s]
    elif mal == "desconocido":
        p["repiten"] = [999999]
    elif mal == "personal":
        p["se_van"] = [b["prof"]]
    elif mal == "personal_inscrito":  # una cuenta inscrita en un curso que además es de personal: nunca se borra por este camino
        from infraestructura.modelos_orm import RolNombre, UsuarioRol

        with b["c"].sesion() as db:
            db.add(UsuarioRol(usuario_id=s, rol=RolNombre.PROFESOR))
            db.commit()
        p["se_van"] = [s]
    antes = donde(b)
    r = previa(b, p).json()
    assert any(texto in x for x in r["problemas"]), r["problemas"]
    resp = cerrar(b, p)
    assert resp.status_code == 409 and texto in resp.json()["detail"]
    assert donde(b) == antes
    with b["c"].sesion() as db:
        assert db.query(Colegio).first().anio_cerrado is True  # sigue cerrado: no se reactivó nada


def test_el_cupo_del_curso_de_destino_se_respeta(b):
    b["c"].put(f"/cursos/{b['cursos']['8A']}/cupo", json={"cupo": 3}, headers=b["utp"])  # 8A: 3 alumnos, y le llegarían 2 más de 7A
    p = {"cursos": [{"curso_id": b["cursos"]["7A"], "destino_id": b["cursos"]["8A"]}, {"curso_id": b["cursos"]["8A"], "destino_nuevo": "9A"}, {"curso_id": b["cursos"]["4M"], "egresa": True}],
         "repiten": [b["alumnos"][n] for n in ("Valentina", "Matías", "Camila")], "se_van": []}
    r = previa(b, p).json()
    assert any("quedaría con 5 alumnos y su máximo es 3" in x for x in r["problemas"]), r["problemas"]
    b["c"].put(f"/cursos/{b['cursos']['8A']}/cupo", json={"cupo": 5}, headers=b["utp"])
    assert previa(b, p).json()["problemas"] == []


def test_sin_confirmar_no_se_prepara_el_anio_nuevo(b):
    assert cerrar(b, plan(b), confirmo=False).status_code == 422
    assert donde(b)["Sofía"] == "7A"


def test_otro_colegio_no_puede_tocar_los_cursos_de_este(b, otro_colegio):
    antes = donde(b)
    r = previa(b, plan(b), headers=otro_colegio[1]).json()
    assert any("no es de este colegio" in x for x in r["problemas"]) and any("Primero hay que cerrar el año" in x for x in r["problemas"])  # su año ni siquiera está cerrado
    assert cerrar(b, plan(b), headers=otro_colegio[1]).status_code == 409
    assert cerrar_clases(b, headers=otro_colegio[1]).status_code == 200  # cerrar SU año no toca nada de este colegio
    assert donde(b) == antes
    with b["c"].sesion() as db:
        assert db.query(Curso).count() == 3 and db.query(Colegio).filter_by(anio_cerrado=True).count() == 2


def test_antes_de_cada_paso_se_hace_un_respaldo_aparte_que_no_se_borra_solo(a, monkeypatch, tmp_path):
    base = tmp_path / "escuela.db"
    con = sqlite3.connect(base)
    con.execute("create table t (x)"), con.execute("insert into t values (42)"), con.commit(), con.close()
    monkeypatch.setattr(rutas_cierre_anio, "_base", lambda: base)
    monkeypatch.setattr(servicio_ajustes, "carpeta_de_respaldos", lambda db: tmp_path / "respaldos")
    r1 = cerrar_clases(a)
    assert r1.status_code == 200
    r2 = cerrar(a, plan(a), confirmo=True)
    assert r2.status_code == 200
    for r in (r1, r2):
        nombre = r.json()["respaldo"]
        assert nombre.startswith("cierre-de-anio-") and (tmp_path / "respaldos" / nombre).is_file()
        assert sqlite3.connect(tmp_path / "respaldos" / nombre).execute("select x from t").fetchone() == (42,)  # es una copia de verdad
    # la limpieza de los respaldos diarios (escuela-*.db) no las ve
    from servicios import servicio_respaldo

    for d in range(1, 6):
        servicio_respaldo.respaldar_si_toca(base, tmp_path / "respaldos", datetime.datetime(2026, 12, d), conservar=2)
    assert len(list((tmp_path / "respaldos").glob("cierre-de-anio-*.db"))) >= 1


def test_las_clases_se_borran_por_tandas_y_si_el_cierre_falla_al_final_se_puede_repetir(a, sin_respaldo_real, monkeypatch):
    monkeypatch.setattr(sc, "LOTE", 2)  # 6 clases en 3 tandas
    real = servicio_ajustes.cambiar_grabaciones
    fallos = []

    def falla_una_vez(*args, **kw):
        if not fallos:
            fallos.append(1)
            raise RuntimeError("se cortó")
        return real(*args, **kw)

    monkeypatch.setattr(servicio_ajustes, "cambiar_grabaciones", falla_una_vez)
    with pytest.raises(RuntimeError):
        cerrar_clases(a)
    with a["c"].sesion() as db:
        assert db.query(Clase).count() == 0  # las clases ya se habían borrado (por tandas)...
    r = cerrar_clases(a)  # ...y se repite el cierre: ahora termina de marcar el año
    assert r.status_code == 200 and r.json()["clases_borradas"] == 0


def test_si_preparar_el_anio_falla_al_final_nada_queda_a_medias_y_se_puede_repetir(b, monkeypatch):
    real = servicio_ajustes.cambiar_grabaciones
    fallos = []

    def falla_una_vez(*args, **kw):
        if not fallos:
            fallos.append(1)
            raise RuntimeError("se cortó")
        return real(*args, **kw)

    monkeypatch.setattr(servicio_ajustes, "cambiar_grabaciones", falla_una_vez)
    with pytest.raises(RuntimeError):
        cerrar(b, plan(b))
    assert donde(b)["Sofía"] == "7A" and donde(b)["Diego"] == "4M"  # ningún alumno se aplicó a medias
    with b["c"].sesion() as db:
        assert db.query(Curso).count() == 3  # ni se creó el curso nuevo
    assert cerrar(b, plan(b)).status_code == 200
    assert donde(b)["Sofía"] == "8A" and donde(b)["Diego"] is None


def test_dos_respaldos_del_cierre_en_el_mismo_instante_no_se_pisan(tmp_path):
    from servicios import servicio_respaldo

    base = tmp_path / "escuela.db"
    con = sqlite3.connect(base)
    con.execute("create table t (x)"), con.commit(), con.close()
    ahora = datetime.datetime(2026, 12, 15, 12, 0, 0)
    copias = {servicio_respaldo.respaldar_antes_del_cierre(base, tmp_path / "r", ahora) for _ in range(3)}
    assert len(copias) == 3 and all(c.is_file() for c in copias)


def test_un_colegio_sin_alumnos_ni_clases_cierra_y_prepara_el_anio_y_vuelve_a_grabar(cliente, colegio_id, headers_utp, monkeypatch, tmp_path):
    monkeypatch.setattr(rutas_cierre_anio, "_base", lambda: None)
    monkeypatch.setattr(servicio_ajustes, "carpeta_de_respaldos", lambda db: tmp_path / "respaldos")
    assert cliente.get("/cierre-anio/estado", headers=headers_utp).json() == {"anio_cerrado": False, "clases_a_borrar": 0, "problemas": []}
    assert cliente.post("/cierre-anio/cerrar", json={"confirmo": True}, headers=headers_utp).json()["clases_borradas"] == 0
    assert cliente.put("/ajustes/grabaciones", json={"activas": True}, headers=headers_utp).status_code == 409  # sigue sin poderse a mano
    r = cliente.post("/cierre-anio/anio-nuevo", json={"cursos": [], "repiten": [], "se_van": [], "confirmo": True}, headers=headers_utp)
    assert r.status_code == 200 and r.json()["codigos"] == []
    assert cliente.get("/ajustes/grabaciones", headers=headers_utp).json()["activas"] is True


def test_al_cerrar_el_anio_no_queda_audio_de_una_clase_con_reintento_pendiente(a, sin_respaldo_real, monkeypatch, tmp_path):
    """Una clase que falló conserva su audio mientras queden reintentos: si el año se cierra, ese audio no puede sobrevivir a la clase."""
    from servicios import servicio_grabacion as sg

    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    with a["c"].sesion() as db:
        g = Grabacion(clase=db.query(Clase).first(), estado=E.ERROR, corte_en=datetime.datetime(2026, 1, 1), reintento_en=datetime.datetime(2099, 1, 1))
        db.add(g)
        db.commit()
        carpeta = tmp_path / "audio" / str(g.id)
        carpeta.mkdir(parents=True)
        (carpeta / "trozo-0.webm").write_bytes(b"voz de una clase")
    assert (carpeta / "trozo-0.webm").exists()
    assert cerrar_clases(a).status_code == 200
    assert not carpeta.exists()  # el audio se fue con la clase


def test_compactar_devuelve_el_espacio_de_lo_borrado_y_nunca_falla(tmp_path):
    from servicios import servicio_respaldo

    base = tmp_path / "escuela.db"
    con = sqlite3.connect(base)
    con.execute("create table t (x text)")
    con.executemany("insert into t values (?)", [("x" * 10000,) for _ in range(500)])
    con.commit()
    con.execute("delete from t")
    con.commit()
    con.close()
    antes = base.stat().st_size
    assert servicio_respaldo.compactar(base) is True and base.stat().st_size < antes / 10
    assert servicio_respaldo.compactar(None) is False and servicio_respaldo.compactar(tmp_path / "no-existe.db") is False  # sin base: no hace nada
