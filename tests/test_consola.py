"""La salida de texto no tumba el servidor ni el trabajador cuando va a un archivo (cp1252 en Windows)."""
import io
import os
import subprocess
import sys

import pytest

from nucleo.consola import salida_segura
from servicios import trabajador

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _como_archivo_de_windows():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")  # lo que Python usa al redirigir la salida en Windows


def test_sin_salida_segura_un_print_con_emoji_falla_en_cp1252(monkeypatch):
    monkeypatch.setattr(sys, "stdout", _como_archivo_de_windows())
    with pytest.raises(UnicodeEncodeError):
        print("✓ Normalización")


def test_con_salida_segura_imprime_en_utf8_sin_fallar(monkeypatch):
    salida, errores = _como_archivo_de_windows(), _como_archivo_de_windows()
    monkeypatch.setattr(sys, "stdout", salida)
    monkeypatch.setattr(sys, "stderr", errores)
    salida_segura()
    print("✓ ⚠️ ñ")
    print("también por el error", file=sys.stderr)
    salida.flush()
    errores.flush()
    assert salida.buffer.getvalue().decode("utf-8") == "✓ ⚠️ ñ\n"
    assert errores.buffer.getvalue().decode("utf-8") == "también por el error\n"


def test_si_el_flujo_no_se_puede_pasar_a_utf8_igual_imprimir_no_falla(monkeypatch):
    # un archivo con una codificación que no tiene el símbolo: en vez de lanzar error, lo reemplaza
    salida = io.TextIOWrapper(io.BytesIO(), encoding="ascii", newline="\n")
    monkeypatch.setattr(sys, "stdout", salida)
    salida_segura()
    print("ñ ✓")  # no lanza
    salida.flush()
    assert salida.buffer.getvalue().decode("utf-8") == "ñ ✓\n"


def test_sin_consola_no_hay_flujo_y_no_falla(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)  # `pythonw` o un .exe de ventana
    monkeypatch.setattr(sys, "stderr", io.StringIO())  # un flujo que no se puede reconfigurar
    salida_segura()


def test_el_trabajador_lo_activa_antes_que_nada(monkeypatch):
    llamadas = []
    monkeypatch.setattr(trabajador, "salida_segura", lambda: llamadas.append("salida"))
    assert trabajador.main(["otro", "3"]) == 2  # argumentos malos: ni siquiera llega a cargar nada
    assert llamadas == ["salida"]


def _python(codigo, tmp_path, **entorno):
    """Corre Python con la salida a un archivo y la codificación de Windows, como el supervisor del servidor."""
    registro = tmp_path / "salida.log"
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252", "JWT_SECRET_KEY": "", "DATABASE_URL": f"sqlite:///{tmp_path / 'x.db'}", **entorno}
    with open(registro, "wb") as f:
        r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env, stdout=f, stderr=subprocess.PIPE, timeout=120)
    return r.returncode, registro.read_bytes().decode("utf-8", errors="replace"), r.stderr.decode("utf-8", errors="replace")


def test_el_entorno_de_la_prueba_reproduce_el_problema_real(tmp_path):
    """Con la salida a un archivo y la codificación de Windows, un print con ✓ falla: así fallaba el procesamiento de las clases."""
    codigo, _, errores = _python("print('✓ Normalización')", tmp_path)
    assert codigo != 0 and "UnicodeEncodeError" in errores


def test_la_api_deja_la_salida_en_utf8_apenas_arranca_aunque_vaya_a_un_archivo(tmp_path):
    codigo, salida, errores = _python("import api, sys; print(sys.stdout.encoding, sys.stdout.errors)", tmp_path)
    assert codigo == 0, errores[-600:]
    assert salida.split()[-2:] == ["utf-8", "replace"]  # (antes imprime el aviso de que no hay clave JWT)


def test_el_trabajador_deja_la_salida_en_utf8_antes_de_cargar_nada_aunque_vaya_a_un_archivo(tmp_path):
    codigo, salida, errores = _python("import sys; from servicios import trabajador; trabajador.main(['malo']); print(sys.stdout.encoding, sys.stderr.encoding)", tmp_path)
    assert codigo == 0, errores[-600:]
    assert salida.split() == ["utf-8", "utf-8"]
