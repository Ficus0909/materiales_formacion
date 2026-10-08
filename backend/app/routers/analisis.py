"""Análisis de precios por lote y vigencia (equivalente a las hojas L1..L11 del Excel)."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import METODOS_PRECIO, AnalisisPrecio, Articulo, Cotizacion, Lote, Solicitud, Vigencia
from ..security import solo_admin, usuario_actual
from ..services import excel_export
from ..services.common import centro_de, get_or_404, lote_accesible, lotes_en_operacion, verificar_centro
from ..services.pricing import analizar

router = APIRouter(prefix="/analisis", tags=["análisis de precios"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _articulos_lote(db: Session, lote_id: int) -> list[Articulo]:
    return db.scalars(select(Articulo).where(Articulo.lote_id == lote_id, Articulo.activo.is_(True))
                      .order_by(Articulo.nombre)).all()


@router.get("")
def analisis_lote(vigencia_id: int, lote_id: int | None = None, user=Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    lote_id = lote_accesible(db, user, lote_id).id
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    arts = _articulos_lote(db, lote_id)
    res = analizar(db, vig, arts)
    items = [{"articulo": {"id": a.id, "codigo_unspsc": a.codigo_unspsc, "nombre": a.nombre, "unidad": a.unidad},
              **res[a.id].as_dict()} for a in arts]
    soporte = Counter(i["soporte"] for i in items)
    return {"vigencia": vig.codigo, "lote_id": lote_id, "items": items,
            "resumen": {"total": len(items), **soporte,
                        "con_precio": sum(1 for i in items if i["precio_estimado"] is not None)}}


@router.get("/cobertura")
def cobertura(vigencia_id: int, centro_id: int | None = None, user=Depends(usuario_actual),
              db: Session = Depends(get_db)):
    """Cobertura de precios por lote: indicador clave del tablero (verde ≥80 %, amarillo 60-79 %, rojo <60 %).
    Sólo incluye los lotes en operación (con líder asignado)."""
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    stmt = (select(Lote).where(Lote.activo.is_(True), Lote.id.in_(lotes_en_operacion()))
            .order_by(Lote.centro_id, Lote.numero))
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    lotes = db.scalars(stmt).all()
    if user.rol == "LIDER":
        lotes = [l for l in lotes if l.id == user.lote_id]
    out = []
    for l in lotes:
        arts = _articulos_lote(db, l.id)
        res = analizar(db, vig, arts)
        c = Counter(r.soporte for r in res.values())
        total = len(arts)
        con_cot = sum(1 for r in res.values() if r.n_validas > 0)
        out.append({"lote_id": l.id, "numero": l.numero, "lote": l.nombre, "color": l.color, "total": total,
                    "centro_id": l.centro_id, "centro": l.centro.nombre,
                    "con_cotizacion": con_cot, "con_precio": total - c.get("SIN_PRECIO", 0), **c,
                    "porcentaje": round(100 * (total - c.get("SIN_PRECIO", 0)) / total, 1) if total else 0,
                    "porcentaje_cotizado": round(100 * con_cot / total, 1) if total else 0})
    return out


class AjusteIn(BaseModel):
    metodo: str | None = None
    precio_experto: float | None = None
    justificacion: str = ""


@router.put("/{vigencia_id}/{articulo_id}")
def ajustar(vigencia_id: int, articulo_id: int, data: AjusteIn, admin=Depends(solo_admin),
            db: Session = Depends(get_db)):
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    art = get_or_404(db, Articulo, articulo_id, "Artículo")
    verificar_centro(admin, art.lote.centro_id, "El artículo")
    if vig.estado == "CERRADA":
        raise HTTPException(409, "La vigencia está cerrada")
    s = db.scalar(select(Solicitud).where(Solicitud.vigencia_id == vig.id, Solicitud.lote_id == art.lote_id))
    if s and s.estado == "APROBADA":
        raise HTTPException(409, "La solicitud del lote ya fue aprobada: los precios están congelados")
    if data.metodo and data.metodo not in METODOS_PRECIO:
        raise HTTPException(422, "Método inválido")
    if data.metodo == "EXPERTO" and not (data.precio_experto and data.precio_experto > 0):
        raise HTTPException(422, "Indique el precio de experto")
    if data.metodo and not data.justificacion.strip():
        raise HTTPException(422, "Toda decisión manual sobre el método debe justificarse")
    a = db.scalar(select(AnalisisPrecio).where(AnalisisPrecio.vigencia_id == vig.id,
                                               AnalisisPrecio.articulo_id == articulo_id))
    if not a:
        a = AnalisisPrecio(vigencia_id=vig.id, articulo_id=articulo_id)
        db.add(a)
    a.metodo, a.precio_experto = data.metodo, data.precio_experto
    a.justificacion, a.actualizado_por = data.justificacion.strip(), admin.id
    db.commit()
    return analizar(db, vig, [art])[art.id].as_dict()


@router.get("/exportar")
def exportar(vigencia_id: int, lote_id: int | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    lote = lote_accesible(db, user, lote_id)
    lote_id = lote.id
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    arts = _articulos_lote(db, lote_id)
    res = analizar(db, vig, arts)
    etiquetas = [(c.etiqueta, f"{c.proveedor.razon_social} (NIT {c.proveedor.nit})") for c in db.scalars(
        select(Cotizacion).where(Cotizacion.vigencia_id == vig.id, Cotizacion.lote_id == lote_id)
        .order_by(Cotizacion.etiqueta))]
    data = excel_export.analisis_precios(vig, lote, arts, res, etiquetas)
    return Response(data, media_type=XLSX, headers={
        "Content-Disposition": f'attachment; filename="analisis_precios_L{lote.numero}_{lote.abreviatura}_{vig.codigo}.xlsx"'})
