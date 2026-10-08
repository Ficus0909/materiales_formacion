import json

import pytest

from app.config import settings
from app.services import correo
from .conftest import PDF


@pytest.fixture()
def buzon(monkeypatch):
    """Activa el SMTP y captura los correos en lugar de enviarlos."""
    enviados = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "materiales@sena.edu.co")
    monkeypatch.setattr(correo, "enviar_async", lambda lote: enviados.extend(lote))
    return enviados


def test_credenciales_al_crear_usuario(client, admin, buzon):
    lotes = client.get("/api/lotes", headers=admin).json()
    r = client.post("/api/usuarios", headers=admin, json={
        "nombre": "Ana Pérez", "email": "ana@sena.edu.co", "rol": "LIDER", "lote_id": lotes[0]["id"],
        "password": "Temporal1!"}).json()
    assert r["correo_enviado"]
    assert [c["para"] for c in buzon] == ["ana@sena.edu.co"]
    assert "Temporal1!" in buzon[0]["texto"] and "Agrícola" in buzon[0]["texto"]


def test_sin_correo_si_falla_la_transaccion(client, admin, manager, buzon):
    # correo duplicado -> 409, no se crea el usuario y no se envía nada
    centro = client.get("/api/centros", headers=admin).json()[0]["id"]
    r = client.post("/api/usuarios", headers=manager, json={"nombre": "X", "email": "admin@sena.edu.co", "rol": "ADMIN",
                                                            "centro_id": centro, "password": "Temporal1!"})
    assert r.status_code == 409 and buzon == []


def test_notificaciones_por_correo_en_el_flujo(client, admin, lider, buzon):
    arts = client.get("/api/articulos", headers=lider).json()["items"]
    provs = client.get("/api/proveedores", headers=lider).json()
    aid = arts[0]["id"]
    for p, precio in zip(provs[:2], (1000, 1100)):
        client.post("/api/cotizaciones", headers=lider, data={"proveedor_id": p["id"], "fecha": "2026-09-10",
                                                               "precios": json.dumps({aid: precio})},
                    files={"pdf": ("c.pdf", PDF, "application/pdf")})
    sid = client.get("/api/solicitudes/mia", headers=lider).json()["solicitud"]["id"]
    client.put(f"/api/solicitudes/{sid}/items", headers=lider, json=[{"articulo_id": aid, "cantidad": 3}])
    buzon.clear()
    client.post(f"/api/solicitudes/{sid}/enviar", headers=lider)
    assert [c["para"] for c in buzon] == ["admin@sena.edu.co"]
    assert f"/admin/solicitudes/{sid}" in buzon[0]["texto"]
    buzon.clear()
    client.post(f"/api/solicitudes/{sid}/decidir", headers=admin, json={"accion": "DEVOLVER", "observaciones": "Revise cantidades"})
    assert [c["para"] for c in buzon] == ["lider.agric@sena.edu.co"]
    assert "Revise cantidades" in buzon[0]["texto"] and "devuelta" in buzon[0]["asunto"]


def test_sin_smtp_no_se_encola(client, admin, monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar_async", lambda lote: enviados.extend(lote))
    lotes = client.get("/api/lotes", headers=admin).json()
    r = client.post("/api/usuarios", headers=admin, json={"nombre": "B", "email": "b@sena.edu.co", "rol": "LIDER",
                                                          "lote_id": lotes[0]["id"], "password": "Temporal1!"}).json()
    assert not r["correo_enviado"] and enviados == []
    assert client.post("/api/correo/prueba", headers=admin).status_code == 409
