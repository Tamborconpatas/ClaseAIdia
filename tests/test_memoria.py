"""Medir y esperar memoria sin librerías extra."""
import sys

import pytest

from nucleo import memoria

MEMINFO = """MemTotal:       16384000 kB
MemFree:          500000 kB
MemAvailable:    8192000 kB
Buffers:          100000 kB
"""


def test_se_lee_la_memoria_disponible_y_no_solo_la_libre_de_proc_meminfo():
    total, libre = memoria._leer_meminfo(MEMINFO)
    assert total == pytest.approx(16384000 * 1024 / memoria.GB)
    assert libre == pytest.approx(8192000 * 1024 / memoria.GB)  # MemAvailable, no MemFree: la caché se puede soltar


def test_un_meminfo_sin_los_datos_no_inventa_nada():
    assert memoria._leer_meminfo("Buffers: 100 kB\n") is None
    assert memoria._leer_meminfo("") is None


@pytest.mark.skipif(sys.platform not in ("win32", "linux"), reason="solo se mide en Windows y Linux")
def test_en_este_equipo_las_medidas_tienen_sentido():
    total, libre, mia = memoria.memoria_total_gb(), memoria.memoria_libre_gb(), memoria.memoria_del_proceso_gb()
    assert total > 1 and 0 < libre <= total
    assert 0.01 < mia < total  # un proceso de pruebas con numpy y fastapi cargados usa algo, y menos que el equipo


@pytest.mark.skipif(sys.platform not in ("win32", "linux"), reason="solo se mide en Windows y Linux")
def test_la_memoria_del_proceso_sube_cuando_el_proceso_pide_memoria():
    import numpy as np

    antes = memoria.memoria_del_proceso_gb()
    bloque = np.ones(150 * 1024 * 1024 // 8)  # 150 MB realmente usados
    despues = memoria.memoria_del_proceso_gb()
    assert despues - antes > 0.1
    del bloque


def test_si_hay_memoria_no_se_espera():
    dormidos = []
    assert memoria.esperar_memoria(2.0, 60, libre=lambda: 5.0, dormir=dormidos.append) is True
    assert dormidos == []


def test_si_no_hay_se_espera_y_se_sigue_cuando_aparece():
    lecturas = iter([1.0, 1.2, 3.0])
    dormidos = []
    assert memoria.esperar_memoria(2.0, 60, intervalo_s=10, libre=lambda: next(lecturas), dormir=dormidos.append) is True
    assert dormidos == [10, 10]


def test_si_se_acaba_la_espera_sin_memoria_dice_que_no():
    dormidos = []
    assert memoria.esperar_memoria(2.0, 30, intervalo_s=10, libre=lambda: 0.5, dormir=dormidos.append) is False
    assert dormidos == [10, 10, 10]  # esperó los 30 s y no más


def test_si_no_se_puede_medir_no_se_bloquea_a_nadie():
    assert memoria.esperar_memoria(2.0, 60, libre=lambda: None, dormir=lambda s: pytest.fail("no debía esperar")) is True


def test_tener_justo_el_minimo_alcanza():
    assert memoria.esperar_memoria(2.0, 60, libre=lambda: 2.0, dormir=lambda s: pytest.fail("no debía esperar")) is True
