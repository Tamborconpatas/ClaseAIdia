# Copyright 2026 Tamborconpatas (Creador Original)
# Este archivo forma parte del proyecto "Transcriptor de clases (ClaseAIdia)".
# Este software se rige por la Licencia Apache v2.0 sujeta a las condiciones de la "Commons Clause" v1.0.
# Uso comercial restringido para terceros por la Commons Clause v1.0; el titular conserva todos sus derechos.
# Términos completos en el archivo LICENSE de la raíz.

"""Dos bloques seguidos de la misma asignatura (clase doble) son una sola clase: una grabación y un material."""
import datetime

from servicios import servicio_grabacion as sg

CLAVE = "clave-segura-123"
LUNES_1000 = datetime.datetime(2026, 9, 28, 10, 0)


def test_bloques_seguidos_son_una_sola_clase(cliente, colegio_id, headers_utp, monkeypatch):
    monkeypatch.setattr(sg, "ahora_local", lambda: LUNES_1000)
    cliente.post("/usuarios", json={"rut": "5126663-3", "nombre": "Ana", "colegio_id": colegio_id, "roles": ["PROFESOR"], "password": CLAVE}, headers=headers_utp)
    ana_id = next(u["id"] for u in cliente.get("/usuarios", headers=headers_utp).json() if u["rut"] == "5126663-3")
    ana = {"Authorization": "Bearer " + cliente.post("/auth/login/staff", json={"rut": "5126663-3", "password": CLAVE}).json()["access_token"]}
    curso = cliente.post("/cursos", json={"nombre": "8A", "colegio_id": colegio_id}, headers=headers_utp).json()["id"]

    def bloque(ini, fin, asignatura="Matemática"):
        r = cliente.post(f"/cursos/{curso}/bloques", json={"tipo": "CLASE", "asignatura": asignatura, "profesor_id": ana_id, "dia_semana": 0, "hora_inicio": ini, "hora_fin": fin}, headers=headers_utp)
        assert r.status_code == 201
        return r.json()["id"]

    # Matemática 09:00-10:30 en dos bloques; Matemática otra vez tras un recreo (no es la misma clase); y Lenguaje pegado.
    m1, m2 = bloque("09:00", "09:45"), bloque("09:45", "10:30")
    m3 = bloque("10:45", "11:30")
    lenguaje = bloque("11:30", "12:15", "Lenguaje")

    por_id = {b["id"]: b for b in cliente.get(f"/cursos/{curso}/bloques", headers=headers_utp).json()}
    assert [por_id[i]["cabeza_id"] for i in (m1, m2, m3, lenguaje)] == [m1, m1, m3, lenguaje]

    # El profesor ve una sola tarjeta para la clase doble, con la hora de fin del último bloque.
    hoy = cliente.get("/grabaciones/hoy", headers=ana).json()
    assert [(h["bloque_id"], h["hora_fin"]) for h in hoy] == [(m1, "10:30:00"), (m3, "11:30:00"), (lenguaje, "12:15:00")]

    # Grabar desde el segundo bloque cae en la misma sesión del primero, que corta al final del segundo.
    g = cliente.post("/grabaciones", json={"bloque_id": m2}, headers=ana)
    assert g.status_code == 201 and g.json()["bloque_id"] == m1 and g.json()["hora_fin"] == "10:30:00"
    assert cliente.post("/grabaciones", json={"bloque_id": m1}, headers=ana).json()["id"] == g.json()["id"]
    assert [c["bloque_id"] for c in cliente.get("/clases", headers=ana).json()] == [m1]
