import datetime
import sqlite3

from servicios.servicio_respaldo import respaldar_si_toca

DIA = datetime.datetime(2026, 10, 2, 3, 0)


def _base(ruta):
    con = sqlite3.connect(ruta)
    con.execute("create table t (x)"), con.execute("insert into t values (42)")
    con.commit(), con.close()
    return ruta


def test_copia_el_contenido_una_vez_al_dia(tmp_path):
    origen = _base(tmp_path / "escuela.db")
    r = respaldar_si_toca(origen, tmp_path / "resp", DIA)
    assert r.name == "escuela-2026-10-02.db" and sqlite3.connect(r).execute("select x from t").fetchone() == (42,)
    assert respaldar_si_toca(origen, tmp_path / "resp", DIA + datetime.timedelta(hours=5)) is None  # ya hay una de hoy
    assert respaldar_si_toca(origen, tmp_path / "resp", DIA + datetime.timedelta(days=1)).name == "escuela-2026-10-03.db"


def test_conserva_solo_los_ultimos_dias_y_no_deja_copias_parciales(tmp_path):
    origen = _base(tmp_path / "escuela.db")
    for d in range(5):
        respaldar_si_toca(origen, tmp_path / "resp", DIA + datetime.timedelta(days=d), conservar=3)
    assert [p.name for p in sorted((tmp_path / "resp").iterdir())] == ["escuela-2026-10-04.db", "escuela-2026-10-05.db", "escuela-2026-10-06.db"]


def test_sin_base_no_hace_nada(tmp_path):
    assert respaldar_si_toca(tmp_path / "no_existe.db", tmp_path / "resp", DIA) is None and not (tmp_path / "resp").exists()


def test_el_servidor_respalda_la_base_al_vigilar(tmp_path, monkeypatch):
    from sqlalchemy import create_engine

    from infraestructura import basedatos
    from interfaz.api import aplicacion

    origen = _base(tmp_path / "escuela.db")
    monkeypatch.setattr(basedatos, "engine", create_engine(f"sqlite:///{origen}"))
    monkeypatch.setenv("CARPETA_RESPALDOS", str(tmp_path / "resp"))
    aplicacion._respaldar()
    assert len(list((tmp_path / "resp").glob("escuela-*.db"))) == 1


def test_cada_pasada_del_vigilante_intenta_respaldar(monkeypatch):
    import asyncio
    import contextlib

    from interfaz.api import aplicacion

    llamadas = []
    monkeypatch.setattr(aplicacion, "INTERVALO_VIGILANTE_S", 0.01)
    monkeypatch.setattr(aplicacion.servicio_grabacion, "vigilar", lambda *a: None)
    monkeypatch.setattr(aplicacion, "_respaldar", lambda: llamadas.append(1))

    async def correr():
        t = asyncio.create_task(aplicacion._vigilante(contextlib.nullcontext))
        await asyncio.sleep(0.2)
        t.cancel()

    asyncio.run(correr())
    assert llamadas
