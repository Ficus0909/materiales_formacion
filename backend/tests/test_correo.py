import json

import pytest

from app.config import settings
from app.services import correo
from .conftest import PDF, login


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
    # Un solo correo: designación como líder (lote, centro y vigencia) + credenciales
    assert [c["para"] for c in buzon] == ["ana@sena.edu.co"]
    texto = buzon[0]["texto"]
    assert "Designación como líder del lote 1. Agrícola" in buzon[0]["asunto"]
    assert "Líder del lote 1. Agrícola (Agric) del Centro de Atención al Sector Agropecuario" in texto
    assert "Vigencia del proceso: 2027, abierta del 01/09/2026 al 30/11/2026" in texto
    assert "Temporal1!" in texto
    # y un aviso en la aplicación
    lider = login(client, "ana@sena.edu.co", "Temporal1!")
    assert client.get("/api/notificaciones", headers=lider).json()["items"][0]["titulo"].startswith("Designación")


def test_designacion_al_cambiar_de_lote(client, admin, buzon):
    lotes = client.get("/api/lotes", headers=admin).json()
    u = next(x for x in client.get("/api/usuarios", headers=admin).json() if x["email"] == "lider.agric@sena.edu.co")
    datos = {"nombre": u["nombre"], "email": u["email"], "rol": "LIDER", "lote_id": u["lote_id"]}
    # Editar sin cambiar el lote ni la clave no envía nada
    r = client.put(f"/api/usuarios/{u['id']}", headers=admin, json={**datos, "nombre": "Otro nombre"}).json()
    assert buzon == [] and not r["designado"]
    # Cambiar de lote: nueva designación, sin credenciales
    r = client.put(f"/api/usuarios/{u['id']}", headers=admin, json={**datos, "lote_id": lotes[1]["id"]}).json()
    assert r["designado"] and r["correo_enviado"]
    assert len(buzon) == 1 and "lote 2. Artesanías" in buzon[0]["asunto"]
    assert "Contraseña temporal" not in buzon[0]["texto"]


def test_designacion_sin_vigencia_abierta(client, admin, manager, buzon):
    vig = client.get("/api/vigencias/activa", headers=manager).json()
    client.post(f"/api/vigencias/{vig['id']}/cerrar", headers=manager)
    client.post("/api/vigencias", headers=manager, json={"codigo": "2028", "anio": 2028, "fecha_inicio": "2027-09-01",
                                                         "fecha_cierre": "2027-11-30"})
    buzon.clear()
    lote = client.get("/api/lotes", headers=admin).json()[0]["id"]
    client.post("/api/usuarios", headers=admin, json={"nombre": "Beto", "email": "beto@sena.edu.co", "rol": "LIDER",
                                                      "lote_id": lote, "password": "Temporal1!"})
    assert "Vigencia del proceso: 2028, programada del 01/09/2027 al 30/11/2027" in buzon[0]["texto"]
    assert "Recibirá un aviso cuando se abra" in buzon[0]["texto"]


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
