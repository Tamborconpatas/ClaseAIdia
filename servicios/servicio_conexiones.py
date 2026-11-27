# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Quién está conectado y desde qué equipo, para el panel de estado del UTP.

Se guarda lo mínimo y nada que identifique a la persona fuera de la aplicación: un código aleatorio que el propio
navegador se pone (cabecera `X-Dispositivo`) y un resumen como «Teléfono · Android · Chrome». NO se guarda la dirección
IP, ni el número de teléfono, ni la ubicación, ni el texto completo del navegador. Todo se borra a los 30 días sin uso.
Es el rastro que permite ubicar de dónde salió una cuenta con un nombre indebido; el aviso de privacidad lo declara.
"""
import datetime
import re

from sqlalchemy.orm import Session

from infraestructura.modelos_orm import AlumnoCurso, Dispositivo, Usuario
from infraestructura.seguridad import ahora_utc

DIAS_RASTRO = 30
MINUTOS_CONECTADO = 5  # sin actividad más allá de esto, ya no cuenta como conectado
_ACTUALIZAR_CADA_S = 60  # la actividad se anota como mucho una vez por minuto por persona (no una escritura por petición)
_CODIGO = re.compile(r"[0-9a-f]{16,40}")
_ROLES = ("UTP", "PROFESOR", "ALUMNO")

ultima_limpieza: datetime.datetime | None = None


def resumen_dispositivo(user_agent: str | None) -> str:
    """«Teléfono · Android · Chrome». Solo tipo, sistema y navegador: el texto original del navegador no se guarda."""
    ua = user_agent or ""
    if re.search(r"iPad|Tablet", ua) or ("Android" in ua and "Mobile" not in ua):
        tipo = "Tablet"
    elif re.search(r"Mobile|iPhone", ua):
        tipo = "Teléfono"
    else:
        tipo = "Computador"
    sistemas = (("Windows", "Windows"), ("Android", "Android"), ("iPhone|iPad|iPod", "iOS"), ("Mac OS X|Macintosh", "macOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))
    navegadores = (("Edg/", "Edge"), ("OPR/|Opera", "Opera"), ("Firefox/|FxiOS", "Firefox"), ("SamsungBrowser", "Samsung Internet"), ("CriOS|Chrome/", "Chrome"), ("Safari/", "Safari"))
    sistema = next((n for p, n in sistemas if re.search(p, ua)), "otro sistema")
    navegador = next((n for p, n in navegadores if re.search(p, ua)), "otro navegador")
    return f"{tipo} · {sistema} · {navegador}"


def codigo_de(request) -> str | None:
    """El código que manda el navegador, o None si falta o no es el esperado (un valor inventado no se guarda)."""
    valor = (request.headers.get("x-dispositivo") or "").strip().lower()
    return valor if _CODIGO.fullmatch(valor) else None


def dispositivo_de(db: Session, colegio_id: int, request, ahora: datetime.datetime | None = None) -> Dispositivo | None:
    """El dispositivo de esta petición (se crea la primera vez). None si el navegador no mandó su código."""
    codigo = codigo_de(request)
    if codigo is None:
        return None
    ahora = ahora or ahora_utc()
    resumen = resumen_dispositivo(request.headers.get("user-agent"))
    d = db.query(Dispositivo).filter_by(colegio_id=colegio_id, codigo=codigo).first()
    if d is None:
        d = Dispositivo(colegio_id=colegio_id, codigo=codigo, resumen=resumen, ultima_vez=ahora)
        db.add(d)
        db.flush()
    else:
        d.resumen, d.ultima_vez = resumen, ahora
    return d


def registrar_actividad(db: Session, usuario: Usuario, request) -> None:
    """Anota que esta persona está activa, desde este equipo. Limitado a una escritura por minuto."""
    ahora = ahora_utc()
    if usuario.visto_en and (ahora - usuario.visto_en).total_seconds() < _ACTUALIZAR_CADA_S:
        return
    d = dispositivo_de(db, usuario.colegio_id, request, ahora)
    usuario.visto_en = ahora
    if d is not None:
        usuario.dispositivo_id = d.id
    db.commit()


def _corto(d: Dispositivo | None) -> str | None:
    return d.codigo[-4:].upper() if d else None


def _rol(u: Usuario) -> str:
    roles = {r.rol.value for r in u.roles}
    return next((r for r in _ROLES if r in roles), "")


def conexiones(db: Session, colegio_id: int, ahora: datetime.datetime | None = None) -> dict:
    """Para el panel del UTP: quién está conectado ahora y desde dónde salió cada cuenta con el nombre por revisar."""
    ahora = ahora or ahora_utc()
    desde = ahora - datetime.timedelta(minutes=MINUTOS_CONECTADO)
    dispositivos = {d.id: d for d in db.query(Dispositivo).filter_by(colegio_id=colegio_id)}
    conectados = sorted(
        (u for u in db.query(Usuario).filter(Usuario.colegio_id == colegio_id, Usuario.visto_en >= desde)),
        key=lambda u: u.visto_en,
        reverse=True,
    )
    por_revisar = []
    for u in db.query(Usuario).filter_by(colegio_id=colegio_id, revisar_nombre=True).order_by(Usuario.nombre):
        d = dispositivos.get(u.registro_dispositivo_id) or dispositivos.get(u.dispositivo_id)
        otras = []
        if d is not None:
            otras = sorted(o.nombre for o in db.query(Usuario).filter(Usuario.id != u.id, (Usuario.dispositivo_id == d.id) | (Usuario.registro_dispositivo_id == d.id)))
        por_revisar.append({
            "alumno": u.nombre,
            "cursos": sorted(a.curso.nombre for a in db.query(AlumnoCurso).filter_by(usuario_id=u.id)),
            "dispositivo": d.resumen if d else None,
            "codigo": _corto(d),
            "otras_cuentas": otras[:5],
        })
    return {
        "conectados": [
            {"nombre": u.nombre, "rol": _rol(u), "dispositivo": dispositivos[u.dispositivo_id].resumen if u.dispositivo_id in dispositivos else None,
             "codigo": _corto(dispositivos.get(u.dispositivo_id)), "hace_segundos": int((ahora - u.visto_en).total_seconds())}
            for u in conectados
        ],
        "dispositivos_conectados": len({u.dispositivo_id for u in conectados if u.dispositivo_id}),
        "nombres_por_revisar": por_revisar,
        "dias_de_rastro": DIAS_RASTRO,
    }


def limpiar(db: Session, ahora: datetime.datetime | None = None) -> None:
    """Borra lo que pasó de DIAS_RASTRO sin uso: los equipos viejos (y todo enlace a ellos) y las horas de conexión viejas."""
    ahora = ahora or ahora_utc()
    limite = ahora - datetime.timedelta(days=DIAS_RASTRO)
    viejos = [d.id for d in db.query(Dispositivo.id).filter(Dispositivo.ultima_vez < limite)]
    if viejos:
        db.query(Usuario).filter(Usuario.dispositivo_id.in_(viejos)).update({"dispositivo_id": None}, synchronize_session=False)
        db.query(Usuario).filter(Usuario.registro_dispositivo_id.in_(viejos)).update({"registro_dispositivo_id": None}, synchronize_session=False)
        db.query(Dispositivo).filter(Dispositivo.id.in_(viejos)).delete(synchronize_session=False)
    db.query(Usuario).filter(Usuario.visto_en < limite).update({"visto_en": None}, synchronize_session=False)
    db.commit()


def limpiar_si_toca(db: Session, ahora: datetime.datetime | None = None) -> None:
    """La vigilancia lo llama en cada pasada; la limpieza real corre como mucho una vez por hora."""
    global ultima_limpieza
    ahora = ahora or ahora_utc()
    if ultima_limpieza is None or (ahora - ultima_limpieza).total_seconds() >= 3600:
        limpiar(db, ahora)
        ultima_limpieza = ahora
