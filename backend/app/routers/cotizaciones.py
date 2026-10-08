"""Cotizaciones de proveedores: un documento PDF por proveedor/lote/vigencia con precios por artículo."""
import io
import json
import uuid
import zipfile
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Articulo, Cotizacion, CotizacionItem, Lote, Proveedor, Solicitud, Usuario, Vigencia
from ..security import operador, solo_admin, usuario_actual
from ..services import excel_export, excel_import
from ..services.common import actividad, centro_de, get_or_404, lote_accesible, lote_del_lider, verificar_centro
from ..services.pricing import param

router = APIRouter(prefix="/cotizaciones", tags=["cotizaciones"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ESTADOS_EDITABLES = ("BORRADOR", "DEVUELTA")


def _verificar_editable(db: Session, vigencia: Vigencia, lote_id: int, user: Usuario) -> None:
    if vigencia.estado != "ABIERTA":
        raise HTTPException(409, "Sólo se pueden cargar o modificar cotizaciones en una vigencia abierta")
    s = db.scalar(select(Solicitud).where(Solicitud.vigencia_id == vigencia.id, Solicitud.lote_id == lote_id))
    if s and s.estado not in ESTADOS_EDITABLES and user.rol == "LIDER":
        raise HTTPException(409, "La solicitud del lote ya fue enviada: las cotizaciones quedan bloqueadas "
                                 "mientras el administrador la revisa")


def _acceso(user: Usuario, c: Cotizacion) -> None:
    if user.rol == "LIDER" and c.lote_id != user.lote_id:
        raise HTTPException(403, "La cotización no pertenece a su lote")
    verificar_centro(user, c.lote.centro_id, "La cotización")


def cotizacion_out(c: Cotizacion, detalle: bool = False) -> dict:
    d = {"id": c.id, "vigencia_id": c.vigencia_id, "lote_id": c.lote_id, "etiqueta": c.etiqueta,
         "proveedor": {"id": c.proveedor.id, "razon_social": c.proveedor.razon_social, "nit": c.proveedor.nit},
         "fecha": c.fecha.isoformat(), "pdf_nombre": c.pdf_nombre, "n_items": len(c.items),
         "total": sum(i.precio for i in c.items)}
    if detalle:
        d["items"] = [{"id": i.id, "articulo_id": i.articulo_id, "precio": i.precio, "excluido": i.excluido,
                       "motivo_exclusion": i.motivo_exclusion} for i in c.items]
    return d


@router.get("")
def listar(vigencia_id: int, lote_id: int | None = None, centro_id: int | None = None, user=Depends(usuario_actual),
           db: Session = Depends(get_db)):
    stmt = (select(Cotizacion).join(Lote).where(Cotizacion.vigencia_id == vigencia_id)
            .order_by(Cotizacion.lote_id, Cotizacion.etiqueta))
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    if user.rol == "LIDER":
        lote_id = lote_del_lider(user)
    if lote_id:
        stmt = stmt.where(Cotizacion.lote_id == lote_id)
    return [cotizacion_out(c) for c in db.scalars(stmt)]


@router.get("/plantilla")
def plantilla(vigencia_id: int, lote_id: int | None = None, cotizacion_id: int | None = None,
              user=Depends(usuario_actual), db: Session = Depends(get_db)):
    lote = lote_accesible(db, user, lote_id)
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    arts = db.scalars(select(Articulo).where(Articulo.lote_id == lote.id, Articulo.activo.is_(True))
                      .order_by(Articulo.nombre)).all()
    valores = {}
    if cotizacion_id:
        c = get_or_404(db, Cotizacion, cotizacion_id, "Cotización")
        _acceso(user, c)
        valores = {i.articulo_id: i.precio for i in c.items}
    data = excel_export.plantilla(
        f"PLANTILLA DE COTIZACIÓN · Lote {lote.numero} {lote.nombre} · Vigencia {vig.codigo}", arts,
        "Precio unitario IVA incluido", valores,
        "Diligencie el precio unitario con IVA incluido (COP) sólo para los artículos que cotiza el proveedor. "
        "Deje en blanco los que no cotiza. No modifique la columna ID.")
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="plantilla_cotizacion_{lote.abreviatura}.xlsx"'})


async def _leer_precios(precios: str | None, archivo_precios: UploadFile | None) -> dict[int, float]:
    if archivo_precios is not None and archivo_precios.filename:
        return excel_import.leer_columnas_id_valor(await archivo_precios.read(), "precio")
    if precios:
        try:
            return {int(k): float(v) for k, v in json.loads(precios).items() if v not in (None, "", 0)}
        except (ValueError, AttributeError):
            raise HTTPException(422, "Formato de precios inválido")
    return {}


async def _guardar_pdf(pdf: UploadFile) -> tuple[str, str]:
    contenido = await pdf.read()
    if len(contenido) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"El PDF supera el máximo de {settings.MAX_UPLOAD_MB} MB")
    if not contenido.startswith(b"%PDF"):
        raise HTTPException(422, "El soporte de la cotización debe ser un archivo PDF")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.pdf"
    (settings.UPLOAD_DIR / nombre).write_bytes(contenido)
    return nombre, (pdf.filename or "cotizacion.pdf")[:200]


def _aplicar_precios(db: Session, c: Cotizacion, precios: dict[int, float]) -> None:
    if not precios:
        raise HTTPException(422, "La cotización debe incluir al menos un precio")
    arts = {a.id: a for a in db.scalars(select(Articulo).where(Articulo.id.in_(precios.keys())))}
    for aid, p in precios.items():
        a = arts.get(aid)
        if not a or a.lote_id != c.lote_id:
            raise HTTPException(422, f"El artículo con ID {aid} no pertenece al lote")
        if not a.activo:
            raise HTTPException(422, f"El artículo «{a.nombre}» está inactivo en el listado maestro")
        if p <= 0:
            raise HTTPException(422, f"Precio inválido para «{a.nombre}»")
    # Máximo de cotizaciones (proveedores) por artículo en la vigencia
    maximo = int(param(db, "max_cotizaciones"))
    otros = dict(db.execute(
        select(CotizacionItem.articulo_id, func.count()).join(Cotizacion)
        .where(Cotizacion.vigencia_id == c.vigencia_id, Cotizacion.id != (c.id or 0),
               CotizacionItem.articulo_id.in_(precios.keys()))
        .group_by(CotizacionItem.articulo_id)).all())
    excedidos = [arts[a].nombre for a in precios if otros.get(a, 0) >= maximo]
    if excedidos:
        raise HTTPException(409, f"Estos artículos ya tienen {maximo} cotizaciones: " + "; ".join(excedidos[:5])
                            + ("…" if len(excedidos) > 5 else ""))
    actuales = {i.articulo_id: i for i in c.items}
    for aid, item in actuales.items():
        if aid not in precios:
            c.items.remove(item)
    for aid, p in precios.items():
        if aid in actuales:
            actuales[aid].precio = round(p, 2)
        else:
            c.items.append(CotizacionItem(articulo_id=aid, precio=round(p, 2)))


@router.post("", status_code=201)
async def crear(proveedor_id: int = Form(...), fecha: date = Form(...), lote_id: int | None = Form(None),
                precios: str | None = Form(None), pdf: UploadFile = File(...),
                archivo_precios: UploadFile | None = File(None),
                user=Depends(operador), db: Session = Depends(get_db)):
    lote_id = lote_accesible(db, user, lote_id).id
    vig = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    if not vig:
        raise HTTPException(409, "No hay una vigencia abierta")
    _verificar_editable(db, vig, lote_id, user)
    prov = get_or_404(db, Proveedor, proveedor_id, "Proveedor")
    if not prov.activo:
        raise HTTPException(409, "El proveedor está inactivo")
    if fecha > date.today():
        raise HTTPException(422, "La fecha de la cotización no puede ser futura")
    if db.scalar(select(Cotizacion).where(Cotizacion.vigencia_id == vig.id, Cotizacion.lote_id == lote_id,
                                          Cotizacion.proveedor_id == proveedor_id)):
        raise HTTPException(409, "Ya existe una cotización de este proveedor para el lote en la vigencia. "
                                 "Edítela en lugar de crear otra.")
    valores = await _leer_precios(precios, archivo_precios)
    n = db.scalar(select(func.count()).select_from(Cotizacion).where(
        Cotizacion.vigencia_id == vig.id, Cotizacion.lote_id == lote_id)) or 0
    usadas = set(db.scalars(select(Cotizacion.etiqueta).where(Cotizacion.vigencia_id == vig.id,
                                                              Cotizacion.lote_id == lote_id)))
    etiqueta = next(f"P{i}" for i in range(n + 1, 100) if f"P{i}" not in usadas)
    c = Cotizacion(vigencia_id=vig.id, lote_id=lote_id, proveedor_id=proveedor_id, etiqueta=etiqueta,
                   fecha=fecha, pdf_path="", pdf_nombre="", cargada_por=user.id)
    db.add(c)
    _aplicar_precios(db, c, valores)
    c.pdf_path, c.pdf_nombre = await _guardar_pdf(pdf)
    actividad(db, user, f"Cargó la cotización {etiqueta} de {prov.razon_social} ({len(valores)} artículos)",
              "/admin/analisis")
    db.commit()
    return cotizacion_out(c, True)


@router.get("/zip")
def descargar_zip(vigencia_id: int, lote_id: int | None = None, centro_id: int | None = None,
                  user=Depends(usuario_actual), db: Session = Depends(get_db)):
    cots = listar(vigencia_id, lote_id, centro_id, user, db)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in cots:
            obj = db.get(Cotizacion, c["id"])
            ruta = settings.UPLOAD_DIR / obj.pdf_path
            if ruta.exists():
                z.write(ruta, f"L{obj.lote_id}_{obj.etiqueta}_{obj.proveedor.razon_social[:40]}.pdf")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="cotizaciones.zip"'})


@router.get("/{cid}")
def detalle(cid: int, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    c = get_or_404(db, Cotizacion, cid, "Cotización")
    _acceso(user, c)
    return cotizacion_out(c, True)


@router.get("/{cid}/pdf")
def ver_pdf(cid: int, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    c = get_or_404(db, Cotizacion, cid, "Cotización")
    _acceso(user, c)
    ruta = settings.UPLOAD_DIR / c.pdf_path
    if not ruta.exists():
        raise HTTPException(404, "El archivo PDF no se encuentra en el servidor")
    return FileResponse(ruta, media_type="application/pdf", filename=c.pdf_nombre, content_disposition_type="inline")


@router.put("/{cid}")
async def editar(cid: int, fecha: date | None = Form(None), precios: str | None = Form(None),
                 pdf: UploadFile | None = File(None), archivo_precios: UploadFile | None = File(None),
                 user=Depends(operador), db: Session = Depends(get_db)):
    c = get_or_404(db, Cotizacion, cid, "Cotización")
    _acceso(user, c)
    _verificar_editable(db, db.get(Vigencia, c.vigencia_id), c.lote_id, user)
    if fecha:
        if fecha > date.today():
            raise HTTPException(422, "La fecha de la cotización no puede ser futura")
        c.fecha = fecha
    if precios is not None or (archivo_precios is not None and archivo_precios.filename):
        _aplicar_precios(db, c, await _leer_precios(precios, archivo_precios))
    if pdf is not None and pdf.filename:
        anterior = c.pdf_path
        c.pdf_path, c.pdf_nombre = await _guardar_pdf(pdf)
        (settings.UPLOAD_DIR / anterior).unlink(missing_ok=True)
    db.commit()
    return cotizacion_out(c, True)


@router.delete("/{cid}")
def eliminar(cid: int, user=Depends(operador), db: Session = Depends(get_db)):
    c = get_or_404(db, Cotizacion, cid, "Cotización")
    _acceso(user, c)
    _verificar_editable(db, db.get(Vigencia, c.vigencia_id), c.lote_id, user)
    ruta = settings.UPLOAD_DIR / c.pdf_path
    actividad(db, user, f"Eliminó la cotización {c.etiqueta} de {c.proveedor.razon_social}")
    db.delete(c)
    db.commit()
    ruta.unlink(missing_ok=True)
    return {"ok": True}


class ExclusionIn(BaseModel):
    excluido: bool
    motivo: str = ""


@router.post("/items/{item_id}/exclusion")
def excluir_item(item_id: int, data: ExclusionIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    """El analista excluye (o reincorpora) un precio atípico del cálculo."""
    item = get_or_404(db, CotizacionItem, item_id, "Precio cotizado")
    verificar_centro(admin, item.cotizacion.lote.centro_id, "La cotización")
    vig = db.get(Vigencia, item.cotizacion.vigencia_id)
    if vig.estado == "CERRADA":
        raise HTTPException(409, "La vigencia está cerrada")
    s = db.scalar(select(Solicitud).where(Solicitud.vigencia_id == vig.id, Solicitud.lote_id == item.cotizacion.lote_id))
    if s and s.estado == "APROBADA":
        raise HTTPException(409, "La solicitud del lote ya fue aprobada: los precios están congelados")
    if data.excluido and not data.motivo.strip():
        raise HTTPException(422, "Indique el motivo de la exclusión (ej. «su valor notoriamente alto»)")
    item.excluido, item.motivo_exclusion = data.excluido, data.motivo.strip() if data.excluido else ""
    db.commit()
    return {"ok": True}
