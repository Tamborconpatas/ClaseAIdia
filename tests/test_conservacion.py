# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""El material de una clase se guarda un año: pasado ese plazo se borra todo lo que quedó de ella; el horario y las clases recientes no se tocan."""
import datetime

from infraestructura.modelos_orm import Bloque, Clase, ContenidoClase, EstadoGrabacion as E, Grabacion
from servicios import servicio_conservacion as sc
from test_clases import esc  # noqa: F401

HOY = datetime.date(2026, 11, 27)
MATERIAL = {"resumen": "R", "puntos_clave": "- a", "hoja_repaso": "H", "tarjetas": [], "transcripcion_texto": "t", "aprobado": True}


def _clase(db, bloque_id, dias_atras, estado=None):
    c = Clase(bloque_id=bloque_id, fecha=HOY - datetime.timedelta(days=dias_atras), contenido=ContenidoClase(**MATERIAL))
    if estado is not None:
        c.grabacion = Grabacion(estado=estado, corte_en=datetime.datetime(2026, 1, 1))
    db.add(c)
    db.flush()
    return c.id


def test_se_borran_las_clases_de_mas_de_un_ano_con_todo_su_material_y_las_recientes_quedan(cliente, esc):  # noqa: F811
    b = esc["bloques"]["mat"]
    with cliente.sesion() as db:
        vieja, justo, reciente = _clase(db, b, 366, E.TERMINADA), _clase(db, b, 365), _clase(db, b, 30)
        db.commit()
        assert sc.borrar_vencidas(db, HOY) == 1
        quedan = {c.id for c in db.query(Clase).filter(Clase.id.in_([vieja, justo, reciente]))}
        assert quedan == {justo, reciente}  # justo un año todavía se conserva
        assert db.query(ContenidoClase).filter_by(clase_id=vieja).count() == 0
        assert db.query(Grabacion).filter_by(clase_id=vieja).count() == 0
        assert db.get(Bloque, b) is not None  # el horario no se toca


def test_una_clase_que_todavia_se_procesa_nunca_se_borra(cliente, esc):  # noqa: F811
    with cliente.sesion() as db:
        c = _clase(db, esc["bloques"]["mat"], 400, E.PROCESANDO)
        db.commit()
        assert sc.borrar_vencidas(db, HOY) == 0
        assert db.get(Clase, c) is not None


def test_la_limpieza_corre_como_mucho_una_vez_al_dia(cliente, esc, monkeypatch):  # noqa: F811
    llamadas = []
    monkeypatch.setattr(sc, "borrar_vencidas", lambda db, hoy=None: llamadas.append(1) or 0)
    monkeypatch.setattr(sc, "ultima_limpieza", None)
    t = datetime.datetime(2026, 11, 27, 3, 0)
    with cliente.sesion() as db:
        sc.limpiar_si_toca(db, t)
        sc.limpiar_si_toca(db, t + datetime.timedelta(hours=5))
        assert len(llamadas) == 1
        sc.limpiar_si_toca(db, t + datetime.timedelta(hours=25))
        assert len(llamadas) == 2


def test_cada_colegio_tiene_su_plazo_y_la_vista_previa_cuenta_lo_que_se_borraria(cliente, esc):  # noqa: F811
    from infraestructura.modelos_orm import Colegio

    b = esc["bloques"]["mat"]
    with cliente.sesion() as db:
        _clase(db, b, 200), _clase(db, b, 100), _clase(db, b, 10)
        db.commit()
        colegio = db.query(Colegio).first()
        assert sc.contar_vencidas(db, colegio, 365, HOY) == 0
        assert sc.contar_vencidas(db, colegio, 150, HOY) == 1  # solo la de 200 días
        assert sc.contar_vencidas(db, colegio, 90, HOY) == 2
        colegio.dias_conservacion = 150
        db.commit()
        assert sc.borrar_vencidas(db, HOY) == 1  # con el plazo de ese colegio, no con el de un año
        assert db.query(Clase).filter(Clase.bloque_id == b, Clase.fecha < HOY - datetime.timedelta(days=150)).count() == 0


def test_acortar_el_plazo_borra_al_instante_lo_vencido_y_la_respuesta_dice_cuanto(cliente, esc):  # noqa: F811
    hoy = datetime.date.today()
    b = esc["bloques"]["mat"]
    with cliente.sesion() as db:
        for dias in (400, 200, 100, 10):
            c = Clase(bloque_id=b, fecha=hoy - datetime.timedelta(days=dias), contenido=ContenidoClase(**MATERIAL))
            db.add(c)
        db.commit()
    previa = cliente.get("/ajustes/conservacion?dias=150", headers=esc["utp"]).json()
    assert previa["se_borrarian"] == 2 and previa["borradas"] == 0  # la vista previa no borra nada
    r = cliente.put("/ajustes/conservacion", json={"dias": 150}, headers=esc["utp"]).json()
    assert r["borradas"] == 2 and r["se_borrarian"] == 0
    with cliente.sesion() as db:
        fechas = sorted((hoy - c.fecha).days for c in db.query(Clase).filter(Clase.fecha >= hoy - datetime.timedelta(days=1000), Clase.bloque_id == b))
        assert 400 not in fechas and 200 not in fechas and 100 in fechas and 10 in fechas


def test_el_borrado_va_por_lotes_y_termina_con_muchas_clases(cliente, esc, monkeypatch):  # noqa: F811
    monkeypatch.setattr(sc, "LOTE", 3)
    b = esc["bloques"]["mat"]
    with cliente.sesion() as db:
        for _ in range(10):
            _clase(db, b, 400)
        _clase(db, b, 5, E.PROCESANDO)
        db.commit()
        assert sc.borrar_vencidas(db, HOY) == 10  # cuatro tandas de 3, 3, 3 y 1; la reciente queda
        assert db.query(Clase).filter(Clase.bloque_id == b, Clase.fecha < HOY - datetime.timedelta(days=365)).count() == 0


def test_al_borrar_por_antiguedad_tampoco_queda_audio_suelto(cliente, esc, monkeypatch, tmp_path):  # noqa: F811
    from servicios import servicio_grabacion as sg

    monkeypatch.setattr(sg, "CARPETA_AUDIO", tmp_path / "audio")
    with cliente.sesion() as db:
        c = _clase(db, esc["bloques"]["mat"], 400, E.ERROR)
        db.commit()
        g = db.query(Grabacion).filter_by(clase_id=c).one()
        carpeta = tmp_path / "audio" / str(g.id)
        carpeta.mkdir(parents=True)
        (carpeta / "trozo-0.webm").write_bytes(b"voz")
        assert sc.borrar_vencidas(db, HOY) == 1
        assert not carpeta.exists()
