"""Endurecimiento: política de contraseñas/PIN, inyección SQL, tokens y claves.
Contexto y hallazgos: QA.md (2026-10-01)."""
import pathlib
import re

import jwt
import pytest

from infraestructura import seguridad

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Payloads clásicos de inyección SQL (y un par de bytes raros).
PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    '" OR ""="',
    "admin'--",
    "'; DROP TABLE usuarios; --",
    "1; SELECT * FROM usuarios",
    "' UNION SELECT password_hash FROM usuarios --",
    "x') OR ('1'='1",
    "\\' OR 1=1 #",
    "\x00' OR 1=1",
]


# --- Política de contraseñas ---------------------------------------------------


@pytest.mark.parametrize(
    "password",
    [
        "corta",  # menos de 10
        "123456789",  # 9 caracteres
        "a" * 129,  # sobre el tope
        "aaaaaaaaaaaa",  # un solo carácter
        "ab" * 6,  # dos caracteres
        "clave7654321clave",  # contiene el RUT
    ],
)
def test_setup_rechaza_contraseñas_debiles(cliente, rut_utp, password):
    r = cliente.post("/auth/setup", json={"colegio_nombre": "L", "rut": rut_utp, "nombre": "U", "password": password})
    assert r.status_code == 422, password
    assert password not in r.text  # el 422 tampoco devuelve lo enviado


def test_crear_usuario_aplica_la_misma_politica(cliente, colegio_id, headers_utp):
    datos = {"rut": "5126663-3", "nombre": "P", "colegio_id": colegio_id, "roles": ["PROFESOR"]}
    assert cliente.post("/usuarios", json={**datos, "password": "corta"}, headers=headers_utp).status_code == 422
    assert cliente.post("/usuarios", json={**datos, "password": "clave-5126663-x"}, headers=headers_utp).status_code == 422
    assert cliente.post("/usuarios", json={**datos, "password": "una-clave-larga-1"}, headers=headers_utp).status_code == 201


def test_login_rechaza_password_gigante_sin_gastar_argon2(cliente, rut_utp):
    r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "a" * 100_000})
    assert r.status_code == 422


@pytest.mark.parametrize("pin", ["111111", "000000", "123456", "654321", "234567", "012345", "987654"])
def test_pin_facil_no_se_puede_elegir(cliente, colegio_id, headers_utp, pin):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    r = cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": pin},
    )
    assert r.status_code == 422, pin
    assert cliente.post("/auth/login/alumno", json={"rut": "11222333-9", "pin": pin}).status_code == 401  # no se creó


def test_pin_facil_tampoco_vale_al_restablecer_y_no_gasta_el_codigo(cliente, colegio_id, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    cliente.post(
        "/cursos/unirse",
        json={"codigo_invitacion": curso["codigo_invitacion"], "rut": "11222333-9", "nombre": "A", "pin": "482915"},
    )
    id_alumno = next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["rut"] == "11222333-9")
    codigo = cliente.post(f"/usuarios/{id_alumno}/reset-pin", headers=headers_utp).json()["codigo"]

    r = cliente.post("/auth/restablecer-pin", json={"rut": "11222333-9", "codigo": codigo, "pin": "111111"})
    assert r.status_code == 422
    r = cliente.post("/auth/restablecer-pin", json={"rut": "11222333-9", "codigo": codigo, "pin": "730164"})
    assert r.status_code == 200  # el código seguía vigente


# --- Inyección SQL ------------------------------------------------------------


def test_inyeccion_sql_en_todos_los_campos_de_texto(cliente, colegio_id, rut_utp, headers_utp):
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()
    rutas = [
        ("/auth/login/staff", lambda p: {"rut": p, "password": p}),
        ("/auth/login/alumno", lambda p: {"rut": p, "pin": p}),
        ("/auth/restablecer-pin", lambda p: {"rut": p, "codigo": p, "pin": p}),
        ("/auth/setup", lambda p: {"colegio_nombre": p, "rut": p, "nombre": p, "password": p}),
        ("/cursos/unirse", lambda p: {"codigo_invitacion": p, "rut": p, "nombre": p, "pin": p}),
        # Código válido pero RUT/nombre/PIN con payload.
        (
            "/cursos/unirse",
            lambda p: {"codigo_invitacion": curso["codigo_invitacion"], "rut": p, "nombre": p, "pin": p},
        ),
        # Código con payload, resto válido.
        ("/cursos/unirse", lambda p: {"codigo_invitacion": p, "rut": "11222333-9", "nombre": "A", "pin": "482915"}),
    ]
    for payload in PAYLOADS:
        for ruta, armar in rutas:
            r = cliente.post(ruta, json=armar(payload))
            # Nunca una sesión, nunca un error de servidor.
            assert r.status_code in (401, 404, 409, 422), (ruta, payload, r.status_code)
            assert "access_token" not in r.text, (ruta, payload)

    # Las tablas siguen ahí y el UTP legítimo sigue entrando.
    r = cliente.post("/auth/login/staff", json={"rut": rut_utp, "password": "clave-segura-123"})
    assert r.status_code == 200


def test_payloads_en_nombres_se_guardan_como_texto_y_no_se_ejecutan(cliente, colegio_id, headers_utp):
    for payload in PAYLOADS:
        r = cliente.post("/cursos", json={"nombre": payload, "colegio_id": colegio_id}, headers=headers_utp)
        assert r.status_code == 201, payload
    nombres = {c["nombre"] for c in cliente.get("/cursos", headers=headers_utp).json()}
    assert set(PAYLOADS) <= nombres  # vuelven idénticos: se trataron como datos
    assert cliente.get("/usuarios", headers=headers_utp).status_code == 200  # `usuarios` no fue borrada


def test_no_hay_sql_armado_a_mano_en_el_backend():
    """Guardia contra regresiones: todo acceso a datos va por el ORM. La única excepción
    es el PRAGMA fijo de basedatos.py y la verificación de un respaldo
    (un PRAGMA y un SELECT fijos sobre el archivo de la copia, sin datos de nadie)."""
    patron = re.compile(r"\btext\(|exec_driver_sql|\.execute\(|executescript|\.raw\(")
    encontrados = {}
    for carpeta in ["interfaz", "infraestructura", "servicios", "nucleo"]:
        for archivo in (RAIZ / carpeta).rglob("*.py"):
            n = len(patron.findall(archivo.read_text(encoding="utf-8")))
            if n:
                encontrados[archivo.relative_to(RAIZ).as_posix()] = n
    assert encontrados == {"infraestructura/basedatos.py": 1, "servicios/servicio_respaldo.py": 2}

    respaldo = (RAIZ / "servicios" / "servicio_respaldo.py").read_text(encoding="utf-8")
    assert not re.search(r"""\.execute\(\s*(f['"]|['"][^'"]*['"]\s*[+%]|[^'"\s])""", respaldo), "el SQL de la verificación debe ser solo texto fijo"


# --- Tokens y clave -----------------------------------------------------------


def _claims(**cambios):
    datos = {"sub": "1", "exp": 4102444800, **cambios}  # exp en el año 2100
    return {k: v for k, v in datos.items() if v is not None}


def _firmar(claims, clave=None, algoritmo="HS256"):
    return jwt.encode(claims, clave if clave is not None else seguridad.JWT_SECRET_KEY, algorithm=algoritmo)


@pytest.mark.parametrize(
    "fabricar",
    [
        pytest.param(lambda: _firmar(_claims(), algoritmo="HS512"), id="otro-algoritmo"),
        pytest.param(lambda: _firmar(_claims(), clave="otra-clave-" * 4), id="clave-ajena"),
        pytest.param(lambda: _firmar(_claims(), clave="", algoritmo="none"), id="alg-none"),
        pytest.param(lambda: _firmar(_claims(exp=None)), id="sin-exp"),
        pytest.param(lambda: _firmar(_claims(exp=1)), id="vencido"),
        pytest.param(lambda: _firmar(_claims(sub=None)), id="sin-sub"),
        pytest.param(lambda: "no.es.untoken", id="basura"),
    ],
)
def test_tokens_falsos_o_mal_formados_dan_401(cliente, colegio_id, fabricar):
    r = cliente.get(f"/colegios/{colegio_id}", headers={"Authorization": f"Bearer {fabricar()}"})
    assert r.status_code == 401


def test_token_con_firma_alterada_da_401(cliente, colegio_id, token_utp):
    cabecera, cuerpo, firma = token_utp.split(".")
    alterado = ".".join([cabecera, cuerpo, firma[:-2] + ("AA" if not firma.endswith("AA") else "BB")])
    assert cliente.get(f"/colegios/{colegio_id}", headers={"Authorization": f"Bearer {alterado}"}).status_code == 401


def test_clave_jwt():
    with pytest.raises(RuntimeError):
        seguridad.cargar_clave_jwt("corta")
    assert seguridad.cargar_clave_jwt("k" * 32) == "k" * 32
    temporal = seguridad.cargar_clave_jwt(None)
    assert len(temporal) == 64 and temporal != seguridad.cargar_clave_jwt("")


def test_verificar_secreto_falso_no_lanza():
    seguridad.verificar_secreto_falso("lo-que-sea")  # camino de RUT inexistente
