# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Compara los modos de limpieza de audio (`LIMPIEZA_AUDIO`) sobre un tramo de una clase REAL, por el pipeline real.

    python -m scripts.medir_limpieza "clase.webm" [--desde 20] [--minutos 5] [none light_dsp dsp ...]

Es lo que le faltaba al estudio de QA.md («Limpieza de audio disponible…», 2026-10-02), que midió con ruido artificial sobre una
clase ya limpia. Para cada modo mide el tiempo y qué tanto cambia el texto respecto de transcribir SIN limpiar (`none`). Ojo: no hay
transcripción de referencia, así que parecerse al texto sin limpiar no es ser mejor ni peor; por eso muestra las diferencias, para
leerlas. También estima el nivel de ruido del tramo (piso de ruido contra nivel de voz). Mismo equipo simulado que `medir_cpu`
(solo CPU, 3 hilos). El tramo se extrae a una carpeta temporal que se borra: el audio no se guarda.
"""
import argparse
import difflib
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

from scripts import medir_cpu as mc  # noqa: E402  (oculta la GPU y fija los hilos antes de importar Whisper)


def palabras_de(texto: str) -> list[tuple[str, str]]:
    """(palabra tal cual, palabra sin mayúsculas, tildes ni puntuación): una coma de más no es un cambio de palabras."""
    out = []
    for w in texto.split():
        n = re.sub(r"[^a-z0-9ñ]+", "", "".join(c for c in unicodedata.normalize("NFD", w.lower()) if unicodedata.category(c) != "Mn"))
        if n:
            out.append((w, n))
    return out


def nivel_de_ruido(wav: Path) -> dict:
    """Piso de ruido (percentil 10 de la energía por ventanas de 50 ms) y nivel de voz (percentil 90), en dBFS."""
    import numpy as np
    from scipy.io import wavfile

    sr, datos = wavfile.read(str(wav))
    x = datos.astype("float32") / 32768.0
    n = int(sr * 0.05)
    ventanas = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((ventanas**2).mean(axis=1)) + 1e-9)
    piso, voz = float(np.percentile(db, 10)), float(np.percentile(db, 90))
    return {"piso_dbfs": round(piso, 1), "voz_dbfs": round(voz, 1), "diferencia_db": round(voz - piso, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("modos", nargs="*", default=["none", "light_dsp", "dsp"])
    ap.add_argument("--desde", type=int, default=20)
    ap.add_argument("--minutos", type=int, default=5)
    args = ap.parse_args()
    if not args.audio.is_file():
        print(f"No existe el archivo: {args.audio}")
        return 2
    from servicios import servicio_grabacion as sg

    with tempfile.TemporaryDirectory(prefix="medir-limpieza-") as carpeta:
        wav = Path(carpeta) / "tramo.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(args.desde * 60), "-t", str(args.minutos * 60), "-i", str(args.audio), "-ac", "1", "-ar", "16000", str(wav)], check=True)
        ruido = nivel_de_ruido(wav)
        print(f"Tramo de {args.minutos} min (minuto {args.desde}): piso de ruido {ruido['piso_dbfs']} dBFS, voz {ruido['voz_dbfs']} dBFS, diferencia {ruido['diferencia_db']} dB "
              "(más de ~35 dB es un audio limpio; menos de ~20, ruidoso)", flush=True)
        textos: dict[str, str] = {}
        tiempos: dict[str, float] = {}
        for modo in args.modos:
            os.environ["LIMPIEZA_AUDIO"] = modo  # `transcribir` lo lee en cada llamada
            t = time.time()
            textos[modo], _ = sg.transcribir(str(wav))
            tiempos[modo] = time.time() - t
            print(f"  {modo:<10} {tiempos[modo]:5.1f} s · {len(textos[modo].split())} palabras", flush=True)

    referencia = palabras_de(textos.get("none") or next(iter(textos.values())))
    print("\n--- Cuánto cambian las PALABRAS respecto de transcribir SIN limpiar (sin contar mayúsculas, tildes ni puntuación) ---")
    resultado = {"ruido": ruido, "tramo_min": args.minutos, "hilos": mc.HILOS, "modos": {}}
    for modo, texto in textos.items():
        pal = palabras_de(texto)
        parecido = difflib.SequenceMatcher(None, [n for _, n in referencia], [n for _, n in pal], autojunk=False)
        cambios = [(" ".join(w for w, _ in referencia[i1:i2]), " ".join(w for w, _ in pal[j1:j2])) for tag, i1, i2, j1, j2 in parecido.get_opcodes() if tag != "equal"]
        print(f"{modo:<10} {parecido.ratio() * 100:5.1f} % igual · {len(cambios)} cambios · {tiempos[modo]:.0f} s")
        for antes, despues in cambios[:10]:
            print(f"     sin limpiar: «{antes[:60]}»  →  {modo}: «{despues[:60]}»")
        resultado["modos"][modo] = {"segundos": round(tiempos[modo], 1), "palabras": len(pal), "igual_a_sin_limpiar_pct": round(parecido.ratio() * 100, 1), "cambios": len(cambios)}
    mc.guardar("limpieza_de_audio", resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
