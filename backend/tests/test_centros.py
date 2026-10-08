"""Centros de formación: jerarquía manager → administrador → líder y aislamiento de datos entre centros."""
import io
import json

import pytest
from openpyxl import Workbook

from .conftest import PDF, login


@pytest.fixture()
def centro_b(client, manager):
    """Segundo centro con su administrador, un lote, un líder y un artículo (creados por la jerarquía real)."""
    c = client.post("/api/centros", headers=manager, json={"codigo": "CAGRO", "nombre": "Centro Agroturístico",
                                                           "regional": "Santander", "cargar_listado": False})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    r = client.post("/api/usuarios", headers=manager, json={"nombre": "Admin B", "email": "admin.b@sena.edu.co",
                                                            "rol": "ADMIN", "centro_id": cid, "password": "Clave123!"})
    assert r.status_code == 201, r.text
    admin_b = login(client, "admin.b@sena.edu.co", "Clave123!")
    # El mismo número y abreviatura de un lote del centro A son válidos en otro centro
    assert client.post("/api/lotes", headers=admin_b, json={"numero": 1, "nombre": "Agrícola B",
                                                            "abreviatura": "Agric"}).status_code == 201
    lote = client.get("/api/lotes", headers=admin_b).json()[0]
    r = client.post("/api/usuarios", headers=admin_b, json={"nombre": "Líder B", "email": "lider.b@sena.edu.co",
                                                            "rol": "LIDER", "lote_id": lote["id"], "password": "Clave123!"})
    assert r.status_code == 201, r.text
    art = client.post("/api/articulos", headers=admin_b, json={"lote_id": lote["id"], "codigo_unspsc": "12162003",
                                                               "nombre": "Aceite agrícola", "unidad": "L"})
    assert art.status_code == 201, art.text
    return {"id": cid, "admin": admin_b, "lider": login(client, "lider.b@sena.edu.co", "Clave123!"),
            "lote": lote["id"], "articulo": art.json()["id"]}


def test_jerarquia_de_usuarios(client, admin, manager, centro_b):
    centro_a = client.get("/api/centros", headers=admin).json()
    assert len(centro_a) == 1 and centro_a[0]["codigo"] == "CASA"
    lote_a = client.get("/api/lotes", headers=admin).json()[0]["id"]
    # El administrador no crea administradores ni managers
    for rol in ("ADMIN", "MANAGER"):
        r = client.post("/api/usuarios", headers=admin, json={"nombre": "X", "email": f"x.{rol}@sena.edu.co",
                                                              "rol": rol, "password": "Clave123!"})
        assert r.status_code == 403
    # El administrador crea líderes sólo en su centro, aunque envíe otro centro_id
    r = client.post("/api/usuarios", headers=admin, json={"nombre": "L", "email": "l@sena.edu.co", "rol": "LIDER",
                                                          "centro_id": centro_b["id"], "lote_id": lote_a,
                                                          "password": "Clave123!"})
    assert r.status_code == 201 and r.json()["centro_id"] == centro_a[0]["id"]
    # ...y con un lote de su centro
    r = client.post("/api/usuarios", headers=admin, json={"nombre": "L2", "email": "l2@sena.edu.co", "rol": "LIDER",
                                                          "lote_id": centro_b["lote"], "password": "Clave123!"})
    assert r.status_code == 422
    # Cada administrador lista sólo los usuarios de su centro; el manager ve todos
    emails_a = {u["email"] for u in client.get("/api/usuarios", headers=admin).json()}
    assert "lider.b@sena.edu.co" not in emails_a and "manager@sena.edu.co" not in emails_a
    emails_b = {u["email"] for u in client.get("/api/usuarios", headers=centro_b["admin"]).json()}
    assert emails_b == {"admin.b@sena.edu.co", "lider.b@sena.edu.co"}
    todos = {u["email"] for u in client.get("/api/usuarios", headers=manager).json()}
    assert {"lider.b@sena.edu.co", "admin@sena.edu.co", "manager@sena.edu.co"} <= todos
    # El administrador no edita ni elimina a otros administradores ni a usuarios de otro centro
    uid_admin_b = next(u["id"] for u in client.get("/api/usuarios", headers=manager).json()
                       if u["email"] == "admin.b@sena.edu.co")
    uid_lider_b = next(u["id"] for u in client.get("/api/usuarios", headers=manager).json()
                       if u["email"] == "lider.b@sena.edu.co")
    assert client.delete(f"/api/usuarios/{uid_admin_b}", headers=admin).status_code == 403
    assert client.delete(f"/api/usuarios/{uid_lider_b}", headers=admin).status_code == 403
    assert client.put(f"/api/usuarios/{uid_lider_b}", headers=admin, json={
        "nombre": "Hack", "email": "lider.b@sena.edu.co", "rol": "LIDER", "lote_id": lote_a}).status_code == 403
    # Los líderes y administradores deben tener centro
    assert client.post("/api/usuarios", headers=manager, json={"nombre": "Y", "email": "y@sena.edu.co", "rol": "ADMIN",
                                                               "password": "Clave123!"}).status_code == 422


def test_aislamiento_de_datos(client, admin, lider, centro_b):
    # Listado maestro
    nombres_b = [a["nombre"] for a in client.get("/api/articulos", headers=centro_b["admin"]).json()["items"]]
    assert nombres_b == ["Aceite agrícola"]
    ids_a = {a["id"] for a in client.get("/api/articulos", headers=admin).json()["items"]}
    assert centro_b["articulo"] not in ids_a
    assert client.get(f"/api/articulos/{centro_b['articulo']}", headers=admin).status_code == 403
    assert client.delete(f"/api/articulos/{centro_b['articulo']}", headers=admin).status_code == 403
    # Lotes de otro centro: no se pueden editar ni analizar
    assert client.put(f"/api/lotes/{centro_b['lote']}", headers=admin, json={
        "numero": 9, "nombre": "x", "abreviatura": "x"}).status_code == 403
    vig = client.get("/api/vigencias/activa", headers=admin).json()["id"]
    assert client.get(f"/api/analisis?vigencia_id={vig}&lote_id={centro_b['lote']}", headers=admin).status_code == 403
    # El administrador no carga cotizaciones en lotes de otro centro
    prov = client.get("/api/proveedores", headers=admin).json()[0]["id"]
    r = client.post("/api/cotizaciones", headers=admin, data={
        "proveedor_id": prov, "fecha": "2026-09-10", "lote_id": centro_b["lote"],
        "precios": json.dumps({centro_b["articulo"]: 1000})}, files={"pdf": ("c.pdf", PDF, "application/pdf")})
    assert r.status_code == 403
    # El mismo proveedor (compartido) cotiza en ambos centros: el máximo por artículo es por centro
    r = client.post("/api/cotizaciones", headers=centro_b["lider"], data={
        "proveedor_id": prov, "fecha": "2026-09-10", "precios": json.dumps({centro_b["articulo"]: 1000})},
        files={"pdf": ("c.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.get(f"/api/cotizaciones/{cid}", headers=admin).status_code == 403
    assert client.get(f"/api/cotizaciones?vigencia_id={vig}", headers=admin).json() == []
    # Solicitudes: el administrador A no ve ni decide las del centro B
    sid = client.get("/api/solicitudes/mia", headers=centro_b["lider"]).json()["solicitud"]["id"]
    assert client.get(f"/api/solicitudes/{sid}", headers=admin).status_code == 403
    assert all(s["id"] != sid for s in client.get(f"/api/solicitudes?vigencia_id={vig}", headers=admin).json())
    client.put(f"/api/solicitudes/{sid}/items", headers=centro_b["lider"],
               json=[{"articulo_id": centro_b["articulo"], "cantidad": 2}])
    assert client.post(f"/api/solicitudes/{sid}/enviar", headers=centro_b["lider"]).status_code == 200
    assert client.post(f"/api/solicitudes/{sid}/decidir", headers=admin,
                       json={"accion": "APROBAR"}).status_code == 403
    r = client.post(f"/api/solicitudes/{sid}/decidir", headers=centro_b["admin"], json={"accion": "APROBAR"})
    assert r.status_code == 200 and r.json()["estado"] == "APROBADA"
    # El líder del centro A no ve el artículo del centro B aunque el lote tenga la misma abreviatura
    assert client.get(f"/api/articulos/{centro_b['articulo']}", headers=lider).status_code == 403


def test_notificaciones_van_al_admin_del_centro(client, admin, centro_b):
    client.post("/api/propuestas", headers=centro_b["lider"], json={"nombre": "Semilla", "unidad": "KG",
                                                                    "descripcion": "Certificada"})
    assert client.get("/api/notificaciones", headers=centro_b["admin"]).json()["no_leidas"] == 1
    assert client.get("/api/notificaciones", headers=admin).json()["no_leidas"] == 0
    p = client.get("/api/propuestas", headers=centro_b["admin"]).json()
    assert len(p) == 1 and client.get("/api/propuestas", headers=admin).json() == []
    assert client.post(f"/api/propuestas/{p[0]['id']}/responder", headers=admin,
                       json={"aprobar": False, "respuesta": "No"}).status_code == 403


def test_manager_supervisa(client, admin, manager, centro_b):
    d = client.get("/api/dashboard/manager", headers=manager).json()
    assert {c["codigo"] for c in d["centros"]} == {"CASA", "CAGRO"}
    assert d["kpis"]["centros"] == 2
    assert client.get("/api/dashboard/manager", headers=admin).status_code == 403
    # El manager consulta un centro concreto o todos
    assert client.get(f"/api/dashboard/admin?centro_id={centro_b['id']}", headers=manager).json()["kpis"]["articulos"] == 1
    assert client.get("/api/dashboard/admin", headers=manager).json()["kpis"]["articulos"] == 5
    assert client.get("/api/dashboard/admin", headers=admin).json()["kpis"]["articulos"] == 4
    # pero no opera dentro de los centros
    assert client.post("/api/lotes", headers=manager, json={"numero": 5, "nombre": "x", "abreviatura": "x"}).status_code == 403
    sid = client.get("/api/solicitudes/mia", headers=centro_b["lider"]).json()["solicitud"]["id"]
    assert client.get(f"/api/solicitudes/{sid}", headers=manager).status_code == 200
    assert client.post(f"/api/solicitudes/{sid}/revisar", headers=manager).status_code == 403
    # Configuración común: sólo el manager
    assert client.put("/api/parametros", headers=admin, json={"min_cotizaciones": "3"}).status_code == 403
    assert client.put("/api/parametros", headers=manager, json={"min_cotizaciones": "3"}).status_code == 200
    vig = client.get("/api/vigencias/activa", headers=manager).json()["id"]
    r = client.get(f"/api/solicitudes/consolidado/exportar?vigencia_id={vig}", headers=manager)
    assert r.status_code == 200


def test_centro_inactivo_bloquea_el_ingreso(client, manager, centro_b):
    lider_b = centro_b["lider"]
    assert client.put(f"/api/centros/{centro_b['id']}", headers=manager, json={
        "codigo": "CAGRO", "nombre": "Centro Agroturístico", "activo": False}).status_code == 200
    assert client.get("/api/auth/me", headers=lider_b).status_code == 401
    r = client.post("/api/auth/login", json={"email": "lider.b@sena.edu.co", "password": "Clave123!"})
    assert r.status_code == 403
    # No se crean usuarios en un centro inactivo; un centro con datos no se elimina
    assert client.post("/api/usuarios", headers=manager, json={"nombre": "Z", "email": "z@sena.edu.co", "rol": "ADMIN",
                                                               "centro_id": centro_b["id"],
                                                               "password": "Clave123!"}).status_code == 409
    assert client.delete(f"/api/centros/{centro_b['id']}", headers=manager).status_code == 409


def test_centros_unicos_y_solo_manager(client, admin, manager):
    assert client.post("/api/centros", headers=admin, json={"codigo": "X", "nombre": "X"}).status_code == 403
    assert client.post("/api/centros", headers=manager, json={"codigo": "casa", "nombre": "Otro"}).status_code == 409
    c = client.post("/api/centros", headers=manager, json={"codigo": "VACIO", "nombre": "Centro vacío",
                                                           "cargar_listado": False}).json()
    assert c["lotes"] == 0 and c["listado_copiado"] is None
    assert client.delete(f"/api/centros/{c['id']}", headers=manager).status_code == 200


def test_importacion_usa_los_lotes_del_centro(client, admin, centro_b):
    """El archivo usa la abreviatura 'Agric', que existe en ambos centros: cada importación va a su centro."""
    wb = Workbook()
    ws = wb.active
    ws.title = "LM-2027"
    ws.append(["N.", "Lote", "Código UNSPSC", "Producto", "Unidad", "Descripción"])
    ws.append([1, "Agric", "10171702", "Yodo agrícola", "GAR", "Yodo"])
    buf = io.BytesIO()
    wb.save(buf)
    r = client.post("/api/articulos/importar", headers=centro_b["admin"], data={"hoja": "LM-2027", "confirmar": "true"},
                    files={"archivo": ("lm.xlsx", buf.getvalue())})
    assert r.json()["resumen"]["nuevos"] == 1
    nombres_b = {a["nombre"] for a in client.get("/api/articulos", headers=centro_b["admin"]).json()["items"]}
    nombres_a = {a["nombre"] for a in client.get("/api/articulos", headers=admin).json()["items"]}
    assert "Yodo agrícola" in nombres_b and "Yodo agrícola" not in nombres_a


def test_centro_nuevo_recibe_el_listado_maestro_predeterminado(client, admin, manager):
    """Sin indicar nada, el centro nuevo recibe los lotes y artículos activos del centro por defecto (CASA)."""
    casa = client.get("/api/centros", headers=admin).json()[0]
    aid = client.get("/api/articulos", headers=admin).json()["items"][0]["id"]
    client.delete(f"/api/articulos/{aid}", headers=admin)  # un artículo retirado no se copia
    r = client.post("/api/centros", headers=manager, json={"codigo": "NUEVO", "nombre": "Centro nuevo"})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["listado_copiado"] == {"lotes": casa["lotes"], "articulos": 3, "origen": casa["nombre"]}
    assert c["lotes"] == casa["lotes"] and c["articulos"] == 3
    # Es una copia independiente: el administrador del centro nuevo la ve y la edita sin tocar la de CASA
    client.post("/api/usuarios", headers=manager, json={"nombre": "Admin N", "email": "admin.n@sena.edu.co", "rol": "ADMIN",
                                                        "centro_id": c["id"], "password": "Clave123!"})
    admin_n = login(client, "admin.n@sena.edu.co", "Clave123!")
    arts_n = client.get("/api/articulos", headers=admin_n).json()["items"]
    ids_casa = {a["id"] for a in client.get("/api/articulos?activo=todos", headers=admin).json()["items"]}
    assert len(arts_n) == 3 and not ids_casa & {a["id"] for a in arts_n}
    assert client.delete(f"/api/articulos/{arts_n[0]['id']}", headers=admin_n).json()["ok"]
    assert client.get("/api/articulos", headers=admin).json()["total"] == 3
    # Se puede elegir el centro de origen o empezar sin listado
    otro = client.post("/api/centros", headers=manager, json={"codigo": "OTRO", "nombre": "Otro centro",
                                                              "listado_desde": c["id"]}).json()
    assert otro["listado_copiado"]["articulos"] == 2


def test_cargar_listado_en_centro_existente(client, admin, manager):
    vacio = client.post("/api/centros", headers=manager, json={"codigo": "VAC", "nombre": "Centro sin listado",
                                                               "cargar_listado": False}).json()
    url = f"/api/centros/{vacio['id']}/cargar-listado"
    assert client.post(url, headers=admin, json={}).status_code == 403  # sólo el manager
    assert client.post(url, headers=manager, json={"listado_desde": vacio["id"]}).status_code == 422  # de sí mismo
    r = client.post(url, headers=manager, json={})  # por defecto: el del centro CASA
    assert r.status_code == 200, r.text
    assert r.json()["listado_copiado"]["articulos"] == 4 and r.json()["lotes"] == 11
    # Con lotes ya no se vuelve a cargar (evita duplicar el catálogo)
    assert client.post(url, headers=manager, json={}).status_code == 409
    # Un origen sin artículos no deja el centro a medias
    otro = client.post("/api/centros", headers=manager, json={"codigo": "OTRO2", "nombre": "Otro vacío",
                                                              "cargar_listado": False}).json()
    nuevo = client.post("/api/centros", headers=manager, json={"codigo": "N3", "nombre": "Destino",
                                                               "cargar_listado": False}).json()
    r = client.post(f"/api/centros/{nuevo['id']}/cargar-listado", headers=manager, json={"listado_desde": otro["id"]})
    assert r.status_code == 422
    destino = next(c for c in client.get("/api/centros", headers=manager).json() if c["id"] == nuevo["id"])
    assert destino["lotes"] == 0


def test_dashboard_solo_muestra_lotes_con_lider(client, manager):
    """Una sede con el listado copiado no muestra lotes hasta que el administrador les asigna un líder."""
    c = client.post("/api/centros", headers=manager, json={"codigo": "SEDE", "nombre": "Sede nueva"}).json()
    assert c["lotes"] == 11
    client.post("/api/usuarios", headers=manager, json={"nombre": "Admin S", "email": "admin.s@sena.edu.co", "rol": "ADMIN",
                                                        "centro_id": c["id"], "password": "Clave123!"})
    admin_s = login(client, "admin.s@sena.edu.co", "Clave123!")
    d = client.get("/api/dashboard/admin", headers=admin_s).json()
    assert d["cobertura"] == [] and d["lotes_sin_solicitud"] == []
    sede = next(x for x in client.get("/api/dashboard/manager", headers=manager).json()["centros"] if x["id"] == c["id"])
    assert sede["lotes_operacion"] == 0 and sede["articulos"] == 0
    # Al asignar un líder, ese lote (y sólo ese) entra en operación
    agric = next(l for l in client.get("/api/lotes", headers=admin_s).json() if l["abreviatura"] == "Agric")
    client.post("/api/usuarios", headers=admin_s, json={"nombre": "Líder S", "email": "lider.s@sena.edu.co", "rol": "LIDER",
                                                        "lote_id": agric["id"], "password": "Clave123!"})
    d = client.get("/api/dashboard/admin", headers=admin_s).json()
    assert [x["lote_id"] for x in d["cobertura"]] == [agric["id"]] and d["lotes_sin_solicitud"] == [agric["nombre"]]
    sede = next(x for x in client.get("/api/dashboard/manager", headers=manager).json()["centros"] if x["id"] == c["id"])
    assert sede["lotes_operacion"] == 1 and sede["articulos"] == 4
    # El listado maestro completo sigue disponible para el administrador
    assert client.get("/api/articulos", headers=admin_s).json()["total"] == 4
