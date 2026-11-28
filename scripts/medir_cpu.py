# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Mide cuánto tarda el procesamiento en un equipo modesto: SOLO CPU y pocos hilos (por defecto 3 = un equipo de 4 núcleos
con uno libre), con el mismo código y las mismas indicaciones que usa la aplicación.

    python -m scripts.medir_cpu whisper "clase.webm" [--desde 20] [--minutos 5]   # Whisper en CPU sobre un tramo
    python -m scripts.medir_cpu whisper "clase.webm" --gpu                        # el mismo tramo con GPU, para comparar
    python -m scripts.medir_cpu llm llama3.2:1b llama3.2:3b gemma3:4b             # condensar un bloque de la clase real

Criterios: son los de la aplicación, no los de una llamada directa a Whisper. `whisper` pasa por `servicio_grabacion.transcribir`, así
que lleva la misma limpieza de audio (`LIMPIEZA_AUDIO`, por defecto `light_dsp`: filtro pasa-altos de 80 Hz, resta suave de ruido y
normalización de entrada y de salida) y la misma decodificación (español, `int8`, en CPU beam 1 y filtro de silencios). `llm` limpia el
texto con `limpiar_transcripcion` (quita frases alucinadas y palabras repetidas en bucle) y usa los mismos bloques (`ollama_chunk_chars`),
indicaciones, temperatura y tope de tokens que la aplicación. Cada resultado guarda esos valores, y el detalle está en QA.md
(«Mediciones de tiempo en CPU»). Cuánto cambia la limpieza el texto y el tiempo se mide aparte, con scripts/medir_limpieza.py.

`whisper` extrae el tramo a una carpeta temporal (se borra al terminar: el audio nunca se guarda) y extrapola a la clase
completa. `llm` usa el texto de `demo_clase_real.json` (lo crea scripts/procesar_clase_real.py). Los resultados se suman a
`demo_medicion_cpu.json` (ignorado por git). Cuidado: mientras mide no corras otra cosa pesada, o los tiempos salen peores.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
HILOS = int(os.environ.get("MEDIR_HILOS", "3"))
if "--gpu" not in sys.argv:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # PyTorch y CTranslate2 no ven la GPU: igual que un equipo sin ella
if "llm" in sys.argv:
    os.environ["OLLAMA_DISPOSITIVO"] = "cpu"  # Ollama genera sin GPU (num_gpu = 0)

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from nucleo import recursos  # noqa: E402

recursos.hilos_de_procesamiento = lambda: HILOS  # antes de importar a quienes la usan (Whisper y el cliente de Ollama)

from nucleo.configuracion import cargar_env  # noqa: E402

cargar_env()

SALIDA = RAIZ / "demo_medicion_cpu.json"
CLASE_REAL = RAIZ / "demo_clase_real.json"


def guardar(clave: str, datos: dict) -> None:
    todo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.is_file() else {}
    todo[clave] = datos
    SALIDA.write_text(json.dumps(todo, ensure_ascii=False, indent=2), encoding="utf-8")


def whisper(args) -> int:
    from servicios import servicio_grabacion as sg

    if not args.audio.is_file():
        print(f"No existe el archivo: {args.audio}")
        return 2
    segundos_audio = args.minutos * 60
    with tempfile.TemporaryDirectory(prefix="medir-cpu-") as carpeta:  # el tramo se borra al salir
        tramo = Path(carpeta) / "tramo.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(args.desde * 60), "-t", str(segundos_audio), "-i", str(args.audio), "-ac", "1", "-ar", "16000", str(tramo)], check=True)
        import torch

        dispositivo = "GPU" if torch.cuda.is_available() else f"CPU ({HILOS} hilos)"
        print(f"Whisper «{sg.MODELO_WHISPER}» en {dispositivo} sobre {args.minutos} min del minuto {args.desde}…", flush=True)
        t = time.time()
        texto, _ = sg.transcribir(str(tramo))
        s = time.time() - t
    factor = s / segundos_audio
    palabras = len(texto.split())
    print(f"  listo en {s:.0f} s ({s / 60:.1f} min) · {palabras} palabras · {factor:.2f} s de proceso por cada s de audio")
    for minutos in (62.6, 90):
        print(f"  extrapolado a una clase de {minutos:g} min: ~{factor * minutos:.0f} min")
    from nucleo import configuracion as app_config

    limpieza = sg.config_de_limpieza()
    print(f"  criterios: limpieza {limpieza['denoise_mode']} (pasa-altos {limpieza['highpass_hz']} Hz, normalización de entrada y salida) · español · beam {1 if not args.gpu else app_config.get_param('beam_size')} · VAD {app_config.get_param('vad_filter')}")
    guardar(f"whisper_{'gpu' if '--gpu' in sys.argv else 'cpu'}", {"modelo": sg.MODELO_WHISPER, "dispositivo": dispositivo, "hilos": HILOS, "minutos_de_audio": args.minutos, "segundos": round(s, 1), "palabras": palabras, "factor": round(factor, 3), "limpieza": limpieza, "vad": app_config.get_param("vad_filter")})
    return 0


def sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def palabras_de(t: str) -> set[str]:
    return set(re.findall(r"[a-zñ]{5,}", sin_tildes(t)))


def llm(args) -> int:
    from infraestructura import cliente_ollama as oc
    from nucleo import configuracion as app_config
    from nucleo import limpieza_texto
    from servicios import servicio_material_estudio as sme

    if not CLASE_REAL.is_file():
        print("Falta demo_clase_real.json (scripts/procesar_clase_real.py).")
        return 2
    real = json.loads(CLASE_REAL.read_text(encoding="utf-8"))
    texto = limpieza_texto.limpiar_transcripcion(real["transcripcion_texto"])
    url = os.environ.get("OLLAMA_URL") or app_config.get_param("ollama_url")
    chunks = sme._split_into_chunks(texto, max_chars=int(app_config.get_param("ollama_chunk_chars")))
    bloque = chunks[0]
    vocabulario = palabras_de(bloque)
    print(f"Bloque de prueba: {len(bloque.split())} palabras (la clase tiene {len(chunks)} bloques) · solo CPU, {HILOS} hilos\n", flush=True)
    resultados = {}
    for modelo in args.modelos:
        print(f"=== {modelo} ===", flush=True)
        r: dict = {}
        t = time.time()
        try:
            oc.generate("Responde solo: ok", model=modelo, max_tokens=2, ollama_url=url)
            r["carga_s"] = round(time.time() - t, 1)
            t = time.time()
            salida = sme._condense_transcript([bloque], modelo, url, real.get("asignatura")).replace("[Parte 1/1]", "").strip()
            r["bloque_s"] = round(time.time() - t, 1)
            p = palabras_de(salida)
            r.update(palabras=len(salida.split()), fundamentacion=round(len(p & vocabulario) / len(p), 2) if p else 0, salida=salida)
        except Exception as e:  # noqa: BLE001
            r["error"] = f"{type(e).__name__}: {e}"
        # Mapa conceptual con un resumen fijo igual para todos (el de 1B lo descarta la app a propósito: se mide igual).
        app_config.get_param = lambda k, _m=modelo: _m if k == "ollama_model" else app_config.DEFAULT_CONFIG.get(k)  # noqa: E731
        anterior, sme._OLLAMA_MODEL_MINIMO = sme._OLLAMA_MODEL_MINIMO, "ninguno"
        t = time.time()
        try:
            r["mapa"] = sme.generar_mapa_conceptual(real["resumen"], real["puntos_clave"], real.get("asignatura"))
        except Exception:  # noqa: BLE001
            r["mapa"] = []
        sme._OLLAMA_MODEL_MINIMO = anterior
        r["mapa_s"] = round(time.time() - t, 1)
        print(f"  carga {r.get('carga_s')} s · bloque {r.get('bloque_s')} s · {r.get('palabras', 0)} palabras · fundamentación {r.get('fundamentacion')} · mapa {len(r['mapa'])} rel. en {r['mapa_s']} s · {r.get('error', 'ok')}", flush=True)
        resultados[modelo] = r
        guardar(f"llm_cpu_{modelo}", {k: v for k, v in r.items() if k != "salida"} | {"hilos": HILOS, "chunk_chars": int(app_config.get_param("ollama_chunk_chars")), "max_tokens": int(app_config.get_param("ollama_max_tokens")), "texto_limpio_con": "limpiar_transcripcion"})
        archivo = RAIZ / "demo_medicion_cpu_salidas.json"  # se suma a lo de corridas anteriores: no se borran los textos de otros modelos
        previas = json.loads(archivo.read_text(encoding="utf-8")) if archivo.is_file() else {}
        archivo.write_text(json.dumps(previas | {m: x.get("salida") for m, x in resultados.items()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n--- RESUMEN (solo CPU) ---")
    print(f"{'modelo':<16}{'carga':>7}{'bloque':>8}{'x9 bloques':>12}{'fund.':>7}{'mapa':>6}{'mapa s':>8}")
    for m, r in resultados.items():
        print(f"{m:<16}{r.get('carga_s', 0):>6.0f}s{r.get('bloque_s', 0):>7.0f}s{r.get('bloque_s', 0) * len(chunks) / 60:>10.0f} m{r.get('fundamentacion', 0):>7}{len(r.get('mapa', [])):>6}{r.get('mapa_s', 0):>7.0f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modo", required=True)
    w = sub.add_parser("whisper")
    w.add_argument("audio", type=Path)
    w.add_argument("--desde", type=int, default=20, help="minuto desde el que se toma el tramo")
    w.add_argument("--minutos", type=int, default=5)
    w.add_argument("--gpu", action="store_true", help="con GPU (por defecto: solo CPU)")
    m = sub.add_parser("llm")
    m.add_argument("modelos", nargs="+")
    args = ap.parse_args()
    return whisper(args) if args.modo == "whisper" else llm(args)


if __name__ == "__main__":
    sys.exit(main())
