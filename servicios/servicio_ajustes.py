# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Ajustes que el UTP decide en «Ajustes» y que antes solo se cambiaban con variables de entorno (la app se reparte portable: el
colegio no edita archivos). Cada uno vale lo que se guardó o, si no se guardó nada, su predeterminado (la variable de entorno de
siempre, o el valor del código): un colegio que ya existe no cambia de comportamiento hasta que el UTP toque algo.

- Por colegio (columnas de `Colegio`): horas para revisar el material antes de publicarlo como «provisorio» y minutos de gracia del corte
  automático de la grabación.
- Del servidor (tabla `ajustes_servidor`): carpeta y días del respaldo diario de la base, y el modelo que escribe los resúmenes. La base es una
  sola, así que valen para todos.
"""
import os
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from infraestructura.modelos_orm import AjusteServidor, Colegio
from nucleo import configuracion as app_config
from nucleo import modelos_ia
from servicios import servicio_respaldo

HORAS_REVISION_POR_DEFECTO = int(os.environ.get("HORAS_REVISION_PROFESOR", "24"))
MINUTOS_CORTE_POR_DEFECTO = int(os.environ.get("MINUTOS_CORTE_GRABACION", "15"))
DIAS_RESPALDO_POR_DEFECTO = int(os.environ.get("DIAS_DE_RESPALDO", servicio_respaldo.DIAS_POR_DEFECTO))

# Límites para que un error de tecleo no deje sin revisión al profesor (1 año), ni la grabación cortándose al instante o nunca.
RANGO_HORAS_REVISION = (1, 168)  # de una hora a una semana
RANGO_MINUTOS_CORTE = (0, 120)  # 0 = se corta justo al terminar el bloque
RANGO_DIAS_RESPALDO = (1, 365)

_CARPETA, _DIAS, _MODELO = "carpeta_respaldos", "dias_respaldo", "modelo_resumen"


class ErrorAjuste(Exception):
    """Un valor que no sirve, con el motivo en palabras de persona (se responde 422)."""

    def __init__(self, detalle: str, estado: int = 422):
        super().__init__(detalle)
        self.detalle, self.estado = detalle, estado


def horas_de_revision(colegio: Colegio) -> int:
    return colegio.horas_revision if colegio.horas_revision is not None else HORAS_REVISION_POR_DEFECTO


def minutos_de_corte(colegio: Colegio) -> int:
    return colegio.minutos_corte if colegio.minutos_corte is not None else MINUTOS_CORTE_POR_DEFECTO


def _en_rango(valor: int | None, rango: tuple[int, int], nombre: str, unidad: str) -> int | None:
    """None = volver al predeterminado. Si no, un entero dentro del rango (un bool no es un número aquí)."""
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or not rango[0] <= valor <= rango[1]:
        raise ErrorAjuste(f"{nombre}: escribe un número entero de {rango[0]} a {rango[1]} {unidad}.")
    return valor


def cambiar_ajustes_del_colegio(db: Session, colegio: Colegio, horas_revision: int | None, minutos_corte: int | None) -> None:
    """Valida los dos antes de guardar cualquiera: o se guardan los dos o ninguno."""
    horas = _en_rango(horas_revision, RANGO_HORAS_REVISION, "Plazo de revisión", "horas")
    minutos = _en_rango(minutos_corte, RANGO_MINUTOS_CORTE, "Corte automático", "minutos")
    colegio.horas_revision, colegio.minutos_corte = horas, minutos
    db.commit()


def _leer(db: Session, clave: str) -> str | None:
    fila = db.get(AjusteServidor, clave)
    return fila.valor if fila else None


def _poner(db: Session, clave: str, valor: str | None) -> None:
    fila = db.get(AjusteServidor, clave)
    if valor is None:
        if fila:
            db.delete(fila)
    elif fila:
        fila.valor = valor
    else:
        db.add(AjusteServidor(clave=clave, valor=valor))


def dias_de_respaldo(db: Session) -> int:
    try:
        return int(_leer(db, _DIAS) or DIAS_RESPALDO_POR_DEFECTO)
    except ValueError:  # un valor ilegible en la base nunca debe frenar el respaldo
        return DIAS_RESPALDO_POR_DEFECTO


def carpeta_de_respaldos(db: Session) -> Path:
    guardada = _leer(db, _CARPETA)
    return Path(guardada) if guardada else servicio_respaldo.carpeta_de_respaldos()


def validar_carpeta(texto: str) -> Path:
    """Una carpeta donde sí se puede escribir. Se crea si no existe (un solo nivel) y se prueba escribiendo un archivo que se borra al
    instante: es mejor enterarse ahora que cuando falle el respaldo de la noche."""
    texto = (texto or "").strip()
    if not texto or len(texto) > 300 or "\0" in texto:
        raise ErrorAjuste("Escribe la ruta completa de la carpeta de respaldos, por ejemplo D:\\Respaldos.")
    ruta = Path(texto)
    if not ruta.is_absolute():
        raise ErrorAjuste("Escribe la ruta completa de la carpeta (que parta por la letra del disco, como D:\\Respaldos, o por /).")
    if ruta.parent == ruta:
        raise ErrorAjuste("No uses la raíz del disco: elige o crea una carpeta dentro de él.")
    if ruta.exists() and not ruta.is_dir():
        raise ErrorAjuste("Esa ruta es un archivo, no una carpeta.")
    if not ruta.exists():
        if not ruta.parent.is_dir():
            raise ErrorAjuste("La carpeta que contendría a esa no existe. Créala primero o revisa que la letra del disco esté bien escrita.")
        try:
            ruta.mkdir()
        except OSError:
            raise ErrorAjuste("No se pudo crear esa carpeta. Revisa los permisos o elige otra.") from None
    try:
        with tempfile.NamedTemporaryFile(dir=ruta, prefix=".prueba-de-respaldo-"):
            pass
    except OSError:
        raise ErrorAjuste("No se puede guardar nada en esa carpeta. Elige otra o revisa los permisos.") from None
    return ruta


def cambiar_ajustes_de_respaldo(db: Session, carpeta: str | None, dias: int | None) -> None:
    """Valida todo antes de guardar. `carpeta` o `dias` en None = volver al predeterminado."""
    nueva = str(validar_carpeta(carpeta)) if carpeta is not None else None
    nuevos_dias = _en_rango(dias, RANGO_DIAS_RESPALDO, "Días de respaldo", "días")
    _poner(db, _CARPETA, nueva)
    _poner(db, _DIAS, str(nuevos_dias) if nuevos_dias is not None else None)
    db.commit()


def modelo_elegido(db: Session) -> str | None:
    """Lo que eligió el UTP, o None si no eligió (la aplicación decide sola)."""
    return _leer(db, _MODELO)


def modelo_de_resumen(db: Session) -> str:
    """Lo que se pide para el resumen: lo que eligió el UTP o, si no eligió, `ollama_model` de quien administra el servidor (`auto` por defecto)."""
    return modelo_elegido(db) or app_config.get_param("ollama_model")


def cambiar_modelo_de_resumen(db: Session, modelo: str, instalado: bool | None) -> None:
    """`modelo`: uno de los que la aplicación ofrece, o `auto` para que decida sola (borra la elección). `instalado`: lo que dice Ollama de ese
    modelo (None = no responde). Solo se elige uno que ya está descargado: elegir uno que falta dejaría sin resumen a todas las clases."""
    if modelo == "auto":
        _poner(db, _MODELO, None)
        db.commit()
        return
    if modelo not in {m for m, _, _ in modelos_ia.ELEGIBLES}:
        raise ErrorAjuste("Ese modelo no está entre los que la aplicación ofrece.")
    if instalado is None:
        raise ErrorAjuste("Ollama no responde, así que no se puede comprobar que ese modelo esté instalado. Ábrelo y vuelve a intentarlo.", 409)
    if not instalado:
        raise ErrorAjuste("Ese modelo todavía no está descargado en este equipo. Descárgalo primero y después úsalo.", 409)
    _poner(db, _MODELO, modelo)
    db.commit()
