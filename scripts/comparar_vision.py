# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Compara modelos de visión leyendo las mismas fotos de pizarra, como lo hace la aplicación y en solo CPU.

    python -m scripts.comparar_vision CARPETA_CON_FOTOS [--salida CARPETA] [modelo ...]     (por defecto qwen2.5vl:3b gemma4:e2b)

Usa lo mismo que `servicio_pizarra`: la foto se normaliza igual, mismo pedido (`_PROMPT`), ventana de 4.096, temperatura 0,1,
tope de 700 tokens y `limpiar_repeticiones`; CPU con MEDIR_HILOS hilos (3). Mide el tiempo de cada foto y el pico de memoria del
proceso de Ollama. Las fotos de clase traen personas: el resultado se guarda FUERA del proyecto (`--salida`, por defecto
~/respaldo_comparaciones_IA/vision) y las fotos nunca se copian. Se sumaría un modelo nuevo a lo ya guardado.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["OLLAMA_DISPOSITIVO"] = "cpu"

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from nucleo import recursos  # noqa: E402

recursos.hilos_de_procesamiento = lambda: int(os.environ.get("MEDIR_HILOS", "3"))

from nucleo.configuracion import cargar_env  # noqa: E402

cargar_env()
from infraestructura import cliente_ollama  # noqa: E402
from servicios import servicio_pizarra as sp  # noqa: E402


def memoria_ollama_gb() -> float:
    pids = subprocess.run("pgrep -f '[l]lama-server'", shell=True, capture_output=True, text=True).stdout.split()
    total = 0
    for p in pids:
        try:
            m = re.search(r"VmRSS:\s+(\d+)", Path(f"/proc/{p}/status").read_text())  # sin VmRSS: el proceso se está cerrando
        except OSError:
            continue
        total += int(m.group(1)) if m else 0
    return total / 1048576


def descargar_todo(url: str) -> None:
    for linea in subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout.splitlines()[1:]:
        cliente_ollama.descargar_modelo(linea.split()[0], url)
    for _ in range(30):
        if memoria_ollama_gb() == 0:
            return
        time.sleep(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fotos", type=Path)
    ap.add_argument("modelos", nargs="*", default=["qwen2.5vl:3b", "gemma4:e2b"])
    ap.add_argument("--salida", type=Path, default=Path.home() / "respaldo_comparaciones_IA" / "vision")
    args = ap.parse_args()
    fotos = sorted(p for p in args.fotos.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"))
    if not fotos:
        print("No hay fotos en esa carpeta.")
        return 2
    args.salida.mkdir(parents=True, exist_ok=True)
    archivo = args.salida / "lecturas.json"
    todo = json.loads(archivo.read_text(encoding="utf-8")) if archivo.is_file() else {}
    url = sp.url_ollama()
    for modelo in args.modelos:
        print(f"\n=== {modelo} · {len(fotos)} fotos · CPU {recursos.hilos_de_procesamiento()} hilos ===", flush=True)
        descargar_todo(url)
        res = {}
        for ruta in fotos:
            imagen = base64.b64encode(sp._normalizar(ruta.read_bytes())).decode()
            pico, fin = [0.0], threading.Event()

            def muestrear():
                while not fin.is_set():
                    pico[0] = max(pico[0], memoria_ollama_gb())
                    time.sleep(0.5)

            threading.Thread(target=muestrear, daemon=True).start()
            t = time.time()
            try:
                texto = sp.limpiar_repeticiones(cliente_ollama.generate(
                    sp._PROMPT, modelo, 700, url, ventana=4096, imagenes=[imagen], opciones={"temperature": 0.1, "repeat_penalty": 1.1}).strip())
                error = None
            except Exception as e:  # noqa: BLE001
                texto, error = "", f"{type(e).__name__}: {e}"
            fin.set()
            res[ruta.name] = {"segundos": round(time.time() - t, 1), "pico_gb": round(pico[0], 2), "palabras": len(texto.split()), "texto": texto, "error": error}
            print(f"  {ruta.name[:12]:<12} {res[ruta.name]['segundos']:>5} s · {res[ruta.name]['palabras']:>3} palabras · pico {pico[0]:.2f} GB · {error or 'ok'}", flush=True)
        todo[modelo] = res
        archivo.write_text(json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8")
        descargar_todo(url)
    print(f"\nGuardado en {archivo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
