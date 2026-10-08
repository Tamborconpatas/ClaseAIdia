"""Mide cuánto tarda procesar dos clases a la vez según cómo se reparta el trabajo entre la CPU y la GPU.

    python -m scripts.medir_reparto clase_A.wav clase_B.wav
    python -m scripts.medir_reparto clase_A.wav clase_B.wav --escenarios cpu-secuencial,reparto

Usa el mismo camino que el servidor (conversión y limpieza, Whisper, material de estudio y mapa conceptual con Ollama) y
cada clase corre en su propio proceso, como con `PROCESAMIENTOS_SIMULTANEOS=2`. Escenarios:
  todo-gpu         una clase después de la otra; Ollama decide (con GPU la usa y elige el modelo de 3B)
  cpu-secuencial   una después de la otra; Ollama solo en la CPU (OLLAMA_DISPOSITIVO=cpu, modelo de 1B)
  reparto          las dos a la vez; Whisper en la GPU y Ollama solo en la CPU
  gpu-simultaneo   las dos a la vez; Ollama decide (con GPU compite con Whisper por la memoria de video)
Necesita Ollama en marcha con los modelos de 1B y 3B, y la GPU visible para `nvidia-smi` si se quiere medir la memoria de video.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from nucleo.consola import salida_segura

salida_segura()

RAIZ = Path(__file__).resolve().parent.parent
ESCENARIOS = {
    "todo-gpu": ({"OLLAMA_DISPOSITIVO": "auto"}, False),
    "cpu-secuencial": ({"OLLAMA_DISPOSITIVO": "cpu"}, False),
    "reparto": ({"OLLAMA_DISPOSITIVO": "cpu"}, True),
    "gpu-simultaneo": ({"OLLAMA_DISPOSITIVO": "auto"}, True),
}


def trabajar(ruta: str) -> None:
    """Lo que hace el servidor con una clase, midiendo cada fase."""
    from servicios import servicio_grabacion as sg

    t0 = time.time()
    texto, _srt = sg.transcribir(ruta)
    t1 = time.time()
    resumen, puntos, hoja, tarjetas = sg.generar_material(texto)
    t2 = time.time()
    mapa = sg.generar_mapa(resumen, puntos, None)
    t3 = time.time()
    print("RESULTADO " + json.dumps({
        "transcripcion_s": round(t1 - t0, 1), "material_s": round(t2 - t1, 1), "mapa_s": round(t3 - t2, 1), "total_s": round(t3 - t0, 1),
        "palabras": len(texto.split()), "resumen_car": len(resumen), "tarjetas": len(tarjetas), "relaciones": len(mapa or []),
    }), flush=True)


class Monitor(threading.Thread):
    """Cada segundo anota la memoria de video, el uso de la GPU y la memoria libre del equipo."""

    def __init__(self):
        super().__init__(daemon=True)
        self.parar = threading.Event()
        self.vram_mb = self.gpu_pct = self.ram_libre_gb = None
        self._gpu = []

    def run(self):
        while not self.parar.is_set():
            if shutil.which("nvidia-smi"):
                r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True)
                try:
                    mem, uso = (int(x) for x in r.stdout.strip().split(","))
                    self.vram_mb = max(self.vram_mb or 0, mem)
                    self._gpu.append(uso)
                except ValueError:
                    pass
            for linea in Path("/proc/meminfo").read_text().splitlines() if Path("/proc/meminfo").exists() else []:
                if linea.startswith("MemAvailable"):
                    libre = int(linea.split()[1]) / 1024 / 1024
                    self.ram_libre_gb = libre if self.ram_libre_gb is None else min(self.ram_libre_gb, libre)
            self.parar.wait(1)

    def resumen(self):
        return {"vram_max_mb": self.vram_mb, "gpu_uso_medio_pct": round(sum(self._gpu) / len(self._gpu)) if self._gpu else None,
                "ram_libre_min_gb": round(self.ram_libre_gb, 1) if self.ram_libre_gb is not None else None}


def _lanzar(ruta: str, env: dict) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "scripts.medir_reparto", "--trabajador", ruta], cwd=RAIZ, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")


def _resultado(proceso: subprocess.Popen) -> dict:
    salida, error = proceso.communicate()
    for linea in salida.splitlines():
        if linea.startswith("RESULTADO "):
            return json.loads(linea[len("RESULTADO "):])
    return {"error": (error or salida).strip().splitlines()[-1][:200] if (error or salida).strip() else f"código {proceso.returncode}"}


def descargar_modelos() -> None:
    """Que cada escenario parta con Ollama sin nada cargado."""
    from infraestructura import cliente_ollama
    from servicios import servicio_material_estudio as sme

    url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    for modelo in (sme._OLLAMA_MODEL_CPU, sme._OLLAMA_MODEL_GPU):
        cliente_ollama.descargar_modelo(modelo, url)
    time.sleep(3)


def correr(nombre: str, clases: list[str]) -> dict:
    extra, simultaneo = ESCENARIOS[nombre]
    env = {**os.environ, **extra, "PYTHONUTF8": "1"}
    descargar_modelos()
    monitor = Monitor()
    monitor.start()
    t0 = time.time()
    if simultaneo:
        procesos = [_lanzar(c, env) for c in clases]
        resultados = [_resultado(p) for p in procesos]
    else:
        resultados = [_resultado(_lanzar(c, env)) for c in clases]
    total = round(time.time() - t0, 1)
    monitor.parar.set()
    monitor.join()
    return {"escenario": nombre, "total_s": total, "clases": resultados, **monitor.resumen()}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--trabajador"]:
        trabajar(argv[1])
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clases", nargs=2, help="dos archivos de audio")
    ap.add_argument("--escenarios", default=",".join(ESCENARIOS), help="separados por coma")
    ap.add_argument("--salida", default="reparto.json", help="dónde guardar los resultados")
    args = ap.parse_args(argv)
    clases = [str(Path(c).resolve()) for c in args.clases]
    resultados = []
    for nombre in args.escenarios.split(","):
        if nombre not in ESCENARIOS:
            ap.error(f"escenario desconocido: {nombre}")
        print(f"\n== {nombre}", flush=True)
        r = correr(nombre, clases)
        resultados.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=1), flush=True)
        Path(args.salida).write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
