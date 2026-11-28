# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Recorre la aplicación en un navegador de verdad (Chromium, con ventana) y comprueba lo que hace cada rol.

Levanta su propio servidor y su propio frontend sobre una base de demostración nueva en una carpeta temporal
(nunca toca escuela.db), así que se puede correr en cualquier momento:

    pip install -r requirements-e2e.txt && playwright install chromium     (una sola vez)
    python -m scripts.e2e_navegador                  # con ventana, para ir viéndolo
    python -m scripts.e2e_navegador --sin-ventana    # sin ventana (p. ej. para automatizarlo)
    python -m scripts.e2e_navegador --movil          # emula un teléfono (Pixel 7)
    python -m scripts.e2e_navegador --telefono       # en un teléfono Android real conectado por USB

--telefono necesita `adb` (en Arch: pacman -S android-tools), la «Depuración USB» activada en el teléfono (con el aviso
aceptado), la pantalla desbloqueada y un navegador basado en Chromium instalado en él (por defecto Brave; --paquete para
otro, p. ej. com.android.chrome). El teléfono abre `localhost` (adb reverse lo lleva al servidor de prueba, así que no hace
falta red del colegio ni certificado y el micrófono real funciona). Corre los recorridos de alumno, profesor, UTP-estado y
«Grabar» (con el micrófono de verdad); cuando un recorrido pide un segundo equipo a la vez, usa el Chromium del computador.

Cada paso aparece en un cartel dentro de la página. Sale con código 1 si algo falla y deja capturas en e2e_capturas/.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.consola import salida_segura  # noqa: E402

salida_segura()

from nucleo.validadores import validar_rut  # noqa: E402

PUERTO_API, PUERTO_WEB = 8100, 5273  # distintos de los de uso normal (8000 y 5173) para no pisarlos
BASE = f"http://127.0.0.1:{PUERTO_WEB}"
PAUSA_MS = 250  # lo justo para alcanzar a leer el cartel de cada paso
CLAVE = "demo-clave-2026"
PIN = "482915"
CAPTURAS = RAIZ / "e2e_capturas"
FALLOS: list[str] = []
DISPOSITIVO: dict | None = None  # perfil de teléfono de Playwright; None = pantalla de PC
TELEFONO = False  # un teléfono Android real por USB (--telefono)
ETIQUETA = ""


def rut(numero: int) -> str:
    return next(f"{numero}-{dv}" for dv in "0123456789K" if validar_rut(f"{numero}-{dv}"))


def paso(pg, texto: str) -> None:
    """Cartel con lo que se está haciendo, visible en la propia página."""
    pg.evaluate(
        """t => {
            let d = document.getElementById('e2e-paso');
            if (!d) {
                d = document.createElement('div'); d.id = 'e2e-paso';
                d.style.cssText = 'position:fixed;left:50%;bottom:12px;transform:translateX(-50%);z-index:99999;background:#111;color:#fff;padding:8px 16px;border-radius:999px;font:600 14px system-ui;pointer-events:none;box-shadow:0 2px 12px #0008;max-width:90vw;text-align:center';
                document.body.appendChild(d);
            }
            d.textContent = t;
        }""",
        texto,
    )
    print(f"   · {texto}")
    pg.wait_for_timeout(PAUSA_MS)


def comprobar(nombre: str, ok: bool, detalle: str = "") -> None:
    nombre = f"[{ETIQUETA}] {nombre}" if ETIQUETA else nombre
    print(f"  {'OK   ' if ok else 'FALLA'} {nombre}" + (f"  ->  {detalle}" if not ok and detalle else ""))
    if not ok:
        FALLOS.append(nombre)


def ir(pg, seccion: str):
    """Entra a una sección del menú: barra lateral en PC, barra inferior en teléfono (solo cuenta lo visible)."""
    return pg.get_by_role("link", name=seccion).or_(pg.get_by_role("button", name=seccion)).filter(visible=True).first


def errores_visibles(pg) -> str:
    return " | ".join(t.strip() for t in pg.locator("[role=alert], .text-destructive").all_inner_texts() if t.strip())


def esperar(url: str, segundos: int = 90) -> None:
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            urllib.request.urlopen(url, timeout=2).close()
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"No respondió a tiempo: {url}")


# ---------- acciones comunes ----------------------------------------------------------------------------------------


def bajar_teclado(pg) -> None:
    """En un teléfono, con el teclado en pantalla abierto Playwright calcula mal dónde está el botón y el clic cae en otro
    campo; quien usa el teléfono baja el teclado (o toca lo que ve). En PC no hace nada."""
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    pg.wait_for_timeout(300)


def entrar_alumno(pg, rut_alumno: str) -> None:
    pg.goto(BASE + "/")
    pg.get_by_label("RUT").fill(rut_alumno)
    pg.get_by_label("PIN").fill(PIN)
    bajar_teclado(pg)
    pg.get_by_role("button", name="Entrar").click()
    pg.get_by_text("Alumno ·").filter(visible=True).first.wait_for(timeout=10000)  # «Hola,» solo existe en PC


def entrar_staff(pg, rut_staff: str) -> None:
    pg.goto(BASE + "/")
    pg.get_by_role("tab", name="Profesor o UTP").click()
    pg.get_by_label("RUT").fill(rut_staff)
    pg.get_by_label("Contraseña").fill(CLAVE)
    bajar_teclado(pg)
    pg.get_by_role("button", name="Entrar").click()
    ir(pg, "Cursos").wait_for(timeout=10000)


def abrir_alumnos(pg, curso: str):
    ir(pg, "Cursos").click()
    pg.locator("li").filter(has=pg.get_by_text(curso, exact=True)).first.get_by_role("button", name="Alumnos").click()
    lista = pg.get_by_label("Alumnos del curso")
    lista.wait_for(timeout=8000)
    pg.wait_for_timeout(400)
    return lista.locator("> li")


def llenar_unirse(pg, nombre: str, rut_alumno: str) -> None:
    pg.get_by_label("Tu nombre").fill(nombre)
    pg.get_by_label("RUT").fill(rut_alumno)
    pg.get_by_label("Elige un PIN").fill(PIN)
    pg.get_by_label("Repite el PIN").fill(PIN)
    bajar_teclado(pg)


def unirse(pg, codigo: str, nombre: str, rut_alumno: str) -> None:
    pg.goto(f"{BASE}/?unirse={codigo}")
    pg.get_by_label("Tu nombre").wait_for()
    llenar_unirse(pg, nombre, rut_alumno)
    pg.get_by_role("button", name="Unirme y entrar").click()


# ---------- recorridos ----------------------------------------------------------------------------------------------


def alumno_se_inscribe(navegador, vista: str, ancho: int, alto: int, nombre: str, rut_alumno: str) -> None:
    vista = ETIQUETA or vista
    print(f"\n[1] Alumno se inscribe ({vista})")
    ctx = navegador.new_context(viewport={"width": ancho, "height": alto})
    pg = ctx.new_page()
    pg.goto(f"{BASE}/?unirse=DEMO8A")
    pg.get_by_label("Tu nombre").wait_for()

    paso(pg, "RUT con dígito verificador válido pero falso")
    llenar_unirse(pg, "Juan Soto", "11.111.111-1")
    pg.get_by_role("button", name="Unirme y entrar").click()
    pg.wait_for_timeout(600)
    comprobar("rechaza un RUT falso", "no parece el de un alumno real" in errores_visibles(pg), errores_visibles(pg))

    paso(pg, "Nombre con grosería")
    llenar_unirse(pg, "Juan Weon", rut(22400900))
    pg.get_by_role("button", name="Unirme y entrar").click()
    pg.wait_for_timeout(600)
    comprobar("rechaza un nombre vetado", "no es válido" in errores_visibles(pg), errores_visibles(pg))

    paso(pg, f"Nombre con doble sentido: «{nombre}»")
    llenar_unirse(pg, nombre, rut_alumno)
    pg.get_by_role("button", name="Unirme y entrar").click()
    aviso = pg.get_by_role("alert").filter(has_text="quedará asociado")
    aviso.wait_for(timeout=5000)
    comprobar("pide confirmar el nombre con el RUT a la vista", rut_alumno[:2] + "." in aviso.inner_text(), aviso.inner_text())
    alto_boton = pg.get_by_role("button", name="Sí, es mi nombre real").bounding_box()["height"]
    en_celular = ancho < 600 or DISPOSITIVO is not None or TELEFONO
    comprobar("botón de confirmar con tamaño táctil en celular" if en_celular else "botón de confirmar visible", alto_boton >= (44 if en_celular else 32), f"{alto_boton}px")

    paso(pg, "Confirma que es su nombre real")
    pg.get_by_role("button", name="Sí, es mi nombre real").click()
    pg.get_by_text("Alumno ·").filter(visible=True).first.wait_for(timeout=10000)  # el saludo «Hola,» solo existe en la vista de PC
    comprobar("entra a su horario tras confirmar", True)
    ctx.close()


def un_rut_un_curso(navegador) -> None:
    print("\n[2] Un RUT, un solo curso")
    ctx = navegador.new_context(viewport={"width": 1100, "height": 800})
    pg = ctx.new_page()
    paso(pg, "Sofía (8°A) intenta unirse a 8°B con el código de ese curso")
    unirse(pg, "DEMO8B", "Sofía Contreras", "21000001-1")
    pg.wait_for_timeout(800)
    comprobar("no se puede estar en dos cursos", "ya está en el curso 8°A" in errores_visibles(pg), errores_visibles(pg))
    ctx.close()


def una_sesion(navegador) -> None:
    print("\n[3] Una sola sesión por alumno")
    a = navegador.new_context(viewport={"width": 1000, "height": 700}).new_page()
    b = navegador.new_context(viewport={"width": 1000, "height": 700}).new_page()
    paso(a, "Matías entra en el equipo A")
    entrar_alumno(a, "21000002-K")
    paso(b, "Matías entra en el equipo B")
    entrar_alumno(b, "21000002-K")
    paso(a, "El equipo A intenta seguir usando la app")
    ir(a, "Clases").click()
    a.get_by_role("heading", name="Entrar").wait_for(timeout=8000)
    comprobar("el equipo anterior queda cerrado", True)
    comprobar("el equipo nuevo sigue dentro", b.get_by_text("Alumno ·").filter(visible=True).first.is_visible())
    a.context.close()
    b.context.close()


def estado_dispositivos(navegador) -> None:
    print("\n[3b] Panel de estado: quién está conectado y desde qué equipo (sin IP)")
    esperado = "Teléfono · Android · Chrome" if (DISPOSITIVO or TELEFONO) else "Computador · Linux · Chrome"
    pg = navegador.new_context(viewport={"width": 1280, "height": 1000}).new_page()
    paso(pg, "El UTP abre «Estado»")
    entrar_staff(pg, "11111111-1")
    ir(pg, "Estado").click()
    pg.get_by_role("heading", name="Conectados ahora").wait_for(timeout=10000)
    conectados = pg.get_by_label("Personas conectadas").inner_text()
    comprobar("aparecen los alumnos que acaban de inscribirse", "Alan Brito" in conectados and "Armando Casas" in conectados, conectados[:120])
    comprobar("con el tipo de equipo desde el que entraron", esperado in conectados, conectados[:160])
    paso(pg, "Nombres por revisar: de dónde salió cada cuenta")
    revisar = pg.get_by_label("Cuentas con un nombre por revisar").inner_text()
    comprobar("los dos nombres marcados dicen desde qué equipo se crearon", revisar.count(f"Se registró desde: {esperado}") == 2, revisar[:200])
    cuerpo = pg.locator("body").inner_text()
    comprobar("no se muestra ninguna dirección IP", re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", cuerpo) is None)
    comprobar("el aviso dice que no se guarda IP ni teléfono", "no la dirección IP ni el número de teléfono" in cuerpo)
    pg.context.close()


def descargar_pdf(navegador) -> None:
    print("\n[4b] «Guardar como PDF» descarga el archivo directo (no abre la impresión)")
    pg = navegador.new_context(viewport={"width": 1280, "height": 800}).new_page()
    entrar_alumno(pg, "21000001-1")
    paso(pg, "Abre una clase con material")
    ir(pg, "Clases").click()
    pg.get_by_text("Matemática").filter(visible=True).first.click()
    pg.get_by_role("button", name="Guardar como PDF").filter(visible=True).first.wait_for(timeout=10000)
    pg.evaluate("() => { window.print = () => { window.__imprimio = true } }")  # si abriera la impresión, lo sabríamos (con la función envuelta: Playwright ejecuta una expresión que devuelve una función)
    boton = pg.get_by_role("button", name="Guardar como PDF").filter(visible=True).first
    paso(pg, "Toca «Guardar como PDF»")
    if TELEFONO:  # por CDP no se ve la descarga en el teléfono: se comprueba el aviso (el archivo se mira a mano en Descargas)
        boton.click()
        pg.get_by_text("Listo: se descargó").first.wait_for(state="attached", timeout=90000)
        comprobar("el teléfono avisa que descargó el PDF", True)
    else:
        with pg.expect_download(timeout=60000) as d:
            boton.click()
        ruta = d.value.path()
        comprobar("descarga un archivo .pdf", d.value.suggested_filename.endswith(".pdf"), d.value.suggested_filename)
        contenido = Path(ruta).read_bytes()
        comprobar("y es un PDF de verdad, con páginas y contenido", contenido.startswith(b"%PDF-") and len(re.findall(rb"/Type /Page(?!s)", contenido)) >= 1 and len(contenido) > 4000, f"{len(contenido)} bytes")
    comprobar("no abrió la impresión del navegador", not pg.evaluate("!!window.__imprimio"))
    pg.context.close()


def clase_doble(navegador) -> None:
    print("\n[4] Clase doble (dos bloques seguidos = una clase)")
    pg = navegador.new_context(viewport={"width": 1280, "height": 800}).new_page()
    entrar_alumno(pg, "21000001-1")
    for indice, hora in ((0, "08:00"), (1, "08:45")):
        paso(pg, f"Abre la Matemática del lunes de las {hora}")
        ir(pg, "Horario").click()
        if pg.viewport_size["width"] < 700:  # teléfono: el horario es por día, hoy es jueves
            pg.get_by_role("tab", name="Lun", exact=True).click()
        pg.locator("button", has_text="Matemática").filter(visible=True).nth(indice).click()
        pg.wait_for_timeout(1200)
        texto = pg.locator("main").inner_text()
        comprobar(f"el bloque de las {hora} abre la clase completa", "08:00–09:30" in texto and "Resumen" in texto, texto[:80].replace("\n", " "))
    pg.context.close()


def profesor(navegador) -> None:
    print("\n[5] Profesor revisa los nombres marcados")
    pg = navegador.new_context(viewport={"width": 1280, "height": 900}).new_page()
    paso(pg, "Entra el profesor y abre los alumnos de 8°A")
    entrar_staff(pg, "12345678-5")
    filas = abrir_alumnos(pg, "8°A")
    marcas = pg.get_by_text("Revisar nombre").count()
    comprobar("ve los dos nombres marcados", marcas == 2, f"{marcas} marcas")
    fila = filas.filter(has_text="Alan Brito").first
    comprobar("puede corregir y dar por bueno", fila.get_by_role("button", name="Corregir el nombre").is_visible() and fila.get_by_role("button", name="está bien").is_visible())
    comprobar("no puede mover, sacar ni eliminar", pg.get_by_role("button", name="Mover de curso").count() == 0 and pg.get_by_role("button", name="Eliminar al alumno").count() == 0)
    paso(pg, "Da por bueno el nombre de Alan Brito")
    fila.get_by_role("button", name="está bien").click()
    pg.wait_for_timeout(700)
    comprobar("la marca desaparece y se anuncia", pg.get_by_text("Revisar nombre").count() == 1 and "quedó como correcto" in pg.locator("[role=status]").first.inner_text())
    pg.context.close()


def utp(navegador) -> None:
    print("\n[8] UTP: máximo por curso, corregir, mover, sacar y eliminar")
    pg = navegador.new_context(viewport={"width": 1280, "height": 1000}).new_page()
    paso(pg, "Entra el UTP y abre los alumnos de 8°A")
    entrar_staff(pg, "11111111-1")
    filas = abrir_alumnos(pg, "8°A")
    cupo = pg.locator("input[type=number]")
    n = filas.count()
    comprobar("muestra el máximo editable (45 por defecto)", cupo.input_value() == "45", cupo.input_value())

    paso(pg, f"Intenta bajar el máximo a {n - 1} con {n} alumnos")
    cupo.fill(str(n - 1))
    pg.get_by_role("button", name="Guardar").click()
    pg.wait_for_timeout(600)
    comprobar("no deja bajar el máximo de los inscritos", "ya tiene" in errores_visibles(pg), errores_visibles(pg))
    paso(pg, "Máximo 0: fuera de rango")
    cupo.fill("0")
    comprobar("bloquea valores fuera de rango", pg.get_by_role("button", name="Guardar").is_disabled())

    paso(pg, f"Fija el máximo en {n}: el curso queda lleno")
    cupo.fill(str(n))
    pg.get_by_role("button", name="Guardar").click()
    pg.wait_for_timeout(700)
    comprobar("guarda el máximo", f"quedó en {n}" in pg.locator("[role=status]").first.inner_text())
    ctx = navegador.new_context(viewport={"width": 390, "height": 844})
    al = ctx.new_page()
    paso(al, "Un alumno nuevo intenta unirse al curso lleno")
    unirse(al, "DEMO8A", "Pedro Pérez", rut(22500001))
    al.wait_for_timeout(800)
    comprobar("el curso lleno rechaza al alumno", "está lleno" in errores_visibles(al), errores_visibles(al))
    ctx.close()
    cupo.fill("45")
    pg.get_by_role("button", name="Guardar").click()
    pg.wait_for_timeout(600)

    paso(pg, "Corrige el nombre de Armando Casas")
    filas.filter(has_text="Armando Casas").first.get_by_role("button", name="Corregir el nombre").click()
    pg.get_by_label("Nuevo nombre de Armando Casas").fill("Armando Cáceres")
    pg.get_by_role("button", name="Guardar el nombre").click()
    pg.wait_for_timeout(700)
    comprobar("corregir el nombre quita la marca", "Armando Cáceres" in pg.get_by_label("Alumnos del curso").inner_text() and pg.get_by_text("Revisar nombre").count() == 0)

    paso(pg, "Mueve a Alan Brito a 8°B")
    filas.filter(has_text=rut(22400001)).first.get_by_role("button", name="Mover de curso").click()
    pg.get_by_label("Curso de destino de Alan Brito").select_option(label="8°B")
    pg.get_by_role("button", name="Mover", exact=True).click()
    pg.wait_for_timeout(700)
    comprobar("el alumno sale de 8°A", filas.count() == n - 1, f"{filas.count()} filas")
    filas_b = abrir_alumnos(pg, "8°B")
    comprobar("y aparece en 8°B", filas_b.filter(has_text="Alan Brito").count() == 1)

    filas = abrir_alumnos(pg, "8°A")
    paso(pg, "Saca a Matías del curso")
    filas.filter(has_text="Matías").first.get_by_role("button", name="Sacar del curso").click()
    pg.get_by_role("button", name="Sí, sacarlo").click()
    pg.wait_for_timeout(700)
    comprobar("sacar del curso", filas.count() == n - 2, f"{filas.count()} filas")
    paso(pg, "Elimina la cuenta de Sofía")
    filas.filter(has_text="Sofía").first.get_by_role("button", name="Eliminar al alumno").click()
    pg.get_by_role("button", name="Sí, eliminar").click()
    pg.wait_for_timeout(700)
    comprobar("eliminar la cuenta", filas.count() == n - 3, f"{filas.count()} filas")
    pg.context.close()


def ajustes_modelo_texto(navegador) -> None:
    print("\n[8b] UTP: «Ajustes» muestra el modelo que escribe los resúmenes y se baja desde la app (sin consola)")
    pg = navegador.new_context(viewport={"width": 1280, "height": 1000}).new_page()
    paso(pg, "Entra el UTP y abre «Ajustes»")
    entrar_staff(pg, "11111111-1")
    ir(pg, "Ajustes").click()
    seccion = pg.locator("section[aria-labelledby=titulo-resumenes]")
    seccion.wait_for()
    pg.wait_for_timeout(800)
    paso(pg, "Ve si el modelo de resúmenes está instalado en este equipo, y cuánto pesa si falta")
    texto = seccion.inner_text()
    comprobar("dice si el modelo de resúmenes está instalado o cuánto pesa bajarlo", "Instalado." in texto or "Falta descargarlo" in texto, texto[:140])
    comprobar("no manda a una consola ni a editar archivos", not re.search(r"ollama pull|consola|\.env", texto, re.I), texto[:140])
    if "Falta descargarlo" in texto:
        comprobar("ofrece el botón para bajarlo", pg.get_by_role("button", name="Descargar el modelo de resúmenes").is_visible())
    paso(pg, "Revisa la accesibilidad de la pantalla")
    axe(pg, "Ajustes con el modelo de resúmenes")


def llamar(metodo: str, ruta: str, cuerpo=None, token: str | None = None):
    """Llamada directa a la API (para preparar datos que la pantalla no crea sola)."""
    cabeceras = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    peticion = urllib.request.Request(f"{BASE}/api{ruta}", method=metodo, headers=cabeceras, data=None if cuerpo is None else json.dumps(cuerpo).encode())
    with urllib.request.urlopen(peticion, timeout=15) as r:
        datos = r.read()
        return json.loads(datos) if datos else None


def grabar_clase_doble(navegador) -> None:
    print(f"\n[6] «Grabar» con una clase doble (micrófono {'REAL del teléfono' if TELEFONO else 'simulado'})")
    token_utp = llamar("POST", "/auth/login/staff", {"rut": "11111111-1", "password": CLAVE})["access_token"]
    colegio = llamar("GET", "/auth/me", token=token_utp)["colegio_id"]
    rut_profesora = rut(9100001)
    profesora = llamar("POST", "/usuarios", {"rut": rut_profesora, "nombre": "Lucía Prueba", "colegio_id": colegio, "roles": ["PROFESOR"], "password": CLAVE}, token_utp)
    curso = llamar("POST", "/cursos", {"nombre": "9°A", "colegio_id": colegio}, token_utp)
    hoy = datetime.date.today().weekday()
    bloques = [
        llamar("POST", f"/cursos/{curso['id']}/bloques", {"tipo": "CLASE", "asignatura": "Matemática", "profesor_id": profesora["id"], "sala": "S9", "dia_semana": hoy, "hora_inicio": ini, "hora_fin": fin}, token_utp)["id"]
        for ini, fin in (("00:00", "12:00"), ("12:00", "23:59"))
    ]
    ctx = navegador.new_context(viewport={"width": 1280, "height": 800}, permissions=["microphone"])
    pg = ctx.new_page()
    paso(pg, "La profesora tiene hoy dos bloques seguidos de Matemática en 9°A")
    entrar_staff(pg, rut_profesora)
    ir(pg, "Grabar").click()
    pg.get_by_role("button", name="Preparar grabación").first.wait_for(timeout=8000)
    tarjetas = pg.locator("li").filter(has_text="Matemática")
    comprobar("los dos bloques salen como una sola tarjeta", tarjetas.count() == 1, f"{tarjetas.count()} tarjetas")
    texto = tarjetas.first.inner_text()
    comprobar("con la hora de inicio del primero y de fin del último", "00:00" in texto and "23:59" in texto and "12:00" not in texto, texto.replace("\n", " "))

    paso(pg, "Prepara la grabación y la inicia con el micrófono simulado")
    pg.get_by_role("button", name="Preparar grabación").click()
    pg.get_by_role("button", name="Grabar con este equipo").click()
    pg.get_by_role("button", name="Iniciar la clase").click()
    pg.get_by_role("button", name="Pausar").wait_for(timeout=10000)
    comprobar("la clase doble se graba (aparece «Pausar»)", True)
    if TELEFONO:  # micrófono de verdad: que el servidor reciba audio (un trozo cada 10 s)
        token = llamar("POST", "/auth/login/staff", {"rut": rut_profesora, "password": CLAVE})["access_token"]
        sesion = llamar("GET", "/grabaciones/hoy", token=token)[0]["grabacion"]
        limite, trozos = time.time() + 40, 0
        while time.time() < limite and trozos == 0:
            pg.wait_for_timeout(2000)
            trozos = llamar("GET", f"/grabaciones/{sesion['id']}", token=token)["trozos"]
        comprobar("el servidor recibe audio real del micrófono del teléfono", trozos > 0, f"trozos={trozos}")
        pg.get_by_role("button", name="Pausar").click()
        pg.wait_for_timeout(1000)

    token_prof = llamar("POST", "/auth/login/staff", {"rut": rut_profesora, "password": CLAVE})["access_token"]
    hoy_api = llamar("GET", "/grabaciones/hoy", token=token_prof)
    comprobar("el servidor la tiene como una sola clase, del primer bloque", len(hoy_api) == 1 and hoy_api[0]["bloque_id"] == bloques[0], str(hoy_api)[:200])
    segunda = llamar("POST", "/grabaciones", {"bloque_id": bloques[1]}, token_prof)
    comprobar("grabar desde el segundo bloque retoma la misma sesión", segunda["bloque_id"] == bloques[0] and segunda["hora_fin"].startswith("23:59"), str(segunda)[:200])
    ctx.close()


AXE = RAIZ / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def axe(pg, donde: str) -> None:
    """Reglas WCAG 2.x A y AA (incluye el contraste, que solo se puede medir con el diseño real)."""
    pg.add_script_tag(path=str(AXE))
    problemas = pg.evaluate(
        """() => axe.run(document, {exclude: [['#e2e-paso']], runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}})
            .then(r => r.violations.map(v => v.id + ' x' + v.nodes.length + ' en ' + v.nodes[0].target.join(' ')))"""
    )
    comprobar(f"accesibilidad (axe): {donde}", not problemas, "; ".join(problemas))


def accesibilidad(navegador) -> None:
    print("\n[7] Accesibilidad de las pantallas nuevas, en modo claro y oscuro")
    for tema in ("light", "dark"):
        nombre_tema = "claro" if tema == "light" else "oscuro"
        ctx = navegador.new_context(viewport={"width": 1280, "height": 900}, color_scheme=tema)
        pg = ctx.new_page()
        paso(pg, f"Modo {nombre_tema}: alumno con un nombre que pide confirmación")
        unirse(pg, "DEMO8B", "Aitor Tilla", rut(22400020 + (tema == "dark")))
        pg.get_by_role("alert").filter(has_text="quedará asociado").wait_for(timeout=5000)
        axe(pg, f"cuadro de confirmación del nombre ({nombre_tema})")

        paso(pg, f"Modo {nombre_tema}: el UTP con las acciones de un alumno abiertas")
        entrar_staff(pg, "11111111-1")
        filas = abrir_alumnos(pg, "8°A")
        filas.first.get_by_role("button", name="Eliminar al alumno").click()
        filas.nth(1).get_by_role("button", name="Corregir el nombre").click()
        axe(pg, f"panel de alumnos del UTP ({nombre_tema})")

        paso(pg, f"Modo {nombre_tema}: el profesor con nombres marcados")
        pg.get_by_role("button", name="Cerrar sesión").filter(visible=True).first.click()
        entrar_staff(pg, "12345678-5")
        abrir_alumnos(pg, "8°A")
        axe(pg, f"panel de alumnos del profesor ({nombre_tema})")
        ctx.close()


# ---------- arranque ------------------------------------------------------------------------------------------------


# ---------- teléfono real por USB (adb) -----------------------------------------------------------------------------

PUERTO_DEPURACION = 9222


def adb(*argumentos: str, serie: str | None = None) -> str:
    cmd = ["adb", *(["-s", serie] if serie else []), *argumentos]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return (r.stdout or "") + (r.stderr or "")


def preparar_telefono(paquete: str) -> tuple[str, str]:
    """Deja el navegador del teléfono abierto en `localhost` y su depuración remota lista. Devuelve (serie, nombre)."""
    if shutil.which("adb") is None:
        raise RuntimeError("Falta `adb` (en Arch: pacman -S android-tools).")
    lineas = [l.split() for l in adb("devices").splitlines()[1:] if l.strip()]
    listos = [l[0] for l in lineas if len(l) > 1 and l[1] == "device"]
    if not listos:
        estados = ", ".join(f"{l[0]}: {l[1]}" for l in lineas if len(l) > 1) or "ninguno"
        raise RuntimeError(f"No hay un teléfono listo por USB ({estados}). Activa la «Depuración USB», acepta el aviso del teléfono y desbloquéalo.")
    serie = listos[0]
    modelo = adb("shell", "getprop", "ro.product.model", serie=serie).strip() or serie
    if f"package:{paquete}" not in adb("shell", "pm", "list", "packages", paquete, serie=serie):
        raise RuntimeError(f"El teléfono no tiene {paquete} (usa --paquete con otro navegador basado en Chromium).")
    adb("reverse", f"tcp:{PUERTO_WEB}", f"tcp:{PUERTO_WEB}", serie=serie)
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP", serie=serie)
    adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", f"http://localhost:{PUERTO_WEB}/", "-p", paquete, serie=serie)
    limite = time.time() + 25
    while time.time() < limite and "chrome_devtools_remote" not in adb("shell", "cat", "/proc/net/unix", serie=serie):
        time.sleep(1)
    if "chrome_devtools_remote" not in adb("shell", "cat", "/proc/net/unix", serie=serie):
        raise RuntimeError(f"{paquete} no abrió su depuración remota (¿la pantalla está desbloqueada y es un navegador basado en Chromium?).")
    adb("forward", f"tcp:{PUERTO_DEPURACION}", "localabstract:chrome_devtools_remote", serie=serie)
    return serie, modelo


def liberar_telefono(serie: str | None) -> None:
    adb("reverse", "--remove", f"tcp:{PUERTO_WEB}", serie=serie)
    adb("forward", "--remove", f"tcp:{PUERTO_DEPURACION}", serie=serie)


class _PaginaTelefono:
    """La pestaña del teléfono, con lo que los recorridos esperan de una página de PC (el contexto propio y el tamaño real)."""

    def __init__(self, pagina, contexto):
        self._pagina, self.context = pagina, contexto

    def __getattr__(self, nombre):
        return getattr(self._pagina, nombre)

    @property
    def viewport_size(self):
        return self._pagina.evaluate("({width: innerWidth, height: innerHeight})")


class _ContextoTelefono:
    """El teléfono tiene una sola ventana de datos: «un equipo nuevo» es la misma pestaña con el almacenamiento vacío."""

    def __init__(self, contexto_real, pagina_real, navegador):
        self._real, self._navegador = contexto_real, navegador
        self._pagina_real = pagina_real
        self.pagina = _PaginaTelefono(pagina_real, self)

    @property
    def pages(self):
        return [self.pagina]

    def _limpiar(self):
        self._pagina_real.goto(BASE + "/")
        self._pagina_real.evaluate("localStorage.clear()")
        self._pagina_real.goto(BASE + "/")

    def new_page(self):
        self._limpiar()
        return self.pagina

    def close(self):
        if not self._navegador.libre:
            self._limpiar()
            self._navegador.libre = True


class _NavegadorTelefono:
    """Hace pasar al teléfono (más el Chromium del computador, para un segundo equipo a la vez) por un navegador de Playwright."""

    def __init__(self, telefono, computador, al_error_de_consola):
        self._telefono, self._computador, self._al_error = telefono, computador, al_error_de_consola
        real = telefono.contexts[0]
        self.ctx = _ContextoTelefono(real, next(x for x in real.pages if f":{PUERTO_WEB}" in x.url), self)
        self.libre = True
        self.ctx._pagina_real.on("console", al_error_de_consola)

    @property
    def contexts(self):
        return [self.ctx, *self._computador.contexts]

    def new_context(self, **opciones):
        if self.libre:  # el primero en pedir un equipo se queda con el teléfono
            self.libre = False
            if "microphone" in opciones.get("permissions", []):
                try:
                    self.ctx._real.grant_permissions(["microphone"], origin=BASE)
                except Exception:  # si no se puede, el teléfono lo pedirá en pantalla
                    print("   (toca «Permitir» si el teléfono pide el micrófono)")
            return self.ctx
        c = self._computador.new_context(**{k: v for k, v in opciones.items() if k in ("viewport", "color_scheme", "permissions")})
        c.on("page", lambda pg: pg.on("console", self._al_error))
        return c

    def close(self):
        self._computador.close()
        self._telefono.close()  # solo se desconecta: el navegador del teléfono sigue abierto


def main() -> int:
    global DISPOSITIVO, ETIQUETA, TELEFONO, BASE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-ventana", action="store_true", help="no abre la ventana del navegador")
    ap.add_argument("--movil", action="store_true", help="emula un teléfono (Pixel 7) en vez de una pantalla de PC")
    ap.add_argument("--dispositivo", help="perfil de teléfono de Playwright a emular, p. ej. «Pixel 7» o «iPhone 13» (implica --movil)")
    ap.add_argument("--telefono", action="store_true", help="usa un teléfono Android real conectado por USB (necesita adb)")
    ap.add_argument("--paquete", default="com.brave.browser", help="navegador del teléfono basado en Chromium (por defecto Brave)")
    args = ap.parse_args()
    if args.telefono and (args.movil or args.dispositivo):
        print("--telefono no se combina con --movil ni --dispositivo.")
        return 2
    if args.telefono:
        TELEFONO, BASE = True, f"http://localhost:{PUERTO_WEB}"  # `localhost` es contexto seguro en el teléfono (micrófono)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Falta Playwright: pip install -r requirements-e2e.txt && playwright install chromium")
        return 2

    npx = shutil.which("npx")
    if npx is None:
        print("Falta Node (npx) para levantar el frontend.")
        return 2
    carpeta = Path(tempfile.mkdtemp(prefix="claseaidia-e2e-"))
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{carpeta / 'demo.db'}", "PYTHONUTF8": "1",
           "JWT_SECRET_KEY": "clave-solo-para-pruebas-en-navegador-0123456789", "API_URL": f"http://127.0.0.1:{PUERTO_API}"}
    procesos: list[subprocess.Popen] = []
    serie_telefono: str | None = None
    try:
        print("Sembrando una base de demostración nueva…")
        subprocess.run([sys.executable, "-m", "scripts.sembrar_demo"], cwd=RAIZ, env=env, check=True, capture_output=True)
        procesos.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "api:app", "--port", str(PUERTO_API), "--host", "127.0.0.1"], cwd=RAIZ, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        procesos.append(subprocess.Popen([npx, "vite", "--port", str(PUERTO_WEB), "--host", "127.0.0.1", "--strictPort"], cwd=RAIZ / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        esperar(f"{BASE}/api/auth/estado")

        CAPTURAS.mkdir(exist_ok=True)
        with sync_playwright() as p:
            motor_nombre = "chromium"
            if args.movil or args.dispositivo:
                ETIQUETA = args.dispositivo or "Pixel 7"
                if ETIQUETA not in p.devices:
                    print(f"Playwright no conoce el dispositivo «{ETIQUETA}».")
                    return 2
                perfil = dict(p.devices[ETIQUETA])
                motor_nombre = perfil.pop("default_browser_type", "chromium")
                DISPOSITIVO = perfil
                print(f"Emulando {ETIQUETA} ({motor_nombre}): pantalla táctil de teléfono, no un teléfono real.")
            opciones_motor = {"args": ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]} if motor_nombre == "chromium" else {}
            errores_consola: list[str] = []

            def al_error_de_consola(m):
                if m.type == "error" and "Failed to load resource" not in m.text:
                    errores_consola.append(m.text)

            if args.telefono:
                try:
                    serie_telefono, modelo = preparar_telefono(args.paquete)
                except RuntimeError as e:
                    print(f"No se pudo preparar el teléfono: {e}")
                    return 2
                partes = args.paquete.split(".")
                ETIQUETA = f"{modelo} · {(partes[-2] if partes[-1] == 'browser' and len(partes) > 1 else partes[-1]).capitalize()}"  # com.brave.browser -> Brave
                print(f"Teléfono real: {ETIQUETA} (por USB y adb). Mantén la pantalla desbloqueada; si pide permiso de micrófono, toca «Permitir».")
                computador = p.chromium.launch(headless=args.sin_ventana, **opciones_motor)  # segundo equipo cuando un recorrido lo pide
                navegador = _NavegadorTelefono(p.chromium.connect_over_cdp(f"http://127.0.0.1:{PUERTO_DEPURACION}"), computador, al_error_de_consola)
            else:
                navegador = getattr(p, motor_nombre).launch(headless=args.sin_ventana, **opciones_motor)
                nuevo_contexto = navegador.new_context

                def contexto_vigilado(**opciones):
                    if DISPOSITIVO:  # el perfil manda en pantalla, táctil y agente; solo se conservan permisos y tema
                        opciones = {**DISPOSITIVO, **{k: v for k, v in opciones.items() if k in ("permissions", "color_scheme")}}
                    c = nuevo_contexto(**opciones)
                    c.on("page", lambda pg: pg.on("console", al_error_de_consola))
                    return c

                navegador.new_context = contexto_vigilado  # así toda página nueva queda vigilada
            recorridos = [
                lambda: alumno_se_inscribe(navegador, "PC", 1280, 800, "Alan Brito", rut(22400001)),
                lambda: alumno_se_inscribe(navegador, "celular", 390, 844, "Armando Casas", rut(22400002)),
                lambda: un_rut_un_curso(navegador),
                lambda: una_sesion(navegador),
                lambda: estado_dispositivos(navegador),
                lambda: clase_doble(navegador),
                lambda: descargar_pdf(navegador),
                lambda: profesor(navegador),
                lambda: grabar_clase_doble(navegador),
            ]
            if args.telefono:
                print("   (en el teléfono no corren «accesibilidad» ni «UTP»: dependen de cambiar el tema y de teclear números; ya pasan en --movil)")
            else:
                recorridos += [lambda: accesibilidad(navegador), lambda: utp(navegador), lambda: ajustes_modelo_texto(navegador)]
            if DISPOSITIVO:
                if motor_nombre != "chromium":  # el micrófono simulado es de Chromium
                    recorridos = [r for r in recorridos if r.__code__.co_names.count("grabar_clase_doble") == 0]
                    print("   (se omite «Grabar»: el micrófono simulado solo existe en Chromium)")
            for numero, recorrido in enumerate(recorridos, 1):
                try:
                    recorrido()
                except Exception as e:  # un recorrido roto no impide ver los demás
                    comprobar(f"el recorrido {numero} terminó sin errores", False, f"{type(e).__name__}: {str(e).splitlines()[0]}")
                    for i, c in enumerate(navegador.contexts):
                        for j, pg in enumerate(c.pages):
                            pg.screenshot(path=str(CAPTURAS / f"fallo_{numero}_{i}_{j}.png"))
                    for c in navegador.contexts:
                        c.close()
            comprobar("sin errores en la consola del navegador", not errores_consola, "; ".join(errores_consola[:3]))
            navegador.close()
    finally:
        if serie_telefono:
            liberar_telefono(serie_telefono)
        for proceso in procesos:
            proceso.terminate()
        shutil.rmtree(carpeta, ignore_errors=True)

    print(f"\n{'TODO BIEN' if not FALLOS else 'HAY FALLAS'}: {len(FALLOS)} fallo(s)" + ("" if not FALLOS else " -> " + "; ".join(FALLOS)))
    return 1 if FALLOS else 0


if __name__ == "__main__":
    sys.exit(main())
