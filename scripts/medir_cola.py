# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Mide la cola de procesamiento de punta a punta, como la vería el colegio: cuánto espera cada clase, cuánto tarda en procesarse y cuánta
memoria usa el conjunto (servidor, trabajador y modelo de Ollama).

    python -m scripts.medir_cola clase.webm                    # dos clases iguales en cola (la segunda espera a la primera)
    python -m scripts.medir_cola clase.webm --clases 1         # una sola clase: cuánto tarda el procesamiento solo
    python -m scripts.medir_cola clase.webm --salida cola.json

Levanta un servidor temporal (base y carpetas propias, nada del colegio), da de alta una profesora y un curso por cada clase, sube el audio
en trozos de 7 MB como lo hace el equipo grabador (el servidor admite hasta 8 MB por trozo) y mira, cada 2 segundos, el estado que vería
el profesor (`posicion_en_cola`). Con `PROCESAMIENTOS_SIMULTANEOS` en 1 (lo normal) las clases se procesan de a una.

Para parecerse a un PC escolar no basta con apagar la GPU: hay que limitar los núcleos y que la aplicación crea que solo tiene esos, y que Ollama
corra con la misma restricción (el servicio del sistema usaría los núcleos rápidos: hay que levantar uno propio dentro de la restricción, con
`OLLAMA_URL`). Ejemplo en Linux (núcleos 8 a 11 = los lentos de un i5 de 13.ª generación, 12 GB de memoria como máximo, sin GPU;
`PYTHON_CPU_COUNT=4` hace que `os.cpu_count()` diga 4, así la aplicación usa 3 hilos como en un PC de 4 núcleos):

    systemd-run --user --scope -p MemoryMax=12G -- taskset -c 8-11 env PYTHON_CPU_COUNT=4 CUDA_VISIBLE_DEVICES=-1 OLLAMA_DISPOSITIVO=cpu \\
        OLLAMA_URL=http://127.0.0.1:11435 python -m scripts.medir_cola clase.webm

Ojo: `systemd-run -p AllowedCPUs=…` NO limita los núcleos en una sesión de usuario sin delegación de `cpuset` (devuelve éxito y no hace nada;
se comprobó): `taskset` sí.

El audio es de una clase real: no se guarda ni se copia (solo se lee) y el servidor temporal lo borra al terminar de procesarlo.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from scripts import prueba_de_humo as ph  # noqa: E402

TROZO_BYTES = 7 * 1024 * 1024  # el servidor admite hasta 8 MB por trozo
SONDEO_S = 2


def duracion_min(audio: Path) -> float:
    sal = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)], capture_output=True, text=True)
    return float(sal.stdout.strip()) / 60


def clasificar(cmd: str) -> str | None:
    if "llama-server" in cmd or "ollama_llama" in cmd:
        return "modelo de Ollama"
    if "servicios.trabajador" in cmd:
        return "trabajador (Whisper)"
    if "uvicorn" in cmd and "api:app" in cmd:
        return "servidor web"
    return None


class Muestreador(threading.Thread):
    """Cada segundo suma la memoria (RSS) de cada tipo de proceso. En Linux; en otros sistemas no mide y lo dice."""

    def __init__(self):
        super().__init__(daemon=True)
        self.pico: dict[str, float] = {}
        self.pico_total = 0.0
        self.linea: list[tuple[float, dict[str, float]]] = []
        self.parar = threading.Event()
        self.t0 = time.monotonic()

    def run(self) -> None:
        if not Path("/proc").is_dir():
            return
        while not self.parar.is_set():
            suma: dict[str, float] = {}
            for pid in filter(str.isdigit, os.listdir("/proc")):
                try:
                    tipo = clasificar(Path(f"/proc/{pid}/cmdline").read_text().replace("\0", " "))
                    if tipo:
                        m = re.search(r"VmRSS:\s+(\d+)", Path(f"/proc/{pid}/status").read_text())
                        suma[tipo] = suma.get(tipo, 0.0) + (int(m.group(1)) / 1048576 if m else 0.0)
                except OSError:
                    pass
            for k, v in suma.items():
                self.pico[k] = max(self.pico.get(k, 0.0), v)
            self.pico_total = max(self.pico_total, sum(suma.values()))
            self.linea.append((time.monotonic() - self.t0, suma))
            time.sleep(1)

    def primer_modelo_cargado_desde(self, t: float) -> float | None:
        """El primer instante, a partir de `t`, en que el modelo de Ollama ocupa más de 1 GB: ahí empieza el resumen."""
        return next((x for x, suma in self.linea if x >= t and suma.get("modelo de Ollama", 0.0) > 1.0), None)


def preparar(s: ph.Servidor, n: int) -> tuple[str, list[tuple[str, int]]]:
    """Un colegio nuevo con su UTP y, por cada clase, una profesora, un curso y un bloque de hoy (así no se estorban ni chocan en el horario)."""
    hoy = time.localtime().tm_wday
    inicio = ph.exigir(s.llamar("POST", "/auth/setup", {"colegio_nombre": "Colegio de la medición", "rut": ph.rut(11111111), "nombre": "UTP de la medición", "password": ph.CLAVE}), 201, "Crear el colegio")
    token_utp, colegio_id = inicio["access_token"], inicio["colegio_id"]
    clases = []
    for i in range(n):
        rut_prof = ph.rut(12345678 + 1111 * i)
        ph.exigir(s.llamar("POST", "/usuarios", {"rut": rut_prof, "nombre": f"Profesora {i + 1}", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": ph.CLAVE}, token=token_utp), 201, "Crear la profesora")
        curso = ph.exigir(s.llamar("POST", "/cursos", {"nombre": f"Curso {i + 1}", "colegio_id": colegio_id}, token=token_utp), 201, "Crear el curso")
        token = ph.exigir(s.llamar("POST", "/auth/login/staff", {"rut": rut_prof, "password": ph.CLAVE}), 200, "Entrar como profesora")["access_token"]
        pid = ph.exigir(s.llamar("GET", "/auth/me", token=token), 200, "Ver a la profesora")["id"]
        bloque = ph.exigir(s.llamar("POST", f"/cursos/{curso['id']}/bloques", {"tipo": "CLASE", "asignatura": f"Asignatura {i + 1}", "profesor_id": pid, "sala": "S1", "dia_semana": hoy, "hora_inicio": "00:00", "hora_fin": "23:59"}, token=token_utp), 201, "Crear el bloque")
        clases.append((token, bloque["id"]))
    return token_utp, clases


def grabar_en_trozos(s: ph.Servidor, token: str, bloque_id: int, audio: Path) -> int:
    """Lo que hace el equipo grabador: iniciar, subir el audio (en trozos que se unen en orden), terminar y finalizar. Devuelve el id de la sesión."""
    equipo = "equipo-de-la-medicion"
    gid = ph.exigir(s.llamar("POST", "/grabaciones", {"bloque_id": bloque_id}, token=token), 201, "Crear la sesión")["id"]
    ph.exigir(s.llamar("POST", f"/grabaciones/{gid}/grabador", {"dispositivo": equipo, "forzar": True}, token=token), 200, "Registrar el equipo grabador")
    ph.exigir(s.llamar("POST", f"/grabaciones/{gid}/comando", {"accion": "iniciar"}, token=token), 200, "Iniciar")
    datos = audio.read_bytes()
    for i in range(0, len(datos), TROZO_BYTES):
        ph.exigir(s.llamar("PUT", f"/grabaciones/{gid}/trozos/{i // TROZO_BYTES}", datos=datos[i:i + TROZO_BYTES], tipo=ph.tipo_de_audio(audio), token=token, params={"dispositivo": equipo}), 200, "Subir un trozo")
    ph.exigir(s.llamar("POST", f"/grabaciones/{gid}/comando", {"accion": "terminar"}, token=token), 200, "Terminar")
    ph.exigir(s.llamar("POST", f"/grabaciones/{gid}/finalizar", {"dispositivo": equipo}, token=token), 200, "Finalizar")
    return gid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    ap.add_argument("--clases", type=int, default=2, help="cuántas clases iguales se encolan a la vez (por defecto 2)")
    ap.add_argument("--espera-max-min", type=float, default=300, help="cuánto se espera a que terminen todas, en minutos")
    ap.add_argument("--salida", type=Path, help="guarda el detalle en un JSON")
    args = ap.parse_args()
    if not args.audio.is_file():
        print(f"No existe el archivo: {args.audio}")
        return 2
    minutos = duracion_min(args.audio)
    from nucleo import recursos

    print(f"Equipo de la medición: {len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else '?'} núcleos permitidos, la aplicación cree que son {os.cpu_count()} "
          f"y usará {recursos.hilos_de_procesamiento()} hilos. Audio: {minutos:.1f} min. Clases en cola: {args.clases}.", flush=True)
    carpeta = Path(tempfile.mkdtemp(prefix="medir_cola_"))
    s = ph.Servidor(carpeta)
    muestreo = Muestreador()
    resultados = []
    try:
        env = ph.entorno_del_servidor(carpeta)
        s.migrar(env)
        s.arrancar(env)
        token_utp, clases = preparar(s, args.clases)
        muestreo.start()
        gids, encoladas = [], []
        for token, bloque_id in clases:
            gids.append(grabar_en_trozos(s, token, bloque_id, args.audio))
            encoladas.append(time.monotonic())
        print(f"Las {args.clases} clases están en la cola. Midiendo (cada {SONDEO_S} s)…", flush=True)
        t0 = encoladas[0]
        estado = [{"inicio": None, "fin": None, "estado": None, "error": None, "posicion_vista": []} for _ in gids]
        limite = time.monotonic() + args.espera_max_min * 60
        while time.monotonic() < limite and any(e["fin"] is None for e in estado):
            for i, (gid, (token, _)) in enumerate(zip(gids, clases)):
                if estado[i]["fin"] is not None:
                    continue
                g = ph.exigir(s.llamar("GET", f"/grabaciones/{gid}", token=token), 200, "Consultar la grabación")
                ahora = time.monotonic()
                if g["estado"] == "procesando" and g.get("posicion_en_cola") is None and estado[i]["inicio"] is None:
                    estado[i]["inicio"] = ahora
                if g.get("posicion_en_cola") is not None and g["posicion_en_cola"] not in estado[i]["posicion_vista"]:
                    estado[i]["posicion_vista"].append(g["posicion_en_cola"])
                if g["estado"] in ("terminada", "error"):
                    estado[i].update(fin=ahora, estado=g["estado"], error=g.get("error"))
                    estado[i]["inicio"] = estado[i]["inicio"] or ahora
            time.sleep(SONDEO_S)
        muestreo.parar.set()
        for i, e in enumerate(estado):
            if e["fin"] is None:
                resultados.append({"clase": i + 1, "estado": "sin terminar", "audio_min": round(minutos, 1)})
                continue
            espera, proc = e["inicio"] - encoladas[i], e["fin"] - e["inicio"]
            r = {"clase": i + 1, "estado": e["estado"], "error": e["error"], "audio_min": round(minutos, 1), "espera_en_cola_min": round(espera / 60, 1),
                 "procesamiento_min": round(proc / 60, 1), "total_min": round((e["fin"] - encoladas[i]) / 60, 1), "procesa_por_cada_min_de_audio_min": round(proc / 60 / minutos, 2),
                 "posiciones_vistas_en_cola": e["posicion_vista"]}
            if i == 0:  # solo en la primera: en las demás el modelo puede seguir cargado de la anterior y no marcaría el comienzo del resumen
                m = muestreo.primer_modelo_cargado_desde(e["inicio"] - muestreo.t0)
                if m is not None:
                    r["transcripcion_min"], r["resumen_min"] = round((m - (e["inicio"] - muestreo.t0)) / 60, 1), round(((e["fin"] - muestreo.t0) - m) / 60, 1)
            resultados.append(r)
        print("\n--- RESULTADO ---")
        for r in resultados:
            print(json.dumps(r, ensure_ascii=False))
        print(f"Memoria: pico por proceso {({k: round(v, 2) for k, v in muestreo.pico.items()})} GB · pico total simultáneo {muestreo.pico_total:.2f} GB")
        sobrante = (carpeta / "audio").exists() and any((carpeta / "audio").iterdir())
        print("Audio sobrante en el disco:", "SÍ (debería haberse borrado)" if sobrante else "ninguno")
        if args.salida:
            args.salida.write_text(json.dumps({"resultados": resultados, "memoria_pico_gb": muestreo.pico, "memoria_pico_total_gb": muestreo.pico_total, "hilos": recursos.hilos_de_procesamiento()}, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(r.get("estado") == "terminada" for r in resultados) else 1
    finally:
        muestreo.parar.set()
        s.detener()
        shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
