# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Contadores de intentos fallidos en memoria, para frenar la adivinación de claves.

No guardan nada en disco: un reinicio los borra (lo que a un atacante no le sirve, porque el bloqueo de cada cuenta
real vive en la base de datos). Están acotados para que un atacante no pueda llenar la memoria del servidor.
"""
import datetime
import threading
import time
from collections import OrderedDict, deque


class LimitadorDeFallos:
    """Ventana deslizante: `maximo` fallos en `ventana_s` segundos bloquean a esa clave hasta que el más viejo caduque."""

    def __init__(self, maximo: int, ventana_s: float, max_claves: int = 10_000, reloj=time.monotonic):
        self.maximo, self.ventana_s, self.max_claves, self._reloj = maximo, ventana_s, max_claves, reloj
        self._fallos: OrderedDict[str, deque] = OrderedDict()
        self._candado = threading.Lock()

    def _podar(self, fallos: deque, ahora: float) -> None:
        while fallos and ahora - fallos[0] >= self.ventana_s:
            fallos.popleft()

    def segundos_de_espera(self, clave: str) -> int:
        """0 si puede intentar; si no, cuánto falta para que se libere."""
        with self._candado:
            fallos = self._fallos.get(clave)
            if not fallos:
                return 0
            ahora = self._reloj()
            self._podar(fallos, ahora)
            if len(fallos) < self.maximo:
                return 0
            return max(1, int(fallos[0] + self.ventana_s - ahora) + 1)

    def registrar(self, clave: str) -> None:
        with self._candado:
            ahora = self._reloj()
            fallos = self._fallos.setdefault(clave, deque())
            self._fallos.move_to_end(clave)
            self._podar(fallos, ahora)
            fallos.append(ahora)
            while len(self._fallos) > self.max_claves:
                self._fallos.popitem(last=False)

    def reiniciar(self) -> None:
        with self._candado:
            self._fallos.clear()


class FallosDeCuentasInexistentes:
    """Lleva la cuenta de intentos contra RUT que no existen (o que no sirven en esa pantalla) con el mismo bloqueo que
    una cuenta real. Sin esto, tras 5 fallos un RUT real respondía 429 y uno inexistente seguía respondiendo 401: la
    respuesta delataba quién está registrado."""

    def __init__(self, limite: int, calcular_bloqueo, max_claves: int = 10_000):
        self.limite, self._calcular, self.max_claves = limite, calcular_bloqueo, max_claves
        self._estado: OrderedDict[str, list] = OrderedDict()  # clave -> [intentos, bloqueado_hasta]
        self._candado = threading.Lock()

    def bloqueado_hasta(self, clave: str, ahora: datetime.datetime) -> datetime.datetime | None:
        with self._candado:
            estado = self._estado.get(clave)
            if estado and estado[1] and estado[1] > ahora:
                return estado[1]
            return None

    def registrar(self, clave: str, ahora: datetime.datetime) -> None:
        with self._candado:
            estado = self._estado.setdefault(clave, [0, None])
            self._estado.move_to_end(clave)
            estado[0] += 1
            if estado[0] >= self.limite:
                estado[1] = ahora + self._calcular(estado[0])
            while len(self._estado) > self.max_claves:
                self._estado.popitem(last=False)

    def reiniciar(self) -> None:
        with self._candado:
            self._estado.clear()
