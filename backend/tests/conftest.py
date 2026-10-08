import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["SKIP_INIT_DB"] = "1"
os.environ["FRONTEND_DIST"] = f"{_tmp}/no-dist"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Articulo, Lote  # noqa: E402
from app.seed import seed_base, seed_demo  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_base(db)
        seed_demo(db)
        agric = db.query(Lote).filter_by(abreviatura="Agric").one()
        for i, (cod, nom, und) in enumerate([("12162003", "Aceite agrícola", "L"), ("11101505", "Azufre mineral", "KG"),
                                             ("10191500", "Bacteria Bacillus subtilis", "L"),
                                             ("40141734", "Adaptador dentado 1/2", "UN")]):
            db.add(Articulo(lote_id=agric.id, codigo_unspsc=cod, nombre=nom, unidad=und, descripcion=f"Ficha {i}"))
        db.commit()
    with TestClient(app) as c:
        yield c


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(client):
    return login(client, "admin@sena.edu.co", "Admin123!")


@pytest.fixture()
def manager(client):
    return login(client, "manager@sena.edu.co", "Manager123!")


@pytest.fixture()
def lider(client):
    return login(client, "lider.agric@sena.edu.co", "Lider123!")
