# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Procesa la grabación de una clase de verdad con el mismo pipeline de la aplicación y guarda el resultado para el demo.

    python -m scripts.procesar_clase_real "ruta/clase.webm" --asignatura "Nombre de la asignatura"

Transcribe con Whisper, genera el material con Ollama y arma el mapa conceptual, igual que cuando termina una grabación
(`servicio_grabacion.transcribir`, `generar_material` y `generar_mapa`). Todo corre en este equipo. Mide los tiempos.

El audio no se copia ni se guarda. El resultado (solo texto) queda en `demo_clase_real.json`, que está en .gitignore:
es una clase real, con voces y posiblemente nombres de personas. Revísalo antes de compartirlo o commitearlo.
`python -m scripts.sembrar_demo` lo agrega al demo si ese archivo existe.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from nucleo.configuracion import cargar_env  # noqa: E402

cargar_env()

SALIDA_POR_DEFECTO = RAIZ / "demo_clase_real.json"


def duracion_s(ruta: Path) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path, help="grabación de la clase (webm, mp3, wav…)")
    ap.add_argument("--asignatura", default=None, help="asignatura, para que el material la tenga en cuenta")
    ap.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    args = ap.parse_args()
    if not args.audio.is_file():
        print(f"No existe el archivo: {args.audio}")
        return 2

    from servicios import servicio_grabacion as sg
    from servicios.servicio_material_estudio import _modelo_que_cabe, _resolve_ollama_model
    from nucleo import configuracion as app_config

    duracion = duracion_s(args.audio)
    print(f"Clase: {args.audio.name} · {duracion / 60:.1f} min" if duracion else f"Clase: {args.audio.name}")
    tiempos: dict[str, float] = {}

    t = time.time()
    print(f"1/3 Transcribiendo con Whisper ({sg.MODELO_WHISPER})… (puede tardar)")
    texto, srt = sg.transcribir(str(args.audio))
    tiempos["transcripcion_s"] = round(time.time() - t, 1)
    print(f"    listo en {tiempos['transcripcion_s'] / 60:.1f} min · {len(texto.split())} palabras")
    if not texto.strip():
        print("No se detectó voz en el audio.")
        return 1

    configurado = app_config.get_param("ollama_model")
    modelo_texto = _modelo_que_cabe(_resolve_ollama_model(configurado), es_auto=configurado == "auto")
    t = time.time()
    print(f"2/3 Generando el material con Ollama ({modelo_texto})…")
    resumen, puntos, hoja, tarjetas = sg.generar_material(texto, args.asignatura)
    tiempos["material_s"] = round(time.time() - t, 1)
    print(f"    listo en {tiempos['material_s']:.0f} s · {len(tarjetas)} tarjetas")

    t = time.time()
    print("3/3 Armando el mapa conceptual…")
    mapa = sg.generar_mapa(resumen, puntos, args.asignatura) or None
    tiempos["mapa_s"] = round(time.time() - t, 1)
    print(f"    {'sin mapa (el modelo no dio para eso)' if not mapa else f'{len(mapa)} relaciones'} · {tiempos['mapa_s']:.0f} s")

    resultado = {
        "archivo": args.audio.name,
        "asignatura": args.asignatura,
        "duracion_s": duracion,
        "modelo_whisper": sg.MODELO_WHISPER,
        "modelo_texto": modelo_texto,
        "tiempos": tiempos,
        "transcripcion_texto": texto,
        "transcripcion_srt": srt,
        "resumen": resumen,
        "puntos_clave": puntos,
        "hoja_repaso": hoja,
        "tarjetas": tarjetas,
        "mapa_conceptual": mapa,
    }
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {args.salida} (solo texto; el audio no se copió).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
