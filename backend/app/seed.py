"""Datos iniciales. Uso:  python -m app.seed [--excel RUTA.xlsx] [--hojas LM-2026] [--anio-historico 2026] [--demo]

El listado maestro del Excel se carga en el centro por defecto (CENTRO_CODIGO)."""
import argparse
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine
from .migraciones import migrar_centros
from .models import Articulo, Centro, EstadoPost, IndiceAjuste, Lote, Proveedor, Usuario, Vigencia
from .security import hash_password
from .services import excel_import

LOTES = [
    (1, "Agrícola", "Agric", "#39A909"), (2, "Artesanías", "Artes", "#B5651D"),
    (3, "Carne de Res, Pollo y Huevos", "Carph", "#DC3545"), (4, "Desinfectantes", "Desin", "#17A2B8"),
    (5, "Elementos de Protección Personal y Salud", "Eppss", "#FD7E14"),
    (6, "Insumos de Chocolatería", "Insch", "#6F4E37"),
    (7, "Laboratorio de Fisicoquímica y Microbiología", "Labor", "#5B6EE1"),
    (8, "Menaje, Cajas y Plásticos", "Mecap", "#718096"), (9, "Panadería", "Panad", "#D4A017"),
    (10, "Pecuario", "Pecua", "#007832"), (11, "Víveres", "Viver", "#71277A"),
]
HOJAS_LISTADO = ("LM-2026",)
ESTADOS_POST = [("En Compra", "#71277A"), ("En Camino", "#17A2B8"), ("En el Punto", "#007832")]
# IPC Colombia (DANE) + 2 puntos, tal como lo indica la nota del estudio de mercados 2026
INDICES = [(2023, 0.0928), (2024, 0.052), (2025, 0.051)]


def centro_defecto(db: Session) -> Centro:
    c = db.scalar(select(Centro).where(Centro.codigo == settings.CENTRO_CODIGO)) or db.scalar(
        select(Centro).order_by(Centro.id))
    if not c:
        c = Centro(codigo=settings.CENTRO_CODIGO, nombre=settings.CENTRO_NOMBRE, regional=settings.CENTRO_REGIONAL)
        db.add(c)
        db.flush()
    return c


def seed_base(db: Session) -> None:
    centro = centro_defecto(db)
    if not db.scalar(select(func.count()).select_from(Lote)):
        for n, nombre, abrev, color in LOTES:
            db.add(Lote(centro_id=centro.id, numero=n, nombre=nombre, abreviatura=abrev, color=color))
    if not db.scalar(select(func.count()).select_from(EstadoPost)):
        for i, (nombre, color) in enumerate(ESTADOS_POST, 1):
            db.add(EstadoPost(nombre=nombre, color=color, orden=i))
    for anio, ipc in INDICES:
        if not db.get(IndiceAjuste, anio):
            db.add(IndiceAjuste(anio=anio, ipc=ipc, puntos_adicionales=0.02))
    if not db.scalar(select(Usuario).where(Usuario.rol == "ADMIN")):
        db.add(Usuario(nombre=f"Administrador {centro.codigo}", email=settings.ADMIN_EMAIL, rol="ADMIN",
                       centro_id=centro.id, password_hash=hash_password(settings.ADMIN_PASSWORD),
                       debe_cambiar_password=False))
    if not db.scalar(select(Usuario).where(Usuario.rol == "MANAGER")):
        db.add(Usuario(nombre="Manager de centros", email=settings.MANAGER_EMAIL, rol="MANAGER",
                       password_hash=hash_password(settings.MANAGER_PASSWORD), debe_cambiar_password=False))
    db.commit()


def seed_excel(db: Session, ruta: str, hojas: tuple[str, ...] = HOJAS_LISTADO, anio_hist: int = 2026) -> dict:
    centro = centro_defecto(db)
    wb = excel_import.abrir_libro(Path(ruta).read_bytes())
    filas = [f for h in hojas if h in wb.sheetnames for f in excel_import.leer_listado(wb, h)]
    prev = excel_import.previsualizar_listado(db, filas, False, centro.id)
    resumen = excel_import.aplicar_listado(db, prev)
    db.flush()
    resumen["historicos"] = excel_import.importar_historicos_estudio(db, wb, anio_hist,
                                                                     f"Estudio de mercados {anio_hist}", centro.id)
    db.commit()
    resumen["errores_detalle"] = [(e["fila"], e["nombre"], e["errores"]) for e in prev["errores"]]
    return resumen


def seed_demo(db: Session) -> None:
    """Vigencia abierta, un líder por lote del centro por defecto y algunos proveedores para probar el flujo completo."""
    if not db.scalar(select(Vigencia)):
        db.add(Vigencia(codigo="2026", anio=2026, fecha_inicio=date(2026, 1, 15), fecha_cierre=date(2026, 2, 19),
                        estado="CERRADA"))
        db.add(Vigencia(codigo="2027", anio=2027, fecha_inicio=date(2026, 9, 1), fecha_cierre=date(2026, 11, 30),
                        estado="ABIERTA"))
    centro = centro_defecto(db)
    for l in db.scalars(select(Lote).where(Lote.centro_id == centro.id)):
        email = f"lider.{l.abreviatura.lower()}@sena.edu.co"
        if not db.scalar(select(Usuario).where(Usuario.email == email)):
            db.add(Usuario(nombre=f"Líder {l.nombre}", email=email, rol="LIDER", centro_id=centro.id, lote_id=l.id,
                           password_hash=hash_password("Lider123!"), debe_cambiar_password=False))
    for nit, nombre in [("900123456-1", "Agroinsumos de Santander S.A.S."), ("800987654-2", "Distribuidora El Campo Ltda."),
                        ("901555777-3", "Comercializadora Piedecuesta S.A.S."), ("830111222-4", "Suministros Andinos S.A.")]:
        if not db.scalar(select(Proveedor).where(Proveedor.nit == nit)):
            db.add(Proveedor(nit=nit, razon_social=nombre))
    db.commit()


def crear_esquema() -> None:
    Base.metadata.create_all(engine)
    migrar_centros(engine, settings.CENTRO_CODIGO, settings.CENTRO_NOMBRE, settings.CENTRO_REGIONAL)


def init_db(excel: str = "", demo: bool = False) -> None:
    crear_esquema()
    with SessionLocal() as db:
        seed_base(db)
        if excel and not db.scalar(select(func.count()).select_from(Articulo)):
            print("Importando listado maestro:", seed_excel(db, excel))
        if demo:
            seed_demo(db)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default=settings.SEED_EXCEL)
    ap.add_argument("--hojas", default=",".join(HOJAS_LISTADO), help="Hojas de listado maestro separadas por coma")
    ap.add_argument("--anio-historico", type=int, default=2026)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    crear_esquema()
    with SessionLocal() as db:
        seed_base(db)
        if a.excel:
            print("Importación:", seed_excel(db, a.excel, tuple(a.hojas.split(",")), a.anio_historico))
        if a.demo:
            seed_demo(db)
    print("Listo.")
