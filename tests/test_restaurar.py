# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Un respaldo que nunca se restauró es solo una esperanza: se prueba restaurar de verdad, y que un respaldo malo no toque nada."""
import datetime
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infraestructura.basedatos import Base
from infraestructura.modelos_orm import Bloque, Clase, Colegio, ContenidoClase, Curso, RolNombre, TipoBloque, Usuario, UsuarioRol
from infraestructura.seguridad import hashear_secreto, verificar_secreto
from scripts import restaurar_respaldo as rr
from servicios import servicio_respaldo as sr

DIA = datetime.datetime(2026, 10, 2, 3, 0)
AHORA = datetime.datetime(2026, 10, 3, 9, 30, 15)
CLAVE = "clave-segura-123"


def migrar(ruta, hasta="head"):
    """Crea el esquema como en una instalación real: con las migraciones (así queda registrada su versión)."""
    from alembic import command
    from alembic.config import Config

    anterior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(ruta).as_posix()}"  # alembic/env.py lo lee de aquí
    try:
        configuracion = Config(str(rr.RAIZ / "alembic.ini"))
        configuracion.set_main_option("script_location", str(rr.RAIZ / "alembic"))
        command.upgrade(configuracion, hasta)
    finally:
        if anterior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = anterior
    return configuracion


def crear_base(ruta, con_migraciones=True):
    """Una base real con lo que importa: colegio, UTP con su contraseña, curso, bloque y una clase con su material."""
    motor = create_engine(f"sqlite:///{ruta}")
    if con_migraciones:
        migrar(ruta)
    else:
        Base.metadata.create_all(motor)  # como la base de demostración: sin historial de migraciones
    with sessionmaker(bind=motor)() as db:
        colegio = Colegio(nombre="Liceo de Prueba")
        utp = Usuario(rut="7654321-6", nombre="Carolina", colegio=colegio, password_hash=hashear_secreto(CLAVE))
        utp.roles = [UsuarioRol(rol=RolNombre.UTP)]
        curso = Curso(nombre="8A", colegio=colegio, codigo_invitacion="ABC123")
        bloque = Bloque(curso=curso, tipo=TipoBloque.CLASE, asignatura="Matemática", dia_semana=0, hora_inicio=datetime.time(8), hora_fin=datetime.time(9))
        clase = Clase(bloque=bloque, fecha=datetime.date(2026, 9, 28))
        clase.contenido = ContenidoClase(transcripcion_texto="Hoy vimos fracciones.", resumen="Resumen de fracciones", puntos_clave="- uno", hoja_repaso="Repaso", tarjetas=[{"pregunta": "¿P?", "respuesta": "R"}], aprobado=True)
        db.add_all([utp, clase])
        db.commit()
    motor.dispose()
    return ruta


def contenido(ruta):
    """Lo que hay en la base, para comparar antes y después."""
    con = sqlite3.connect(ruta)
    try:
        return {
            "colegio": con.execute("select nombre from colegios").fetchall(),
            "utp": con.execute("select rut, nombre, password_hash from usuarios").fetchall(),
            "cursos": con.execute("select nombre, codigo_invitacion from cursos").fetchall(),
            "resumen": con.execute("select resumen, transcripcion_texto from contenido_clases").fetchall(),
        }
    finally:
        con.close()


# --- verificar -----------------------------------------------------------------------------------


def test_un_respaldo_bueno_pasa_la_verificacion(tmp_path):
    copia = sr.respaldar_si_toca(crear_base(tmp_path / "escuela.db"), tmp_path / "resp", DIA)
    sr.verificar(copia)  # no lanza


@pytest.mark.parametrize("estropear,dice", [
    ("falta", "No existe el respaldo"),
    ("basura", "no se puede leer como base de datos"),
    ("cortada", "no se puede leer como base de datos|está dañado"),
    ("ajena", "no parece ser de ClaseAIdia"),
])
def test_un_respaldo_malo_se_rechaza_con_una_explicacion(tmp_path, estropear, dice):
    copia = sr.respaldar_si_toca(crear_base(tmp_path / "escuela.db"), tmp_path / "resp", DIA)
    if estropear == "falta":
        copia = tmp_path / "resp" / "escuela-2000-01-01.db"
    elif estropear == "basura":
        copia.write_bytes(b"esto no es una base de datos" * 100)
    elif estropear == "cortada":
        copia.write_bytes(copia.read_bytes()[: len(copia.read_bytes()) // 3])
    elif estropear == "ajena":
        copia.unlink()
        con = sqlite3.connect(copia)
        con.execute("create table otra_cosa (x)"), con.commit(), con.close()
    with pytest.raises(sr.ErrorRespaldo, match=dice):
        sr.verificar(copia)


# --- restaurar -------------------------------------------------------------------------------------


def test_restaurar_devuelve_la_base_al_estado_del_respaldo_y_conserva_la_danada(tmp_path):
    base = crear_base(tmp_path / "escuela.db")
    antes = contenido(base)
    copia = sr.respaldar_si_toca(base, tmp_path / "resp", DIA)
    # el desastre: se borra casi todo y se estropea la contraseña
    con = sqlite3.connect(base)
    con.execute("PRAGMA foreign_keys=OFF")
    con.execute("delete from contenido_clases"), con.execute("delete from cursos"), con.execute("update usuarios set password_hash = 'roto'")
    con.commit(), con.close()
    assert contenido(base) != antes

    anterior = sr.restaurar(copia, base, AHORA)

    assert contenido(base) == antes  # todo volvió, contraseña incluida
    assert anterior.name == "escuela-antes-de-restaurar-20261003-093015.db"
    assert contenido(anterior)["utp"][0][2] == "roto"  # la versión dañada no se perdió: queda para quien la quiera revisar
    assert sqlite3.connect(base).execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    assert not list(tmp_path.glob("*.restaurando"))  # sin archivos temporales


def test_la_contrasena_restaurada_sigue_sirviendo(tmp_path):
    base = crear_base(tmp_path / "escuela.db")
    copia = sr.respaldar_si_toca(base, tmp_path / "resp", DIA)
    sr.restaurar(copia, base, AHORA)
    (hash_,) = sqlite3.connect(base).execute("select password_hash from usuarios").fetchone()
    assert verificar_secreto(CLAVE, hash_)


def test_restaurar_sin_base_previa_la_crea_y_no_hay_nada_que_conservar(tmp_path):
    copia = sr.respaldar_si_toca(crear_base(tmp_path / "escuela.db"), tmp_path / "resp", DIA)
    destino = tmp_path / "nueva" / "escuela.db"
    destino.parent.mkdir()
    assert sr.restaurar(copia, destino, AHORA) is None
    assert contenido(destino) == contenido(copia)


def test_un_respaldo_malo_no_toca_la_base_actual(tmp_path):
    base = crear_base(tmp_path / "escuela.db")
    antes = (base.read_bytes(), contenido(base))
    mala = tmp_path / "resp" / "escuela-2026-10-01.db"
    mala.parent.mkdir()
    mala.write_bytes(b"basura" * 50)
    with pytest.raises(sr.ErrorRespaldo):
        sr.restaurar(mala, base, AHORA)
    assert (base.read_bytes(), contenido(base)) == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ["escuela.db", "resp"]  # ni siquiera quedó la base anterior movida


def test_se_van_los_restos_de_la_base_anterior(tmp_path):
    base = crear_base(tmp_path / "escuela.db")
    copia = sr.respaldar_si_toca(base, tmp_path / "resp", DIA)
    for resto in ("-wal", "-shm", "-journal"):
        (tmp_path / f"escuela.db{resto}").write_bytes(b"resto de la base anterior")
    sr.restaurar(copia, base, AHORA)
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("escuela.db-")]


def test_un_respaldo_hecho_con_la_base_encendida_tambien_se_restaura(tmp_path):
    """La copia en caliente es la que hace el servidor mientras atiende gente: con alguien escribiendo, la copia debe servir."""
    base = crear_base(tmp_path / "escuela.db")
    abierta = sqlite3.connect(base)
    abierta.execute("BEGIN"), abierta.execute("update colegios set nombre = 'En medio de un cambio'")
    copia = sr.respaldar_si_toca(base, tmp_path / "resp", DIA)  # con una transacción abierta sin confirmar
    abierta.rollback(), abierta.close()
    sr.verificar(copia)
    sr.restaurar(copia, base, AHORA)
    assert contenido(base)["colegio"] == [("Liceo de Prueba",)]  # solo lo confirmado, no lo que estaba a medias


def test_un_respaldo_con_paginas_danadas_pero_cabecera_valida_se_rechaza(tmp_path):
    """Lo que un archivo cortado o de basura no muestra: el archivo abre, pero por dentro está roto (un sector malo del disco)."""
    copia = sr.respaldar_si_toca(crear_base(tmp_path / "escuela.db"), tmp_path / "resp", DIA)
    datos = bytearray(copia.read_bytes())
    for pagina in range(3, len(datos) // 4096 - 1):  # todas las páginas menos la cabecera y las primeras
        datos[pagina * 4096: pagina * 4096 + 64] = bytes([255]) * 64
    copia.write_bytes(bytes(datos))
    with pytest.raises(sr.ErrorRespaldo, match="no se puede leer como base de datos|está dañado"):
        sr.verificar(copia)


def test_si_la_revision_de_integridad_informa_problemas_el_respaldo_se_rechaza(tmp_path, monkeypatch):
    """El archivo abre y tiene las tablas, pero SQLite dice que por dentro hay daños (un índice que no coincide, una página rota)."""
    copia = sr.respaldar_si_toca(crear_base(tmp_path / "escuela.db"), tmp_path / "resp", DIA)
    real = sr._abrir_solo_lectura

    class ConDanos:
        def __init__(self, con):
            self.con = con

        def execute(self, sql, *a):
            if sql == "PRAGMA integrity_check":
                return self.con.execute("SELECT '*** in database main *** Page 5: btreeInitPage() returns error code 11'")
            return self.con.execute(sql, *a)

        def close(self):
            self.con.close()

    monkeypatch.setattr(sr, "_abrir_solo_lectura", lambda ruta: ConDanos(real(ruta)))
    with pytest.raises(sr.ErrorRespaldo, match="está dañado: la revisión de integridad falló"):
        sr.verificar(copia)


def test_un_archivo_temporal_sobrante_de_un_intento_anterior_no_estorba(tmp_path):
    base = crear_base(tmp_path / "escuela.db")
    copia = sr.respaldar_si_toca(base, tmp_path / "resp", DIA)
    (tmp_path / "escuela.db.restaurando").write_bytes(b"sobras de un corte de luz en mitad de otra restauracion" * 100)
    sr.restaurar(copia, base, AHORA)
    assert contenido(base)["colegio"] == [("Liceo de Prueba",)] and not (tmp_path / "escuela.db.restaurando").exists()


def test_la_ultima_copia_es_la_mas_reciente_por_su_nombre(tmp_path):
    carpeta = tmp_path / "resp"
    assert sr.ultima_copia(carpeta) is None  # ni existe la carpeta
    carpeta.mkdir()
    assert sr.ultima_copia(carpeta) is None  # existe, sin copias
    for dia in ("2026-09-30", "2026-10-02", "2026-10-01"):
        (carpeta / f"escuela-{dia}.db").write_bytes(b"x")
    (carpeta / "escuela-2026-10-09.parcial").write_bytes(b"a medias")  # una copia a medias no cuenta
    assert sr.ultima_copia(carpeta).name == "escuela-2026-10-02.db"


# --- el script de quien administra -------------------------------------------------------------------


@pytest.fixture()
def instalacion(tmp_path, monkeypatch):
    """Una base y su carpeta de respaldos, con el servidor apagado."""
    base = crear_base(tmp_path / "escuela.db")
    carpeta = tmp_path / "respaldos"
    sr.respaldar_si_toca(base, carpeta, DIA)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{base.as_posix()}")
    monkeypatch.setenv("CARPETA_RESPALDOS", str(carpeta))
    monkeypatch.setattr(rr, "_servidor_en_marcha", lambda: False)
    return {"base": base, "carpeta": carpeta, "antes": contenido(base)}


def _danar(base):
    con = sqlite3.connect(base)
    con.execute("PRAGMA foreign_keys=OFF"), con.execute("delete from cursos"), con.commit(), con.close()


def test_sin_confirmar_el_script_solo_dice_lo_que_haria(instalacion, capsys):
    _danar(instalacion["base"])
    estropeada = contenido(instalacion["base"])
    assert rr.main([], ahora=AHORA) == 0
    salida = capsys.readouterr().out
    assert "No se hizo nada todavía" in salida and "escuela-2026-10-02.db" in salida
    assert contenido(instalacion["base"]) == estropeada


def test_con_confirmacion_restaura_el_ultimo_respaldo(instalacion, capsys):
    _danar(instalacion["base"])
    assert rr.main(["--si"], ahora=AHORA) == 0
    assert contenido(instalacion["base"]) == instalacion["antes"]
    salida = capsys.readouterr().out
    assert "La base anterior quedó en" in salida and "Listo" in salida


def test_se_puede_elegir_otro_respaldo(instalacion):
    carpeta = instalacion["carpeta"]
    con = sqlite3.connect(instalacion["base"])
    con.execute("update colegios set nombre = 'Liceo Nuevo'"), con.commit(), con.close()
    segundo = sr.respaldar_si_toca(instalacion["base"], carpeta, DIA + datetime.timedelta(days=1))
    assert rr.main([str(carpeta / "escuela-2026-10-02.db"), "--si"], ahora=AHORA) == 0  # el primero, no el último
    assert contenido(instalacion["base"])["colegio"] == [("Liceo de Prueba",)]
    assert segundo.name == "escuela-2026-10-03.db"


def test_con_el_servidor_encendido_se_niega_y_no_toca_nada(instalacion, monkeypatch, capsys):
    monkeypatch.setattr(rr, "_servidor_en_marcha", lambda: True)
    _danar(instalacion["base"])
    estropeada = contenido(instalacion["base"])
    assert rr.main(["--si"], ahora=AHORA) == 2
    assert "Apágalo antes de restaurar" in capsys.readouterr().out
    assert contenido(instalacion["base"]) == estropeada


def test_sin_respaldos_lo_dice(instalacion, capsys):
    for copia in instalacion["carpeta"].glob("*.db"):
        copia.unlink()
    assert rr.main(["--si"], ahora=AHORA) == 1
    assert "No hay respaldos" in capsys.readouterr().out


def test_un_respaldo_danado_no_se_restaura_y_el_script_lo_dice(instalacion, capsys):
    (instalacion["carpeta"] / "escuela-2026-10-02.db").write_bytes(b"basura" * 50)
    _danar(instalacion["base"])
    estropeada = contenido(instalacion["base"])
    assert rr.main(["--si"], ahora=AHORA) == 1
    assert "No se restaura nada" in capsys.readouterr().out
    assert contenido(instalacion["base"]) == estropeada


def test_un_respaldo_de_una_version_anterior_queda_al_dia_con_las_migraciones(tmp_path, monkeypatch):
    """Una copia de antes de la cola de procesamiento (sin `iniciada_en`) se restaura y queda lista para la versión actual."""
    from alembic.script import ScriptDirectory

    vieja = tmp_path / "vieja.db"
    configuracion = migrar(vieja, "b4e6a8c0d2f5")  # el esquema de antes de la Fase 5
    con = sqlite3.connect(vieja)
    con.execute("insert into colegios (nombre) values ('Liceo antiguo')"), con.commit()
    assert "iniciada_en" not in [fila[1] for fila in con.execute("pragma table_info(grabaciones)")]
    con.close()
    copia = sr.respaldar_si_toca(vieja, tmp_path / "respaldos", DIA)

    destino = tmp_path / "escuela.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{destino.as_posix()}")
    monkeypatch.setenv("CARPETA_RESPALDOS", str(tmp_path / "respaldos"))
    monkeypatch.setattr(rr, "_servidor_en_marcha", lambda: False)
    assert rr.main([str(copia), "--si"], ahora=AHORA) == 0

    con = sqlite3.connect(destino)
    assert "iniciada_en" in [fila[1] for fila in con.execute("pragma table_info(grabaciones)")]  # migrada
    assert con.execute("select nombre from colegios").fetchall() == [("Liceo antiguo",)]  # y con sus datos
    assert con.execute("select version_num from alembic_version").fetchone() == (ScriptDirectory.from_config(configuracion).get_current_head(),)
    con.close()


def test_una_base_sin_historial_de_migraciones_se_restaura_y_el_script_avisa_en_vez_de_fallar(tmp_path, monkeypatch, capsys):
    """La base de demostración se crea sin migraciones: no se sabe en qué versión está, y no hay que adivinarlo."""
    sin_historial = crear_base(tmp_path / "demo.db", con_migraciones=False)
    copia = sr.respaldar_si_toca(sin_historial, tmp_path / "respaldos", DIA)
    destino = tmp_path / "escuela.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{destino.as_posix()}")
    monkeypatch.setattr(rr, "_servidor_en_marcha", lambda: False)
    assert rr.main([str(copia), "--si"], ahora=AHORA) == 0
    assert contenido(destino) == contenido(sin_historial)  # igual se restauró
    salida = capsys.readouterr().out
    assert "no registra su versión" in salida and "Listo" in salida


def test_el_script_reconoce_si_el_servidor_esta_encendido(monkeypatch):
    """`_servidor_en_marcha` de verdad (en las demás pruebas se reemplaza): contra un servidor HTTP real y contra un puerto cerrado."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Salud(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/salud" else 404)
            self.end_headers()

        def log_message(self, *a):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Salud)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    puerto = servidor.server_address[1]
    try:
        monkeypatch.setattr(rr, "DIRECCIONES", (f"http://127.0.0.1:{puerto}/salud",))
        assert rr._servidor_en_marcha() is True
        monkeypatch.setattr(rr, "DIRECCIONES", (f"http://127.0.0.1:{puerto}/otra_cosa",))
        assert rr._servidor_en_marcha() is False  # algo contesta, pero no es la salud del servidor
    finally:
        servidor.shutdown()
        servidor.server_close()
    monkeypatch.setattr(rr, "DIRECCIONES", (f"http://127.0.0.1:{puerto}/salud",))
    assert rr._servidor_en_marcha() is False  # ya nadie escucha


def test_no_se_restaura_una_base_que_no_es_sqlite(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://usuario:clave@servidor/base")
    assert rr.main(["--si"], ahora=AHORA) == 1
    assert "Solo se pueden restaurar bases SQLite" in capsys.readouterr().out
