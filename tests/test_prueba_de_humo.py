"""La prueba de humo de la instalación: sus piezas (el veredicto, el audio, el entorno) se prueban rápido; la corrida real la hace el administrador."""
import json
import socket
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from scripts import prueba_de_humo as ph


@pytest.mark.parametrize("estado,error,con_voz,bien,dice", [
    ("terminada", None, False, True, "se procesó completa"),
    ("terminada", None, True, True, "se procesó completa"),
    ("error", "No se detectó voz en el audio", False, True, "con un tono no hay palabras"),
    ("error", "No se detectó voz en el audio", True, False, "no se pudo procesar"),  # con una voz de verdad, no oír nada sí es un problema
    ("error", "No se pudo generar el resumen: Ollama no responde", True, False, "falta la generación del material"),
    ("error", "Falta el modelo llama3.2", True, False, "falta la generación del material"),
    ("error", "Falló el procesamiento de la clase. Se reintentará sola.", False, False, "no se pudo procesar"),
    ("error", None, False, False, "sin detalle"),
    ("procesando", None, False, False, "no se pudo procesar"),
])
def test_el_veredicto_distingue_lo_esperado_de_lo_que_falla(estado, error, con_voz, bien, dice):
    ok, texto = ph.veredicto(estado, error, con_voz)
    assert ok is bien and dice in texto


def test_el_audio_de_prueba_es_un_wav_valido_de_ocho_segundos_con_sonido(tmp_path):
    ruta = ph.audio_de_prueba(tmp_path / "tono.wav")
    with wave.open(str(ruta)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 16000 * 8)
        muestras = w.readframes(2000)
    assert muestras[:4] != b"\x00" * 4 and len(set(muestras)) > 10  # no es silencio


def test_el_tipo_de_audio_sale_de_la_extension_y_lo_desconocido_se_rechaza():
    assert ph.tipo_de_audio(Path("clase.WAV")) == "audio/wav"
    assert ph.tipo_de_audio(Path("clase.webm")) == "audio/webm;codecs=opus"
    assert ph.tipo_de_audio(Path("clase.m4a")) == "audio/mp4"
    with pytest.raises(SystemExit, match="no admitido"):
        ph.tipo_de_audio(Path("clase.txt"))


def test_el_servidor_de_la_prueba_tiene_lo_suyo_y_la_codificacion_de_windows(tmp_path):
    base = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PROCESAMIENTO_EN_HILO": "1", "DATABASE_URL": "sqlite:///la_del_colegio.db", "CARPETA_RESPALDOS": "los_del_colegio", "OTRA": "x"}
    env = ph.entorno_del_servidor(tmp_path, base)
    for tapa in ("PYTHONUTF8", "PYTHONIOENCODING", "PROCESAMIENTO_EN_HILO"):
        assert tapa not in env  # taparían justo la falla que la prueba quiere cazar (o la esquivarían con un hilo)
    assert env["DATABASE_URL"] == f"sqlite:///{(tmp_path / 'escuela.db').as_posix()}" and "colegio" not in env["DATABASE_URL"]  # nunca la base del colegio
    assert Path(env["AUDIO_TEMP_DIR"]).parent == Path(env["FOTOS_TEMP_DIR"]).parent == Path(env["CARPETA_RESPALDOS"]).parent == tmp_path
    assert "colegio" not in env["CARPETA_RESPALDOS"] and env["OTRA"] == "x"  # lo demás se hereda
    assert len(env["JWT_SECRET_KEY"]) >= 32 and env["JWT_SECRET_KEY"] != ph.entorno_del_servidor(tmp_path, base)["JWT_SECRET_KEY"]
    assert base["PYTHONUTF8"] == "1"  # el entorno original no se toca


def test_el_puerto_libre_se_puede_usar():
    puerto = ph.puerto_libre()
    assert 1024 <= puerto <= 65535
    with socket.socket() as s:
        s.bind(("127.0.0.1", puerto))


def test_los_rut_de_la_prueba_son_validos():
    from nucleo.validadores import validar_rut

    assert validar_rut(ph.rut(11111111)) and validar_rut(ph.rut(12345678)) and ph.rut(11111111) != ph.rut(12345678)


class Eco(BaseHTTPRequestHandler):
    def _responder(self, codigo, cuerpo, tipo="application/json"):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self):
        if self.path == "/conflicto":
            self._responder(409, {"detail": "ya existe"})
        elif self.path == "/roto":
            self._responder(500, b"Internal Server Error", "text/plain")
        elif self.path == "/vacio":
            self._responder(204, b"")
        else:
            self._responder(200, {"auth": self.headers.get("Authorization"), "ruta": self.path})

    def do_POST(self):
        largo = int(self.headers["Content-Length"])
        self._responder(201, {"tipo": self.headers["Content-Type"], "cuerpo": json.loads(self.rfile.read(largo))})

    def do_PUT(self):
        largo = int(self.headers["Content-Length"])
        self._responder(200, {"tipo": self.headers["Content-Type"], "bytes": len(self.rfile.read(largo))})

    def log_message(self, *a):
        pass


@pytest.fixture()
def servidor_de_mentira(tmp_path):
    http = HTTPServer(("127.0.0.1", 0), Eco)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    s = ph.Servidor(tmp_path)
    s.base = f"http://127.0.0.1:{http.server_address[1]}"
    yield s
    http.shutdown()
    http.server_close()


def test_las_llamadas_llevan_el_token_el_cuerpo_y_los_parametros(servidor_de_mentira):
    s = servidor_de_mentira
    assert s.llamar("GET", "/cosa", token="abc", params={"dispositivo": "eq1"}) == (200, {"auth": "Bearer abc", "ruta": "/cosa?dispositivo=eq1"})
    assert s.llamar("POST", "/x", {"a": 1}) == (201, {"tipo": "application/json", "cuerpo": {"a": 1}})
    assert s.llamar("PUT", "/y", datos=b"1234", tipo="audio/wav") == (200, {"tipo": "audio/wav", "bytes": 4})


def test_los_errores_del_servidor_llegan_como_estado_y_detalle(servidor_de_mentira):
    s = servidor_de_mentira
    assert s.llamar("GET", "/conflicto") == (409, {"detail": "ya existe"})
    assert s.llamar("GET", "/roto") == (500, "Internal Server Error")  # no es JSON: se devuelve el texto
    assert s.llamar("GET", "/vacio") == (204, None)


def test_exigir_explica_que_paso_con_las_palabras_del_servidor():
    assert ph.exigir((201, {"id": 5}), 201, "Crear el curso") == {"id": 5}
    with pytest.raises(RuntimeError, match=r"Crear el curso falló \(HTTP 409\): ya existe"):
        ph.exigir((409, {"detail": "ya existe"}), 201, "Crear el curso")
    with pytest.raises(RuntimeError, match=r"HTTP 500\): Internal Server Error"):
        ph.exigir((500, "Internal Server Error"), 200, "Algo")


def test_los_argumentos_de_la_linea_de_comandos(monkeypatch, tmp_path, capsys):
    llamadas = []
    monkeypatch.setattr(ph, "correr", lambda audio, espera, conservar: llamadas.append((audio, espera, conservar)) or 0)
    assert ph.main([]) == 0
    clase = tmp_path / "clase.wav"
    clase.write_bytes(b"x")
    assert ph.main(["--audio", str(clase), "--espera", "30", "--conservar"]) == 0
    assert llamadas == [(None, 900.0, False), (clase, 30.0, True)]
    assert ph.main(["--audio", str(tmp_path / "no_existe.wav")]) == 1
    assert "No existe el audio" in capsys.readouterr().out and len(llamadas) == 2  # no llegó a correr


def test_solo_se_muestran_los_avisos_del_equipo():
    assert set(ph.TEMAS_DEL_EQUIPO) == {"ollama", "disco", "memoria", "vigilancia"}  # no «clases» (el error del tono) ni «respaldos» (la carpeta temporal)
