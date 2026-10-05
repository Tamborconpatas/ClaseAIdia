"""El lanzador de un solo comando: prepara el `.env` sin pisar nada y se niega a arrancar dos veces."""
import socket

from scripts import iniciar

EJEMPLO = "# comentario\nJWT_SECRET_KEY=\nOTRA=1\n"


def clave(env):
    return next(l.split("=", 1)[1] for l in env.read_text(encoding="utf-8").splitlines() if l.startswith("JWT_SECRET_KEY="))


def test_sin_env_lo_crea_desde_el_ejemplo_con_una_clave_nueva(tmp_path):
    ejemplo, env = tmp_path / ".env.example", tmp_path / ".env"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    assert iniciar.asegurar_env(env, ejemplo) is True
    assert len(clave(env)) == 64 and "OTRA=1" in env.read_text(encoding="utf-8") and "# comentario" in env.read_text(encoding="utf-8")
    assert ejemplo.read_text(encoding="utf-8") == EJEMPLO  # el ejemplo no se toca


def test_con_clave_ya_puesta_no_cambia_nada(tmp_path):
    ejemplo, env = tmp_path / ".env.example", tmp_path / ".env"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    env.write_text("JWT_SECRET_KEY=la-del-colegio-que-no-se-toca\nCARPETA_RESPALDOS=D:/resp\n", encoding="utf-8")
    assert iniciar.asegurar_env(env, ejemplo) is False
    assert env.read_text(encoding="utf-8") == "JWT_SECRET_KEY=la-del-colegio-que-no-se-toca\nCARPETA_RESPALDOS=D:/resp\n"


def test_con_la_clave_vacia_la_completa_y_conserva_lo_demas(tmp_path):
    ejemplo, env = tmp_path / ".env.example", tmp_path / ".env"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    env.write_text("CARPETA_RESPALDOS=D:/resp\nJWT_SECRET_KEY=\n", encoding="utf-8")
    assert iniciar.asegurar_env(env, ejemplo) is True
    assert len(clave(env)) == 64 and "CARPETA_RESPALDOS=D:/resp" in env.read_text(encoding="utf-8")


def test_si_el_env_no_tiene_la_linea_la_agrega(tmp_path):
    ejemplo, env = tmp_path / ".env.example", tmp_path / ".env"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    env.write_text("OTRA=1\n", encoding="utf-8")
    assert iniciar.asegurar_env(env, ejemplo) is True
    assert len(clave(env)) == 64 and "OTRA=1" in env.read_text(encoding="utf-8")


def test_dos_claves_generadas_no_se_repiten(tmp_path):
    ejemplo = tmp_path / ".env.example"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    iniciar.asegurar_env(tmp_path / "a", ejemplo), iniciar.asegurar_env(tmp_path / "b", ejemplo)
    assert clave(tmp_path / "a") != clave(tmp_path / "b")


def test_un_puerto_ocupado_se_detecta_y_uno_libre_no():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        puerto = s.getsockname()[1]
        assert iniciar.puerto_abierto(puerto) is True
    assert iniciar.puerto_abierto(puerto) is False  # ya cerrado


def test_un_modo_desconocido_muestra_la_ayuda_y_no_arranca_nada(capsys, monkeypatch):
    monkeypatch.setattr(iniciar.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía arrancar nada")))
    assert iniciar.main(["otra"]) == 2
    assert "python -m scripts.iniciar" in capsys.readouterr().out


def test_si_ya_hay_una_abierta_se_niega_sin_tocar_el_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(iniciar, "RAIZ", tmp_path)
    (tmp_path / ".env.example").write_text(EJEMPLO, encoding="utf-8")
    monkeypatch.setattr(iniciar, "puerto_abierto", lambda p: p == iniciar.PUERTO_API)
    monkeypatch.setattr(iniciar.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía arrancar nada")))
    assert iniciar.main([]) == 1
    assert f"El puerto {iniciar.PUERTO_API} ya está en uso" in capsys.readouterr().out
