"""Inicia ClaseAIdia completo con un solo comando (backend + interfaz) y abre el navegador.

    python -m scripts.iniciar            # uso normal, en este equipo
    python -m scripts.iniciar celular    # https en la red del colegio, para grabar con el celular
    python -m scripts.iniciar demo       # con datos de ejemplo (no toca la base real)

Prepara solo lo que falta: el archivo `.env` con su clave de sesión, la base de datos al día y las dependencias de la interfaz.
Para detener todo, Ctrl+C o cerrar la ventana. Es para desarrollar y probar; el servidor 24/7 del colegio usa
scripts\\windows\\instalar_servidor.bat.
"""
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from nucleo.consola import salida_segura

salida_segura()

RAIZ = Path(__file__).resolve().parent.parent
PUERTO_API, PUERTO_WEB = 8000, 5173
DEMO = "sqlite:///./escuela_demo.db"


def asegurar_env(env: Path, ejemplo: Path) -> bool:
    """Deja un `.env` con `JWT_SECRET_KEY` (sin ella las sesiones se cierran en cada reinicio). True si hubo que crearlo o completarlo."""
    lineas = (env if env.exists() else ejemplo).read_text(encoding="utf-8").splitlines()
    for i, linea in enumerate(lineas):
        if linea.split("=", 1)[0].strip() == "JWT_SECRET_KEY":
            if linea.split("=", 1)[1].strip().strip("\"'"):
                return False
            lineas[i] = f"JWT_SECRET_KEY={secrets.token_hex(32)}"
            break
    else:
        lineas.append(f"JWT_SECRET_KEY={secrets.token_hex(32)}")
    env.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return True


def puerto_abierto(puerto: int) -> bool:
    """¿Alguien escucha en `localhost:puerto`? (Vite lo hace solo por IPv6 en algunos equipos: se prueban todas las direcciones.)"""
    try:
        socket.create_connection(("localhost", puerto), timeout=0.5).close()
        return True
    except OSError:
        return False


def esperar_puerto(puerto: int, proceso: subprocess.Popen, segundos: float = 90) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite and proceso.poll() is None:
        if puerto_abierto(puerto):
            return True
        time.sleep(0.5)
    return False


def detener(proceso: subprocess.Popen) -> None:
    if proceso.poll() is None:  # `npm` deja procesos hijos: se cierra todo el árbol
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proceso.pid)], capture_output=True)


def main(argv: list[str]) -> int:
    modo = argv[0] if argv else ""
    if modo not in ("", "celular", "demo"):
        print(__doc__)
        return 2
    python = sys.executable
    env = {**os.environ}
    if asegurar_env(RAIZ / ".env", RAIZ / ".env.example"):
        print("Se preparó el archivo .env con una clave de sesión nueva.")
    for puerto in (PUERTO_API, PUERTO_WEB):
        if puerto_abierto(puerto):
            print(f"El puerto {puerto} ya está en uso: ¿ya hay una ClaseAIdia abierta? Ciérrala y vuelve a intentar.")
            return 1

    if modo == "demo":
        env["DATABASE_URL"] = DEMO
        print("Creando la base de demostración (se rehace en cada arranque: una antigua puede ser de un modelo anterior)...")
        (RAIZ / "escuela_demo.db").unlink(missing_ok=True)
        subprocess.run([python, "-m", "scripts.sembrar_demo"], cwd=RAIZ, env=env, check=True)
    else:
        print("Poniendo la base de datos al día...")
        if subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=RAIZ, env=env).returncode != 0:
            print("No se pudo actualizar la base de datos (mira el mensaje de arriba).")
            return 1
    if not (RAIZ / "frontend" / "node_modules").exists():
        print("Instalando la interfaz (solo la primera vez)...")
        if subprocess.run(["npm", "install"], cwd=RAIZ / "frontend", shell=True).returncode != 0:
            return 1
    if modo == "celular" and not (RAIZ / "certs" / "cert.pem").exists():
        print("Creando el certificado https de la red del colegio...")
        subprocess.run([python, "-m", "scripts.generar_certificado"], cwd=RAIZ, check=True)

    esquema = "https" if modo == "celular" else "http"
    api = subprocess.Popen([python, "-m", "uvicorn", "api:app", "--port", str(PUERTO_API)], cwd=RAIZ, env=env)
    web = subprocess.Popen(["npm", "run", "dev:https" if modo == "celular" else "dev"], cwd=RAIZ / "frontend", env=env, shell=True)
    try:
        if not (esperar_puerto(PUERTO_API, api) and esperar_puerto(PUERTO_WEB, web)):
            print("Algo no arrancó (mira los mensajes de arriba).")
            return 1
        print(f"\nListo. Abre {esquema}://localhost:{PUERTO_WEB}  (para detener todo: Ctrl+C o cierra esta ventana)")
        if modo == "celular":
            print(f"Desde el celular: {esquema}://{socket.gethostbyname(socket.gethostname())}:{PUERTO_WEB}  (la primera vez: «Avanzado → continuar»)")
        if modo == "demo":
            print("Datos de ejemplo: UTP 11111111-1 / demo-clave-2026 (las demás cuentas las mostró el comando de siembra).")
        webbrowser.open(f"{esquema}://localhost:{PUERTO_WEB}")
        while api.poll() is None and web.poll() is None:
            time.sleep(1)
        print("Uno de los dos procesos se cerró; se detiene todo.")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        detener(api)
        detener(web)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
