"""Compara modelos de Ollama generando el material de una clase real (misma transcripción, mismo código del proyecto).

    python -m scripts.comparar_modelos [--cpu] [modelo ...]      (por defecto llama3.2:1b llama3.2:3b qwen2.5vl:3b)

Con --cpu corre como el servidor del colegio (sin GPU, MEDIR_HILOS hilos, 3 por defecto) y guarda cada modelo como «modelo [CPU]».
Los resultados se suman a los de corridas anteriores; no se borran.

Usa la transcripción de demo_clase_real.json (la crea scripts/procesar_clase_real.py) y deja el detalle en
demo_comparacion_modelos.json (ignorado por git: trae texto de una clase real). «fundamentación» es una medida
gruesa: la fracción de las palabras de 5+ letras del material que aparecen en lo que se dijo en clase; no reemplaza leerlo."""
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
CPU = "--cpu" in sys.argv
if CPU:
    sys.argv.remove("--cpu")
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    os.environ["OLLAMA_DISPOSITIVO"] = "cpu"
    from nucleo import recursos  # noqa: E402

    recursos.hilos_de_procesamiento = lambda: int(os.environ.get("MEDIR_HILOS", "3"))  # antes de importar a quienes la usan
from nucleo import configuracion as app_config  # noqa: E402
from nucleo.configuracion import cargar_env  # noqa: E402

cargar_env()
from servicios import servicio_grabacion as sg  # noqa: E402
from servicios import servicio_material_estudio as sme  # noqa: E402

SALIDA = RAIZ / "demo_comparacion_modelos.json"
real = json.loads((RAIZ / "demo_clase_real.json").read_text(encoding="utf-8"))
texto, asignatura = real["transcripcion_texto"], real["asignatura"]
modelos = sys.argv[1:] or ["llama3.2:1b", "llama3.2:3b", "qwen2.5vl:3b"]


def sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def palabras(t: str) -> set[str]:
    return set(re.findall(r"[a-zñ]{5,}", sin_tildes(t)))


VOCAB_CLASE = palabras(texto)
ES = set("que los las una por con para como pero este esta esto sobre entre desde hasta donde cuando tambien porque ademas segun puede pueden".split())
EN = set("the and with that this from which their where when also because about between through".split())


def fundamentacion(t: str) -> float:
    """Qué fracción de las palabras (de 5+ letras) del material aparece en lo que se dijo en la clase."""
    p = palabras(t)
    return len(p & VOCAB_CLASE) / len(p) if p else 0.0


def idioma(t: str) -> str:
    bajas = re.findall(r"[a-zñáéíóúü]+", t.lower())
    es, en = sum(w in ES for w in bajas), sum(w in EN for w in bajas)
    no_latino = sum(1 for c in t if ord(c) > 0x2E80)
    return f"es={es} en={en} no_latino={no_latino}"


SUFIJO = (" [CPU]" if CPU else "") + os.environ.get("ETIQUETA", "")  # ETIQUETA=" #2" guarda una repetición aparte
resultados = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.is_file() else {}
for modelo in modelos:
    print(f"\n=== {modelo} ===", flush=True)
    app_config.get_param = lambda k, _m=modelo: _m if k == "ollama_model" else app_config.DEFAULT_CONFIG.get(k)  # noqa: E731
    r: dict = {}
    t = time.time()
    try:
        resumen, puntos, hoja, tarjetas = sg.generar_material(texto, asignatura)
        r["material_s"] = round(time.time() - t, 1)
        todo = f"{resumen}\n{puntos}\n{hoja}\n" + " ".join(f"{x.get('pregunta', '')} {x.get('respuesta', '')}" for x in tarjetas)
        r.update(
            resumen=resumen, puntos_clave=puntos, hoja_repaso=hoja, tarjetas=tarjetas,
            palabras_resumen=len(resumen.split()), puntos=len([l for l in puntos.splitlines() if l.strip()]),
            palabras_hoja=len(hoja.split()), n_tarjetas=len(tarjetas),
            fundamentacion=round(fundamentacion(todo), 3), idioma=idioma(todo),
        )
    except Exception as e:  # noqa: BLE001
        r.update(error=f"{type(e).__name__}: {e}", material_s=round(time.time() - t, 1))
    print(f"  material: {r.get('material_s')} s · {r.get('error', 'ok')}", flush=True)

    # Mapa conceptual: como lo haría la app (el modelo de 1B se descarta a propósito) y, aparte, forzándolo para ver su calidad.
    for etiqueta, forzar in (("mapa_app", False), ("mapa_forzado", True)):
        if forzar and modelo != sme._OLLAMA_MODEL_MINIMO:
            continue
        anterior = sme._OLLAMA_MODEL_MINIMO
        if forzar:
            sme._OLLAMA_MODEL_MINIMO = "modelo-que-no-existe"
        t = time.time()
        try:
            mapa = sme.generar_mapa_conceptual(r.get("resumen", ""), r.get("puntos_clave", ""), asignatura) if "resumen" in r else []
        except Exception as e:  # noqa: BLE001
            mapa = []
        finally:
            sme._OLLAMA_MODEL_MINIMO = anterior
        ok = [m for m in mapa if palabras(m["de"]) <= VOCAB_CLASE and palabras(m["a"]) <= VOCAB_CLASE and palabras(m["de"] + m["a"])]
        r[etiqueta] = {"relaciones": mapa, "n": len(mapa), "fundamentadas": len(ok), "s": round(time.time() - t, 1)}
        print(f"  {etiqueta}: {len(mapa)} relaciones ({len(ok)} con conceptos que se dijeron en clase) · {r[etiqueta]['s']} s", flush=True)
    resultados[modelo + SUFIJO] = r
    SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

print("\n--- RESUMEN ---")
print(f"{'modelo':<16}{'tiempo':>8}{'resumen':>9}{'puntos':>8}{'hoja':>7}{'tarj.':>7}{'fundam.':>9}  idioma / mapa(app)")
for m, r in resultados.items():
    print(f"{m:<16}{r.get('material_s', 0):>7.0f}s{r.get('palabras_resumen', 0):>9}{r.get('puntos', 0):>8}{r.get('palabras_hoja', 0):>7}{r.get('n_tarjetas', 0):>7}{r.get('fundamentacion', 0):>9.2f}  {r.get('idioma', r.get('error', ''))} / {r.get('mapa_app', {}).get('n', '-')}")
