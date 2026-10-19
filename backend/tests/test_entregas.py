"""Entrega de materiales a instructores (formato GIL-F-014)."""
import io
from datetime import date, timedelta

import pytest
from PIL import Image

from app.config import settings
from app.db import SessionLocal
from app.models import Articulo, EstadoPost, Lote, Solicitud, SolicitudItem, Usuario, Vigencia
from app.services import correo
from app.services.entregas import avisar_extemporaneas, sumar_dias_habiles
from .conftest import login


def _imagen(fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, fmt)
    return buf.getvalue()


@pytest.fixture()
def buzon(monkeypatch):
    enviados = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "materiales@sena.edu.co")
    monkeypatch.setattr(correo, "enviar_async", lambda lote: enviados.extend(lote))
    return enviados


@pytest.fixture()
def escenario(client, admin, monkeypatch):
    """Lote Agrícola con material recibido (solicitud aprobada al final del ciclo de compra), un coordinador por
    coordinación y un instructor aprobado de la Coordinación Académica."""
    monkeypatch.setattr(settings, "REGISTRO_DOMINIOS", ["sena.edu.co"])
    with SessionLocal() as db:
        lote = db.query(Lote).filter_by(abreviatura="Agric").one()
        vig = db.query(Vigencia).filter_by(codigo="2026").one()
        fin = db.query(EstadoPost).order_by(EstadoPost.orden.desc()).first()
        lider = db.query(Usuario).filter_by(email="lider.agric@sena.edu.co").one()
        s = Solicitud(vigencia_id=vig.id, lote_id=lote.id, lider_id=lider.id, estado="APROBADA", estado_post_id=fin.id)
        arts = {a.nombre: a for a in db.query(Articulo).filter_by(lote_id=lote.id)}
        s.items = [SolicitudItem(articulo_id=arts["Aceite agrícola"].id, cantidad=10, precio_aprobado=30000),
                   SolicitudItem(articulo_id=arts["Azufre mineral"].id, cantidad=4, precio_aprobado=8000)]
        db.add(s)
        db.commit()
        items = {i.articulo.nombre: i.id for i in s.items}
        lote_id = lote.id
    coords = {c["nombre"]: c["id"] for c in client.get("/api/coordinaciones", headers=admin).json()}
    assert len(coords) == 3
    acad = coords["Coordinación Académica"]
    for email, cid in (("coord.acad@sena.edu.co", acad), ("coord.esp@sena.edu.co", coords["Coordinación de Programas Especiales"])):
        r = client.post("/api/usuarios", headers=admin, json={"nombre": f"Coord {email[6:10]}", "email": email,
                                                              "rol": "COORDINADOR", "coordinacion_id": cid,
                                                              "password": "Clave123!"})
        assert r.status_code == 201, r.text
    client.post("/api/usuarios", headers=admin, json={"nombre": "Instructor Uno", "email": "inst1@sena.edu.co",
                                                      "rol": "INSTRUCTOR", "coordinacion_id": acad, "documento": "1098765432",
                                                      "password": "Clave123!"})
    return {"lote": lote_id, "items": items, "acad": acad, "coords": coords,
            "coord": login(client, "coord.acad@sena.edu.co", "Clave123!"),
            "coord_otra": login(client, "coord.esp@sena.edu.co", "Clave123!"),
            "inst": login(client, "inst1@sena.edu.co", "Clave123!")}


def _solicitar(client, h, esc, cantidades, **extra):
    body = {"lote_id": esc["lote"], "ficha": "2671234", "destino": "FORMACION",
            "items": [{"solicitud_item_id": esc["items"][n], "cantidad": c} for n, c in cantidades.items()], **extra}
    return client.post("/api/entregas", headers=h, json=body)


def _firma(client, h):
    r = client.post("/api/auth/firma", headers=h, files={"archivo": ("firma.png", _imagen(), "image/png")})
    assert r.status_code == 200, r.text


# --- Registro -------------------------------------------------------------------
def test_autorregistro_requiere_aprobacion(client, admin, escenario, buzon):
    opciones = client.get("/api/auth/registro/opciones").json()
    centro = opciones["centros"][0]
    datos = {"nombre": "Nuevo Instructor", "email": "nuevo@gmail.com", "documento": "1.098.111.222",
             "password": "Clave123!", "centro_id": centro["id"], "coordinacion_id": escenario["acad"]}
    assert client.post("/api/auth/registro", json=datos).status_code == 422  # dominio no institucional
    r = client.post("/api/auth/registro", json={**datos, "email": "nuevo@sena.edu.co"})
    assert r.status_code == 201, r.text
    assert {c["para"] for c in buzon} == {"coord.acad@sena.edu.co", "nuevo@sena.edu.co"}  # sólo su coordinador
    r = client.post("/api/auth/login", json={"email": "nuevo@sena.edu.co", "password": "Clave123!"})
    assert r.status_code == 403 and "pendiente" in r.json()["detail"]
    pendientes = client.get("/api/instructores?pendientes=true", headers=escenario["coord"]).json()
    assert [p["email"] for p in pendientes] == ["nuevo@sena.edu.co"] and pendientes[0]["documento"] == "1098111222"
    assert client.get("/api/instructores?pendientes=true", headers=escenario["coord_otra"]).json() == []
    assert client.post(f"/api/instructores/{pendientes[0]['id']}/aprobar", headers=escenario["coord_otra"]).status_code == 403
    buzon.clear()
    assert client.post(f"/api/instructores/{pendientes[0]['id']}/aprobar", headers=escenario["coord"]).status_code == 200
    assert buzon[0]["para"] == "nuevo@sena.edu.co" and "activada" in buzon[0]["asunto"]
    assert client.post("/api/auth/login", json={"email": "nuevo@sena.edu.co", "password": "Clave123!"}).status_code == 200
    # Un registro rechazado se elimina
    client.post("/api/auth/registro", json={**datos, "email": "otro@sena.edu.co"})
    uid = client.get("/api/instructores?pendientes=true", headers=escenario["coord"]).json()[0]["id"]
    assert client.post(f"/api/instructores/{uid}/rechazar", headers=escenario["coord"]).status_code == 200
    assert client.post("/api/auth/login", json={"email": "otro@sena.edu.co", "password": "Clave123!"}).status_code == 401


def test_instructor_y_coordinador_no_acceden_al_estudio_de_mercados(client, escenario):
    for h in (escenario["inst"], escenario["coord"]):
        for url in ("/api/solicitudes", "/api/articulos", "/api/proveedores", "/api/parametros",
                    "/api/reportes/historico"):
            assert client.get(url, headers=h).status_code == 403, url


# --- Flujo completo ------------------------------------------------------------------
def test_flujo_f014_completo(client, admin, escenario, buzon):
    inst, coord = escenario["inst"], escenario["coord"]
    lider = login(client, "lider.agric@sena.edu.co", "Lider123!")
    cat = {c["nombre"]: c for c in client.get(f"/api/entregas/catalogo?lote_id={escenario['lote']}", headers=inst).json()}
    assert cat["Aceite agrícola"]["disponible"] == 10
    # Validaciones de la solicitud
    assert _solicitar(client, inst, escenario, {"Aceite agrícola": 11}).status_code == 409  # más que el saldo
    assert _solicitar(client, inst, escenario, {"Aceite agrícola": 2}, ficha="").status_code == 422  # ficha
    assert _solicitar(client, inst, escenario, {"Aceite agrícola": 2}, tipo_cuentadante="MULTIPLE",
                      nombre_cuentadante="Grupo", integrantes=[{"nombre": "A", "documento": "1"}]).status_code == 422
    r = _solicitar(client, inst, escenario, {"Aceite agrícola": 6, "Azufre mineral": 4})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["estado"] == "ENVIADA" and e["coordinacion"] == "Coordinación Académica"
    assert e["documento_cuentadante"] == "1098765432" and e["valor"] == 6 * 30000 + 4 * 8000
    assert [c["para"] for c in buzon] == ["coord.acad@sena.edu.co"]
    eid = e["id"]
    # Otra coordinación no la ve; el coordinador devuelve y el instructor corrige
    assert client.get(f"/api/entregas/{eid}", headers=escenario["coord_otra"]).status_code == 403
    assert client.post(f"/api/entregas/{eid}/decidir", headers=coord, json={"accion": "DEVOLVER"}).status_code == 422
    r = client.post(f"/api/entregas/{eid}/decidir", headers=coord, json={"accion": "DEVOLVER", "observaciones": "Menos aceite"})
    assert r.json()["estado"] == "DEVUELTA"
    r = client.put(f"/api/entregas/{eid}", headers=inst, json={
        "lote_id": escenario["lote"], "ficha": "2671234", "destino": "FORMACION",
        "items": [{"solicitud_item_id": escenario["items"]["Aceite agrícola"], "cantidad": 5},
                  {"solicitud_item_id": escenario["items"]["Azufre mineral"], "cantidad": 4}]})
    assert r.status_code == 200 and r.json()["estado"] == "ENVIADA", r.text
    # Aprobar exige la firma del coordinador
    assert client.post(f"/api/entregas/{eid}/decidir", headers=coord, json={"accion": "APROBAR"}).status_code == 409
    _firma(client, coord)
    buzon.clear()
    r = client.post(f"/api/entregas/{eid}/decidir", headers=coord, json={"accion": "APROBAR"})
    assert r.status_code == 200 and r.json()["estado"] == "APROBADA" and r.json()["firmada"]
    assert {c["para"] for c in buzon} == {"inst1@sena.edu.co", "lider.agric@sena.edu.co"}
    # La aprobación reserva el material: otra solicitud no puede pasar del saldo
    cat = {c["nombre"]: c for c in client.get(f"/api/entregas/catalogo?lote_id={escenario['lote']}", headers=inst).json()}
    assert cat["Aceite agrícola"]["disponible"] == 5 and "Azufre mineral" not in cat
    r = _solicitar(client, inst, escenario, {"Azufre mineral": 1})  # todo el azufre quedó reservado
    assert r.status_code == 409 and "sólo hay 0" in r.json()["detail"]
    # El PDF del F-014 se genera con la firma
    pdf = client.get(f"/api/entregas/{eid}/f014.pdf", headers=lider)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000
    # El líder entrega (puede entregar menos de lo solicitado)
    det = client.get(f"/api/entregas/{eid}", headers=lider).json()
    ids = {i["nombre"]: i["id"] for i in det["items"]}
    assert client.post(f"/api/entregas/{eid}/entregar", headers=lider, json={"items": [
        {"id": ids["Aceite agrícola"], "cantidad_entregada": 6}]}).status_code == 422  # más que lo solicitado
    buzon.clear()
    r = client.post(f"/api/entregas/{eid}/entregar", headers=lider, json={"items": [
        {"id": ids["Aceite agrícola"], "cantidad_entregada": 5}, {"id": ids["Azufre mineral"], "cantidad_entregada": 3}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "ENTREGADA" and d["valor"] == 5 * 30000 + 3 * 8000
    assert d["fecha_limite_legalizacion"] == sumar_dias_habiles(date.today(), 15).isoformat()
    assert buzon[0]["para"] == "inst1@sena.edu.co" and "legalizar" in buzon[0]["texto"]
    # Inventario del líder: descuenta cantidad y valor; lo no entregado vuelve al saldo
    inv = client.get("/api/entregas/inventario", headers=lider).json()
    filas = {f["nombre"]: f for f in inv["items"]}
    assert filas["Aceite agrícola"]["entregado"] == 5 and filas["Aceite agrícola"]["disponible"] == 5
    assert filas["Azufre mineral"]["entregado"] == 3 and filas["Azufre mineral"]["disponible"] == 1
    assert inv["totales"] == {"valor_recibido": 332000, "valor_entregado": 174000, "valor_disponible": 158000}
    # Legalización: acta + entre 3 y 5 fotos
    foto = ("f.jpg", _imagen("JPEG"), "image/jpeg")
    acta = ("acta.pdf", b"%PDF-1.4 acta", "application/pdf")
    r = client.post(f"/api/entregas/{eid}/legalizar", headers=inst, files=[("acta", acta), ("fotos", foto), ("fotos", foto)])
    assert r.status_code == 422
    r = client.post(f"/api/entregas/{eid}/legalizar", headers=inst,
                    files=[("acta", acta), ("fotos", ("x.pdf", b"%PDF", "application/pdf")), ("fotos", foto), ("fotos", foto)])
    assert r.status_code == 422  # las fotos deben ser imágenes
    r = client.post(f"/api/entregas/{eid}/legalizar", headers=inst, files=[("acta", acta)] + [("fotos", foto)] * 3)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "LEGALIZADA" and len(d["evidencias"]) == 4
    assert [h["estado_nuevo"] for h in d["historial"]] == ["ENVIADA", "DEVUELTA", "ENVIADA", "APROBADA", "ENTREGADA",
                                                          "LEGALIZADA"]
    ev = client.get(f"/api/entregas/{eid}/evidencias/{d['evidencias'][1]['id']}", headers=lider)
    assert ev.status_code == 200 and ev.headers["content-type"] == "image/jpeg"
    # Informes del líder
    r = client.get("/api/entregas/informe?formato=pdf", headers=lider)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r = client.get("/api/entregas/informe?formato=csv", headers=lider)
    lineas = r.content.decode("utf-8-sig").splitlines()
    assert lineas[0].startswith("N° solicitud;Fecha entrega;Instructor") and len(lineas) == 3
    assert "Legalizada" in lineas[1]


def test_reserva_impide_aprobar_sin_saldo(client, escenario):
    inst, coord = escenario["inst"], escenario["coord"]
    _firma(client, coord)
    a = _solicitar(client, inst, escenario, {"Aceite agrícola": 8}).json()["id"]
    b = _solicitar(client, inst, escenario, {"Aceite agrícola": 8}).json()["id"]  # ambas caben por separado
    assert client.post(f"/api/entregas/{a}/decidir", headers=coord, json={"accion": "APROBAR"}).status_code == 200
    r = client.post(f"/api/entregas/{b}/decidir", headers=coord, json={"accion": "APROBAR"})
    assert r.status_code == 409 and "disponible 2" in r.json()["detail"]["errores"][0]


def test_aviso_de_legalizacion_extemporanea(client, escenario, buzon):
    inst, coord = escenario["inst"], escenario["coord"]
    lider = login(client, "lider.agric@sena.edu.co", "Lider123!")
    _firma(client, coord)
    eid = _solicitar(client, inst, escenario, {"Aceite agrícola": 1}).json()["id"]
    client.post(f"/api/entregas/{eid}/decidir", headers=coord, json={"accion": "APROBAR"})
    item = client.get(f"/api/entregas/{eid}", headers=lider).json()["items"][0]["id"]
    client.post(f"/api/entregas/{eid}/entregar", headers=lider, json={"items": [{"id": item, "cantidad_entregada": 1}]})
    limite = date.fromisoformat(client.get(f"/api/entregas/{eid}", headers=inst).json()["fecha_limite_legalizacion"])
    buzon.clear()
    with SessionLocal() as db:
        assert avisar_extemporaneas(db, limite) == 0  # el último día del plazo aún no está vencida
        assert avisar_extemporaneas(db, limite + timedelta(days=1)) == 1
        assert avisar_extemporaneas(db, limite + timedelta(days=3)) == 0  # máximo un aviso por semana
        assert avisar_extemporaneas(db, limite + timedelta(days=8)) == 1
    assert [c["para"] for c in buzon] == ["inst1@sena.edu.co"] * 2
    assert "EXTEMPORÁNEO" in buzon[0]["texto"] and "Realícelo de inmediato" in buzon[0]["texto"]
    with SessionLocal() as db:  # simulamos que ya pasó el plazo para la vista del líder
        from app.models import Entrega
        db.get(Entrega, eid).fecha_limite_legalizacion = date.today() - timedelta(days=1)
        db.commit()
    lista = client.get("/api/entregas?estado=EXTEMPORANEA", headers=lider).json()
    assert [x["id"] for x in lista] == [eid] and lista[0]["avisos_extemporaneo"] == 2


def test_acceso_por_rol(client, admin, escenario):
    inst, coord = escenario["inst"], escenario["coord"]
    eid = _solicitar(client, inst, escenario, {"Aceite agrícola": 1}).json()["id"]
    otro_lider = login(client, "lider.viver@sena.edu.co", "Lider123!")
    assert client.get(f"/api/entregas/{eid}", headers=otro_lider).status_code == 403
    assert client.get(f"/api/entregas/{eid}", headers=admin).status_code == 200
    client.post("/api/usuarios", headers=admin, json={"nombre": "Instructor Dos", "email": "inst2@sena.edu.co",
                                                      "rol": "INSTRUCTOR", "coordinacion_id": escenario["acad"],
                                                      "documento": "55555555", "password": "Clave123!"})
    inst2 = login(client, "inst2@sena.edu.co", "Clave123!")
    assert client.get(f"/api/entregas/{eid}", headers=inst2).status_code == 403
    assert client.get("/api/entregas", headers=inst2).json() == []
    assert client.post(f"/api/entregas/{eid}/decidir", headers=inst, json={"accion": "APROBAR"}).status_code == 403
    # El administrador no gestiona administradores, pero sí coordinadores e instructores de su centro
    assert [u["rol"] for u in client.get("/api/usuarios?rol=COORDINADOR", headers=admin).json()] == ["COORDINADOR"] * 2
