"""Estado del servidor para el UTP: qué se está procesando, qué falló, y si el equipo está sano (disco, memoria, IA, respaldos).

El servidor del colegio corre 24/7 y casi nadie lo mira; este panel es la forma de enterarse a tiempo de que algo anda mal
(el disco se llena, el respaldo está en el mismo disco, Ollama se cerró) sin abrir una consola. Las alertas se escriben ya en
palabras de persona. No carga los modelos de IA ni PyTorch: solo lee estado.
"""
import datetime
import os
from pathlib import Path

from sqlalchemy.orm import Session

from infraestructura import basedatos
from infraestructura.modelos_orm import Bloque, Clase, Curso, EstadoGrabacion as E, Grabacion
from nucleo import configuracion as app_config
from nucleo.disco import ancestro_existente, espacio_en_disco
from nucleo.memoria import memoria_libre_gb, memoria_total_gb
from servicios import servicio_grabacion as sg
from servicios import servicio_modelos, servicio_pizarra, servicio_respaldo

DISCO_AVISO_GB = 5.0
DISCO_CRITICO_GB = sg.DISCO_MINIMO_PARA_GRABAR_GB  # con menos no se puede empezar a grabar: el aviso y el bloqueo hablan del mismo número
MEMORIA_AVISO_GB = 1.5
RESPALDO_ATRASADO_DIAS = 2
AUDIO_SOBRANTE_MB = 1500
SIN_PULSO_S = 60  # la vigilancia pasa cada 10 s (más lo que tarde el respaldo del día)
MODELOS_AUTO = ("llama3.2:1b", "llama3.2:3b")  # los que elige la app con `ollama_model: auto` (sin importar PyTorch en el servidor)


def _mb(ruta: Path) -> float:
    if ruta.is_file():
        return round(ruta.stat().st_size / 1e6, 1)
    total = sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file()) if ruta.is_dir() else 0
    return round(total / 1e6, 1)


def _misma_unidad(a: Path, b: Path) -> bool | None:
    """¿Las dos rutas están en el mismo disco? None si no se puede saber. (Un respaldo en el disco de la base no sirve si el disco falla.)"""
    x, y = ancestro_existente(a), ancestro_existente(b)
    if x is None or y is None:
        return None
    return os.stat(x).st_dev == os.stat(y).st_dev


def _procesamiento(db: Session, colegio_id: int) -> dict:
    filas = (
        db.query(Grabacion)
        .join(Clase, Clase.id == Grabacion.clase_id).join(Bloque, Bloque.id == Clase.bloque_id).join(Curso, Curso.id == Bloque.curso_id)
        .filter(Curso.colegio_id == colegio_id, Grabacion.estado.in_([E.ESPERANDO, E.GRABANDO, E.PAUSADA, E.TERMINANDO, E.PROCESANDO, E.ERROR]))
        .all()
    )

    def base(g: Grabacion) -> dict:
        b = g.clase.bloque
        return {"clase_id": g.clase_id, "asignatura": b.asignatura, "curso": b.curso.nombre, "fecha": g.clase.fecha}

    ahora = sg.ahora_utc()
    turnos = {x.id: n for n, x in enumerate(sg.cola(db), start=1)}  # el orden real en que se van a procesar
    en_vivo, procesando, con_reintento, con_error = [], [], [], []
    for g in filas:
        if g.estado in sg.ACTIVAS:
            en_vivo.append({**base(g), "estado": g.estado.value})
        elif g.estado == E.PROCESANDO:
            prioritaria = g.clase.prioritaria
            if g.iniciada_en is not None:  # ya la tomó un trabajador
                minutos = max(0, int((ahora - g.iniciada_en).total_seconds() // 60))
                procesando.append({**base(g), "turno": "ahora", "minutos": minutos, "posicion": None, "prioritaria": prioritaria})
            else:
                procesando.append({**base(g), "turno": "espera", "minutos": None, "posicion": turnos.get(g.id), "prioritaria": prioritaria})
        elif g.reintento_en is not None:
            con_reintento.append({**base(g), "intentos": g.intentos + 1, "reintento_en": g.reintento_en.replace(tzinfo=datetime.timezone.utc), "error": g.error})
        else:
            con_error.append({**base(g), "error": g.error})
    desde = ahora - datetime.timedelta(hours=24)
    terminadas = (
        db.query(Grabacion).join(Clase, Clase.id == Grabacion.clase_id).join(Bloque, Bloque.id == Clase.bloque_id).join(Curso, Curso.id == Bloque.curso_id)
        .filter(Curso.colegio_id == colegio_id, Grabacion.estado == E.TERMINADA, Grabacion.creada_en >= desde).count()
    )
    procesando.sort(key=lambda c: (c["posicion"] is not None, c["posicion"] or 0))  # primero las que ya están en marcha, luego la cola en orden
    return {"en_vivo": en_vivo, "procesando": procesando, "con_reintento": con_reintento, "con_error": con_error, "terminadas_24h": terminadas}


def _ollama() -> dict:
    url = servicio_pizarra.url_ollama()
    nombres = servicio_modelos.modelos_instalados(url)
    configurado = app_config.get_param("ollama_model")
    posibles = list(MODELOS_AUTO) if configurado == "auto" else [configurado]
    return {
        "responde": nombres is not None,
        "modelo_texto": " o ".join(posibles),
        "modelo_texto_instalado": nombres is not None and any(servicio_modelos.esta_en(m, nombres) for m in posibles),
    }


def _disco() -> dict:
    libre, total = espacio_en_disco(sg.CARPETA_AUDIO)  # el disco donde se escribe el audio (el mismo que mira el bloqueo de grabar)
    base = Path(basedatos.engine.url.database) if basedatos.engine.url.get_backend_name() == "sqlite" and basedatos.engine.url.database else None
    return {
        "libre_gb": round(libre, 1), "total_gb": round(total, 1),
        "audio_temporal_mb": _mb(sg.CARPETA_AUDIO), "fotos_temporales_mb": _mb(servicio_pizarra.CARPETA_FOTOS),
        "base_de_datos_mb": _mb(base) if base else None,
    }


def _respaldos() -> dict:
    carpeta = servicio_respaldo.carpeta_de_respaldos()
    datos = servicio_respaldo.estado(carpeta)
    base = Path(basedatos.engine.url.database) if basedatos.engine.url.get_backend_name() == "sqlite" and basedatos.engine.url.database else None
    hoy = datetime.date.today()
    return {
        "carpeta": str(carpeta.resolve()), "cantidad": datos["cantidad"], "mb": datos["mb"], "ultimo": datos["ultimo"],
        "hace_dias": (hoy - datos["ultimo"]).days if datos["ultimo"] else None,
        "en_el_mismo_disco": _misma_unidad(carpeta, base) if base else None,
    }


def construir_alertas(e: dict) -> list[dict]:
    """De los datos al aviso en palabras de persona. `critico` pide actuar hoy; `aviso`, pronto."""
    a: list[dict] = []

    def alerta(tema: str, nivel: str, texto: str):
        a.append({"tema": tema, "nivel": nivel, "texto": texto})

    d, r, o, m, p, v = e["disco"], e["respaldos"], e["ollama"], e["memoria"], e["procesamiento"], e["vigilancia"]
    if d["libre_gb"] < DISCO_CRITICO_GB:
        alerta("disco", "critico", f"Quedan solo {d['libre_gb']} GB libres en el disco: no se pueden empezar clases nuevas y el procesamiento y los respaldos pueden fallar. Libera espacio ya.")
    elif d["libre_gb"] < DISCO_AVISO_GB:
        alerta("disco", "aviso", f"Quedan {d['libre_gb']} GB libres en el disco. Conviene liberar espacio pronto.")
    if d["audio_temporal_mb"] > AUDIO_SOBRANTE_MB and not (p["procesando"] or p["en_vivo"] or p["con_reintento"]):
        alerta("disco", "aviso", f"Hay {round(d['audio_temporal_mb'] / 1000, 1)} GB de audio guardado sin ninguna clase que lo necesite: debería haberse borrado.")
    if not o["responde"]:
        alerta("ollama", "aviso", "El programa de IA (Ollama) no responde: las clases no se pueden resumir por ahora (quedan con error y se reintentan solas cuando vuelva).")
    elif not o["modelo_texto_instalado"]:
        alerta("ollama", "critico", f"Falta el modelo que escribe los resúmenes ({o['modelo_texto']}): sin él ninguna clase se puede resumir.")
    if r["cantidad"] == 0:
        alerta("respaldos", "aviso", "Todavía no hay ningún respaldo de la base de datos. Se hace uno al día; si lo ves después de un día de uso, algo falla.")
    elif r["hace_dias"] is not None and r["hace_dias"] > RESPALDO_ATRASADO_DIAS:
        alerta("respaldos", "critico", f"El último respaldo es de hace {r['hace_dias']} días: el respaldo diario no se está haciendo.")
    if r["en_el_mismo_disco"]:
        alerta("respaldos", "aviso", "Los respaldos están en el mismo disco que la base de datos: si el disco falla se pierde todo. Conviene guardarlos en otro disco o en una unidad externa.")
    if m["libre_gb"] is not None and m["libre_gb"] < MEMORIA_AVISO_GB:
        alerta("memoria", "aviso", f"Queda poca memoria libre ({m['libre_gb']} GB): el procesamiento de clases puede esperar o cortarse.")
    if v["activa"] is False:
        alerta("vigilancia", "critico", "La vigilancia automática no responde: las grabaciones olvidadas no se cortan solas y los reintentos no se lanzan. Reinicia el servidor.")
    if p["con_error"]:
        n = len(p["con_error"])
        alerta("clases", "critico", f"{n} {'clase' if n == 1 else 'clases'} con error sin reintento pendiente: hay que grabarla de nuevo o revisarla.")
    a.sort(key=lambda x: x["nivel"] != "critico")  # lo urgente primero (el orden es estable: dentro de cada nivel queda el de arriba)
    return a


def estado_del_servidor(db: Session, colegio_id: int, vigilando: bool = True) -> dict:
    """`vigilando`: si la vigilancia automática está encendida en este servidor (en las pruebas no lo está, y no hay latido que exigir)."""
    ahora = sg.ahora_utc()
    ultimo = sg.ultima_vigilancia
    total, libre = memoria_total_gb(), memoria_libre_gb()
    e = {
        "generado_en": ahora.replace(tzinfo=datetime.timezone.utc),
        "procesamiento": _procesamiento(db, colegio_id),
        "ollama": _ollama(),
        "disco": _disco(),
        "respaldos": _respaldos(),
        "memoria": {"total_gb": round(total, 1) if total else None, "libre_gb": round(libre, 1) if libre is not None else None},
        "vigilancia": {
            "ultima_pasada": ultimo.replace(tzinfo=datetime.timezone.utc) if ultimo else None,
            "activa": (ahora - (ultimo or sg.ARRANQUE)).total_seconds() < SIN_PULSO_S if vigilando else None,
        },
    }
    e["alertas"] = construir_alertas(e)
    return e
