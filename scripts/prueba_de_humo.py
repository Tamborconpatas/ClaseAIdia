# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Prueba de humo de la instalación: levanta el servidor de verdad en una carpeta temporal y procesa una clase de punta a punta.

    python -m scripts.prueba_de_humo                    # con un tono de audio: comprueba que todo el motor corre
    python -m scripts.prueba_de_humo --audio clase.wav  # con una voz: además comprueba que Ollama escribe el material
    python -m scripts.prueba_de_humo --conservar        # no borra la carpeta temporal (para revisar los registros)

Existe porque las pruebas automáticas pasaban mientras, en el servidor real, ninguna clase se procesaba: nadie corría el
servidor y el trabajador de verdad con la salida a un archivo, como lo hace el supervisor de Windows. Aquí sí. No toca la
base de datos ni las carpetas del colegio: todo va a una carpeta temporal, con su propia base creada con las migraciones.
"""
import datetime
import json
import math
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from nucleo.consola import salida_segura

salida_segura()

from nucleo.validadores import validar_rut  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CLAVE = "clave-de-la-prueba-de-humo"
# De los avisos del panel del UTP, solo los del equipo: los de «clases con error» y «respaldos» serían ruido (el error es el del tono y los respaldos son los de la carpeta temporal).
TEMAS_DEL_EQUIPO = ("ollama", "disco", "memoria", "vigilancia")
TIPOS = {".wav": "audio/wav", ".webm": "audio/webm;codecs=opus", ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".mp4": "audio/mp4", ".m4a": "audio/mp4"}


def audio_de_prueba(destino: Path, segundos: int = 8) -> Path:
    """Un tono de 440 Hz (WAV, 16 kHz, mono): audio válido sin voz. Whisper no encuentra palabras, que es el resultado esperado."""
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(16000 * segundos)))
    return destino


def entorno_del_servidor(carpeta: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """El entorno del servidor de la prueba: su propia base y carpetas, y la codificación de Windows tal como queda con la salida
    a un archivo (sin PYTHONUTF8 ni PYTHONIOENCODING, que taparían justo la falla que se quiere cazar)."""
    env = dict(os.environ if base is None else base)
    for variable in ("PYTHONUTF8", "PYTHONIOENCODING", "PROCESAMIENTO_EN_HILO"):
        env.pop(variable, None)
    env.update(
        DATABASE_URL=f"sqlite:///{(carpeta / 'escuela.db').as_posix()}",
        AUDIO_TEMP_DIR=str(carpeta / "audio"),
        FOTOS_TEMP_DIR=str(carpeta / "fotos"),
        CARPETA_RESPALDOS=str(carpeta / "respaldos"),
        JWT_SECRET_KEY=secrets.token_hex(32),
    )
    return env


def veredicto(estado: str, error: str | None, con_voz: bool) -> tuple[bool, str]:
    """¿Cómo terminó la clase de la prueba? (¿está bien?, explicación)."""
    error = error or ""
    if estado == "terminada":
        return True, "La clase se procesó completa: se transcribió y se generó el material."
    if not con_voz and "No se detectó voz" in error:
        return True, "El motor corrió hasta la transcripción: con un tono no hay palabras, y eso es lo esperado."
    if "Ollama" in error or "modelo" in error:
        return False, f"La transcripción funcionó, pero falta la generación del material: {error}"
    return False, f"La clase no se pudo procesar ({estado}): {error or 'sin detalle'}"


def tipo_de_audio(ruta: Path) -> str:
    try:
        return TIPOS[ruta.suffix.lower()]
    except KeyError:
        raise SystemExit(f"Formato de audio no admitido: {ruta.suffix}. Usa uno de: {', '.join(TIPOS)}") from None


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rut(cuerpo: int) -> str:
    return next(f"{cuerpo}-{d}" for d in "0123456789K" if validar_rut(f"{cuerpo}-{d}"))


class Servidor:
    """El servidor de la prueba, con la salida a un archivo como la deja el supervisor."""

    def __init__(self, carpeta: Path):
        self.carpeta, self.puerto = carpeta, puerto_libre()
        self.base = f"http://127.0.0.1:{self.puerto}"
        self.registro = carpeta / "servidor.log"
        self.proceso: subprocess.Popen | None = None

    def migrar(self, env: dict[str, str]) -> None:
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode != 0:
            raise RuntimeError(f"Las migraciones fallaron:\n{(r.stdout + r.stderr)[-1500:]}")

    def arrancar(self, env: dict[str, str], espera: float = 90) -> None:
        with open(self.registro, "wb") as salida:
            self.proceso = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", str(self.puerto), "--no-access-log"],
                cwd=RAIZ, env=env, stdout=salida, stderr=subprocess.STDOUT,
            )
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if self.proceso.poll() is not None:
                raise RuntimeError(f"El servidor se cerró al arrancar (código {self.proceso.returncode}).")
            try:
                if self.llamar("GET", "/salud")[0] == 200:
                    return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError(f"El servidor no respondió en {espera:.0f} s.")

    def detener(self) -> None:
        if self.proceso and self.proceso.poll() is None:
            self.proceso.terminate()
            try:
                self.proceso.wait(15)
            except subprocess.TimeoutExpired:
                self.proceso.kill()

    def llamar(self, metodo: str, ruta: str, cuerpo=None, token: str | None = None, datos: bytes | None = None, tipo: str | None = None, params: dict | None = None):
        url = self.base + ruta + (("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else "")
        cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
        if cuerpo is not None:
            datos, tipo = json.dumps(cuerpo).encode(), "application/json"
        if tipo:
            cabeceras["Content-Type"] = tipo
        peticion = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
        try:
            with urllib.request.urlopen(peticion, timeout=60) as r:
                texto = r.read()
                return r.status, (json.loads(texto) if texto else None)
        except urllib.error.HTTPError as e:
            texto = e.read()
            try:
                return e.code, json.loads(texto)
            except ValueError:
                return e.code, texto.decode("utf-8", errors="replace")


def paso(numero: int, total: int, texto: str) -> None:
    print(f"[{numero}/{total}] {texto} ...", flush=True)


def exigir(respuesta, esperado: int, que: str):
    estado, cuerpo = respuesta
    if estado != esperado:
        detalle = cuerpo.get("detail") if isinstance(cuerpo, dict) else cuerpo
        raise RuntimeError(f"{que} falló (HTTP {estado}): {detalle}")
    return cuerpo


def preparar_clase(s: Servidor):
    """Primer arranque de un colegio nuevo (como en una instalación): colegio y UTP, una profesora, un curso y un bloque de hoy."""
    hoy = datetime.datetime.now()
    profesora = rut(12345678)
    inicio = exigir(s.llamar("POST", "/auth/setup", {"colegio_nombre": "Colegio de la prueba", "rut": rut(11111111), "nombre": "UTP de la prueba", "password": CLAVE}), 201, "Crear el colegio")
    token_utp, colegio_id = inicio["access_token"], inicio["colegio_id"]
    exigir(s.llamar("POST", "/usuarios", {"rut": profesora, "nombre": "Profesora de la prueba", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, token=token_utp), 201, "Crear la profesora")
    curso = exigir(s.llamar("POST", "/cursos", {"nombre": "Prueba", "colegio_id": colegio_id}, token=token_utp), 201, "Crear el curso")
    token_profesora = exigir(s.llamar("POST", "/auth/login/staff", {"rut": profesora, "password": CLAVE}), 200, "Entrar como profesora")["access_token"]
    profesora_id = exigir(s.llamar("GET", "/auth/me", token=token_profesora), 200, "Ver a la profesora")["id"]
    bloque = exigir(
        s.llamar("POST", f"/cursos/{curso['id']}/bloques", {"tipo": "CLASE", "asignatura": "Ciencias", "profesor_id": profesora_id, "sala": "S1", "dia_semana": hoy.weekday(), "hora_inicio": "00:00", "hora_fin": "23:59"}, token=token_utp),
        201, "Crear el bloque de hoy",
    )
    return token_utp, token_profesora, bloque["id"]


def grabar(s: Servidor, token: str, bloque_id: int, audio: Path) -> int:
    """Lo que hace el equipo grabador de la sala: iniciar, subir el audio, terminar y finalizar."""
    equipo = "equipo-prueba-de-humo"
    sesion = exigir(s.llamar("POST", "/grabaciones", {"bloque_id": bloque_id}, token=token), 201, "Crear la sesión de grabación")
    gid = sesion["id"]
    exigir(s.llamar("POST", f"/grabaciones/{gid}/grabador", {"dispositivo": equipo, "forzar": True}, token=token), 200, "Registrar el equipo grabador")
    exigir(s.llamar("POST", f"/grabaciones/{gid}/comando", {"accion": "iniciar"}, token=token), 200, "Iniciar la grabación")
    exigir(s.llamar("PUT", f"/grabaciones/{gid}/trozos/0", datos=audio.read_bytes(), tipo=tipo_de_audio(audio), token=token, params={"dispositivo": equipo}), 200, "Subir el audio")
    exigir(s.llamar("POST", f"/grabaciones/{gid}/comando", {"accion": "terminar"}, token=token), 200, "Terminar la grabación")
    exigir(s.llamar("POST", f"/grabaciones/{gid}/finalizar", {"dispositivo": equipo}, token=token), 200, "Finalizar la grabación")
    return gid


def esperar_resultado(s: Servidor, token: str, gid: int, espera: float) -> dict:
    limite = time.monotonic() + espera
    ultimo = {}
    while time.monotonic() < limite:
        ultimo = exigir(s.llamar("GET", f"/grabaciones/{gid}", token=token), 200, "Consultar la grabación")
        if ultimo["estado"] in ("terminada", "error"):
            return ultimo
        time.sleep(2)
    raise RuntimeError(f"La clase no terminó de procesarse en {espera:.0f} s (quedó en «{ultimo.get('estado')}»).")


def correr(audio: Path | None, espera: float, conservar: bool) -> int:
    inicio = time.monotonic()
    carpeta = Path(tempfile.mkdtemp(prefix="prueba_de_humo_"))
    s = Servidor(carpeta)
    ok = False
    try:
        if audio is None:
            audio = audio_de_prueba(carpeta / "tono.wav")
        con_voz = audio.name != "tono.wav"
        env = entorno_del_servidor(carpeta)
        paso(1, 6, "Crear la base de datos desde cero con las migraciones")
        s.migrar(env)
        paso(2, 6, "Arrancar el servidor con la salida a un archivo (como lo hace el supervisor de Windows)")
        s.arrancar(env)
        paso(3, 6, "Preparar un colegio, una profesora y un bloque de hoy")
        token_utp, token, bloque_id = preparar_clase(s)
        paso(4, 6, f"Grabar y subir el audio ({audio.name})")
        gid = grabar(s, token, bloque_id, audio)
        paso(5, 6, f"Procesar la clase (Whisper{' y Ollama' if con_voz else ''}; la primera vez puede tardar si hay que cargar los modelos)")
        resultado = esperar_resultado(s, token, gid, espera)
        bien, explicacion = veredicto(resultado["estado"], resultado.get("error"), con_voz)
        paso(6, 6, "Revisar que no quede audio guardado y cómo está el equipo")
        sobrante = (carpeta / "audio" / str(gid)).exists()
        estado = s.llamar("GET", "/estado", token=token_utp)[1] or {}
        print(f"\n  {'OK   ' if bien else 'FALLA'} {explicacion}")
        print(f"  {'FALLA' if sobrante else 'OK   '} {'Quedó audio guardado en el disco: debería haberse borrado.' if sobrante else 'No quedó audio guardado: se borró al terminar.'}")
        for alerta in estado.get("alertas", []) if isinstance(estado, dict) else []:
            if alerta["tema"] in TEMAS_DEL_EQUIPO:
                print(f"  AVISO ({alerta['nivel']}): {alerta['texto']}")
        ok = bien and not sobrante
    except (RuntimeError, OSError, subprocess.SubprocessError) as e:
        print(f"\n  FALLA {e}")
    finally:
        s.detener()
        if ok and not conservar:
            shutil.rmtree(carpeta, ignore_errors=True)
        else:
            print(f"\n  Los archivos de la prueba quedaron en {carpeta} (el registro del servidor es servidor.log).")
            if not ok and s.registro.exists():
                cola = s.registro.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
                print("  Últimas líneas del registro del servidor:\n    " + "\n    ".join(cola))
    print(f"\nRESULTADO: {'TODO BIEN' if ok else 'ALGO FALLÓ'} ({time.monotonic() - inicio:.0f} s)")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    audio = None
    espera = 900.0
    conservar = "--conservar" in argv
    if "--audio" in argv:
        audio = Path(argv[argv.index("--audio") + 1])
        if not audio.is_file():
            print(f"No existe el audio {audio}.")
            return 1
    if "--espera" in argv:
        espera = float(argv[argv.index("--espera") + 1])
    return correr(audio, espera, conservar)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
