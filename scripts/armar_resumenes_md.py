# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Arma `demo_resumenes_ia.md`: todo lo que generó la IA sobre la clase real, una sección por modelo.

    python -m scripts.armar_resumenes_md

Junta los resultados de `procesar_clase_real` (la clase), `comparar_modelos` (material de la clase completa por modelo) y
`medir_cpu llm` (un bloque en solo CPU, diez modelos). El resultado trae texto de una clase real: está en .gitignore.
"""
import datetime
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from nucleo import configuracion as app_config  # noqa: E402
from nucleo import limpieza_texto  # noqa: E402
from servicios import servicio_material_estudio as sme  # noqa: E402

NOMBRES = {"llama3.2:1b": "Llama 3.2 1B", "llama3.2:3b": "Llama 3.2 3B", "qwen2.5vl:3b": "Qwen2.5-VL 3B (solo texto)", "gemma3:1b": "Gemma 3 1B", "gemma3:4b": "Gemma 3 4B",
           "qwen3:1.7b": "Qwen3 1.7B", "qwen3.5:2b": "Qwen3.5 2B", "qwen3.5:4b": "Qwen3.5 4B", "granite4:micro": "Granite 4 micro (3B)", "phi4-mini:3.8b": "Phi-4-mini 3.8B", "gemma4:e2b": "Gemma 4 E2B", "gemma4:e4b": "Gemma 4 E4B", "lfm3:1.7b": "LFM3 1.7B", "ministral-3:3b": "Ministral 3 3B", "bonsai-2:4b": "Bonsai 2 4B"}
ORDEN_CPU = ("gemma4:e2b", "gemma3:1b", "qwen3:1.7b", "llama3.2:1b", "llama3.2:3b", "qwen3.5:2b", "granite4:micro", "phi4-mini:3.8b", "gemma3:4b", "qwen3.5:4b")


def nombre(m: str) -> str:
    base, _, sufijo = m.partition(" [CPU]")
    if " [CPU]" not in m:
        return NOMBRES.get(m, m) + " (GPU)"
    return NOMBRES.get(base, base) + f" (CPU, 3 hilos{', repetición' + sufijo if sufijo.strip() else ''})"


def plano(t: str) -> str:
    """Los títulos de Markdown que escribe un modelo (`### 1. …`) se ven como texto, no como secciones de este documento."""
    return re.sub(r"(?m)^(\s*)(#+)", r"\1\\\2", t.strip())


def mapa(rel) -> str:
    return "\n".join(f"- {r['de']} —{r['relacion']}→ {r['a']}" for r in rel) if rel else "*(sin mapa)*"


def main() -> int:
    real = json.loads((RAIZ / "demo_clase_real.json").read_text(encoding="utf-8"))
    comp = json.loads((RAIZ / "demo_comparacion_modelos.json").read_text(encoding="utf-8"))
    med = json.loads((RAIZ / "demo_medicion_cpu.json").read_text(encoding="utf-8"))
    salidas = json.loads((RAIZ / "demo_medicion_cpu_salidas.json").read_text(encoding="utf-8"))
    texto = limpieza_texto.limpiar_transcripcion(real["transcripcion_texto"])
    bloques = sme._split_into_chunks(texto, max_chars=int(app_config.get_param("ollama_chunk_chars")))
    bloque = bloques[0]
    orden = [m for m in ORDEN_CPU if f"llm_cpu_{m}" in med]

    L = ["# Lo que generó la IA sobre la clase real", "",
         "> ⚠️ Contiene texto derivado de una clase real (transcripción y material). **No se sube a git** (`.gitignore`). Todo se generó en este equipo, con Ollama; el audio nunca salió de él.", "",
         f"Clase: «{real.get('asignatura')}», {real['duracion_s'] / 60:.1f} min. Generado el {datetime.date.today().isoformat()}. Hay dos partes: **(1)** el material de la **clase completa** con tres modelos "
         "(en GPU, 9 bloques condensados y una pasada final) y **(2)** una **prueba por bloque en solo CPU** (3 hilos, como un equipo de 4 núcleos) con diez modelos sobre el mismo bloque de ~1.000 palabras. "
         "Los criterios son los de la aplicación: texto limpiado con `limpiar_transcripcion`, bloques de 6.000 caracteres, temperatura 0,3, las mismas indicaciones, y `think: false` (sin esto los modelos con pensamiento devuelven la respuesta vacía).", "",
         "## Parte 1 — Material de la clase completa", "", "| Modelo | Tiempo | Palabras del resumen | Puntos clave | Tarjetas | Mapa |", "|---|---|---|---|---|---|"]
    for m, r in comp.items():
        if r.get("error"):
            L.append(f"| {nombre(m)} | {r['material_s']:.0f} s | **falló:** {r['error'][:70]} | | | |")
            continue
        rel = (r.get("mapa_app") or {}).get("relaciones") or []
        puntos = len([x for x in r["puntos_clave"].splitlines() if x.strip()])
        L.append(f"| {nombre(m)} | {r['material_s']:.0f} s | {len(r['resumen'].split())} | {puntos} | {len(r['tarjetas'])} | {str(len(rel)) + ' relaciones' if rel else 'ninguno (la app lo descarta)'} |")
    L.append("")
    for m, r in comp.items():
        if r.get("error"):
            continue
        rel = (r.get("mapa_app") or {}).get("relaciones") or []
        L += [f"### {nombre(m)}", "", f"*Tardó {r['material_s']:.0f} s.*", "", "#### Resumen", "", plano(r["resumen"]), "", "#### Puntos clave", "", plano(r["puntos_clave"]), "",
              "#### Hoja de repaso", "", plano(r["hoja_repaso"]), "", "#### Mapa conceptual", ""]
        if rel:
            L += [mapa(rel), ""]
        else:
            L += ["*Con este modelo la aplicación descarta el mapa. Lo que salió al forzarlo (para ver por qué):*", "", mapa((r.get("mapa_forzado") or {}).get("relaciones")), ""]
        L += ["#### Tarjetas de estudio", ""]
        for i, t in enumerate(r["tarjetas"], 1):
            L += [f"{i}. **P:** {t.get('pregunta', '').strip()}  ", f"   **R:** {t.get('respuesta', '').strip()}"]
        L += ["", "---", ""]

    L += ["## Parte 2 — Un bloque de la clase en solo CPU, diez modelos", "",
          f"Mismo bloque para todos ({len(bloque.split())} palabras, el primero de {len(bloques)}), 3 hilos, sin GPU, ordenados de más a menos rápido en condensarlo. "
          "«Fundamentación» es una medida gruesa: la fracción de las palabras de 5 o más letras que dijo el modelo y que están en el bloque; no reemplaza leerlo.", "",
          "| Modelo | Carga | Condensar el bloque | Palabras | Fundamentación | Mapa (relaciones · tiempo) | Resultado |", "|---|---|---|---|---|---|---|"]
    for m in orden:
        r = med[f"llm_cpu_{m}"]
        L.append(f"| {nombre(m)} | {r.get('carga_s', '—')} s | {r.get('bloque_s', '—')} s | {r.get('palabras', 0)} | {r.get('fundamentacion', '—')} | {len(r.get('mapa', []))} · {r.get('mapa_s')} s | "
                 + ("ok" if not r.get("error") else f"**falló:** {r['error'][:60]}") + " |")
    L += ["", "<details><summary>El bloque original (lo que se les dio a leer)</summary>", "", bloque.strip(), "", "</details>", ""]
    for m in orden:
        r = med[f"llm_cpu_{m}"]
        L += [f"### {nombre(m)}", "", f"*Condensó el bloque en {r.get('bloque_s')} s; mapa en {r.get('mapa_s')} s.*", "", "#### Condensación del bloque", "",
              plano(salidas.get(m) or f"*Sin texto: {r.get('error')}*"), "", "#### Mapa conceptual", "", mapa(r.get("mapa")), "", "---", ""]

    (RAIZ / "demo_resumenes_ia.md").write_text("\n".join(L), encoding="utf-8")
    print(f"demo_resumenes_ia.md: {len(orden)} modelos en CPU, {len(comp)} de clase completa, {len(L)} líneas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
