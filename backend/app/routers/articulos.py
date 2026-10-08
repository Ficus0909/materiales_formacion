"""Listado maestro de artículos (fichas técnicas), importación desde Excel y propuestas de artículos nuevos.
Cada centro de formación tiene su propio listado maestro: el administrador sólo ve y edita el de su centro."""
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import (
    Articulo, Cotizacion, CotizacionItem, Lote, PrecioHistorico, PropuestaArticulo, Proveedor, SolicitudItem,
    Usuario, Vigencia,
)
from ..security import solo_admin, solo_lider, usuario_actual
from ..services import excel_export, excel_import
from ..services.common import (
    actividad, centro_de, get_or_404, lote_del_lider, notificar, notificar_admins, verificar_centro,
)

router = APIRouter(tags=["listado maestro"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def articulo_out(a: Articulo) -> dict:
    return {"id": a.id, "lote_id": a.lote_id, "lote": a.lote.nombre, "lote_abrev": a.lote.abreviatura,
            "codigo_unspsc": a.codigo_unspsc, "nombre": a.nombre, "unidad": a.unidad,
            "descripcion": a.descripcion, "activo": a.activo}


def _filtrar(user: Usuario, q: str, lote_id: int | None, activo: str, centro_id: int | None = None):
    activo = None if activo in ("", "todos") else activo.lower() == "true"
    stmt = (select(Articulo).join(Lote).options(joinedload(Articulo.lote))
            .order_by(Lote.centro_id, Articulo.lote_id, Articulo.nombre))
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    if user.rol == "LIDER":
        lote_id = lote_del_lider(user)
    if lote_id:
        stmt = stmt.where(Articulo.lote_id == lote_id)
    if activo is not None:
        stmt = stmt.where(Articulo.activo.is_(activo))
    if q:
        for palabra in q.split():
            stmt = stmt.where(Articulo.nombre.ilike(f"%{palabra}%") | Articulo.codigo_unspsc.like(f"{palabra}%"))
    return stmt


@router.get("/articulos")
def listar(q: str = "", lote_id: int | None = None, activo: str = "true", pagina: int = 1, por_pagina: int = 50,
           centro_id: int | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    stmt = _filtrar(user, q, lote_id, activo, centro_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    por_pagina = min(max(por_pagina, 1), 2000)
    items = db.scalars(stmt.offset((max(pagina, 1) - 1) * por_pagina).limit(por_pagina)).all()
    ids = [a.id for a in items]
    n_cot = dict(db.execute(select(CotizacionItem.articulo_id, func.count()).where(
        CotizacionItem.articulo_id.in_(ids)).group_by(CotizacionItem.articulo_id)).all()) if ids else {}
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina,
            "items": [{**articulo_out(a), "cotizaciones": n_cot.get(a.id, 0)} for a in items]}


@router.get("/articulos/exportar")
def exportar(q: str = "", lote_id: int | None = None, activo: str = "true", centro_id: int | None = None,
             user=Depends(usuario_actual), db: Session = Depends(get_db)):
    arts = db.scalars(_filtrar(user, q, lote_id, activo, centro_id)).all()
    data = excel_export.listado_maestro(arts, "LISTADO MAESTRO DE FICHAS TÉCNICAS")
    return Response(data, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="listado_maestro.xlsx"'})


@router.get("/articulos/{aid}")
def detalle(aid: int, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    a = get_or_404(db, Articulo, aid, "Artículo")
    if user.rol == "LIDER" and a.lote_id != user.lote_id:
        raise HTTPException(403, "El artículo no pertenece a su lote")
    verificar_centro(user, a.lote.centro_id, "El artículo")
    hist = db.scalars(select(PrecioHistorico).where(PrecioHistorico.articulo_id == aid)
                      .order_by(PrecioHistorico.anio.desc())).all()
    cots = db.execute(select(CotizacionItem, Cotizacion, Proveedor.razon_social, Vigencia.codigo)
                      .join(Cotizacion, CotizacionItem.cotizacion_id == Cotizacion.id)
                      .join(Proveedor).join(Vigencia, Cotizacion.vigencia_id == Vigencia.id)
                      .where(CotizacionItem.articulo_id == aid).order_by(Cotizacion.fecha.desc())).all()
    return {**articulo_out(a),
            "historicos": [{"anio": h.anio, "precio": h.precio, "fuente": h.fuente} for h in hist],
            "cotizaciones": [{"vigencia": v, "proveedor": p, "etiqueta": c.etiqueta, "fecha": c.fecha.isoformat(),
                              "precio": i.precio, "excluido": i.excluido} for i, c, p, v in cots]}


class ArticuloIn(BaseModel):
    lote_id: int
    codigo_unspsc: str
    nombre: str
    unidad: str
    descripcion: str = ""
    activo: bool = True


def _validar(db: Session, data: ArticuloIn, admin: Usuario, aid: int | None = None) -> None:
    verificar_centro(admin, get_or_404(db, Lote, data.lote_id, "Lote").centro_id, "El lote")
    if not re.fullmatch(r"\d{8}", data.codigo_unspsc.strip()):
        raise HTTPException(422, "El código UNSPSC debe tener 8 dígitos (clasificador de SECOP II)")
    if not data.nombre.strip() or not data.unidad.strip():
        raise HTTPException(422, "Nombre y unidad de medida son obligatorios")
    dup = db.scalars(select(Articulo).where(Articulo.lote_id == data.lote_id, Articulo.id != (aid or 0))).all()
    if any(excel_import.normalizar(a.nombre) == excel_import.normalizar(data.nombre) for a in dup):
        raise HTTPException(409, "Ya existe un artículo con ese nombre en el lote")


@router.post("/articulos", status_code=201)
def crear(data: ArticuloIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    _validar(db, data, admin)
    a = Articulo(lote_id=data.lote_id, codigo_unspsc=data.codigo_unspsc.strip(), nombre=data.nombre.strip(),
                 unidad=excel_import.limpiar_unidad(data.unidad), descripcion=data.descripcion.strip(), activo=data.activo)
    db.add(a)
    actividad(db, admin, f"Creó el artículo {a.nombre}")
    db.commit()
    db.refresh(a)
    return articulo_out(a)


@router.put("/articulos/{aid}")
def editar(aid: int, data: ArticuloIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    a = get_or_404(db, Articulo, aid, "Artículo")
    verificar_centro(admin, a.lote.centro_id, "El artículo")
    _validar(db, data, admin, aid)
    if data.lote_id != a.lote_id and db.scalar(select(func.count()).select_from(CotizacionItem)
                                               .where(CotizacionItem.articulo_id == aid)):
        raise HTTPException(409, "No se puede cambiar de lote un artículo que ya tiene cotizaciones")
    a.lote_id, a.codigo_unspsc, a.nombre = data.lote_id, data.codigo_unspsc.strip(), data.nombre.strip()
    a.unidad, a.descripcion, a.activo = excel_import.limpiar_unidad(data.unidad), data.descripcion.strip(), data.activo
    db.commit()
    db.refresh(a)
    return articulo_out(a)


@router.delete("/articulos/{aid}")
def eliminar(aid: int, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    a = get_or_404(db, Articulo, aid, "Artículo")
    verificar_centro(admin, a.lote.centro_id, "El artículo")
    usado = db.scalar(select(func.count()).select_from(CotizacionItem).where(CotizacionItem.articulo_id == aid)) or \
        db.scalar(select(func.count()).select_from(SolicitudItem).where(SolicitudItem.articulo_id == aid))
    if usado:
        a.activo = False
        db.commit()
        return {"ok": True, "desactivado": True,
                "mensaje": "El artículo tiene cotizaciones o solicitudes: se desactivó en lugar de eliminarse"}
    db.query(PrecioHistorico).filter(PrecioHistorico.articulo_id == aid).delete()
    db.delete(a)
    db.commit()
    return {"ok": True, "desactivado": False}


# --- Importación desde Excel --------------------------------------------
@router.post("/articulos/importar/hojas")
async def hojas(archivo: UploadFile = File(...), _=Depends(solo_admin)):
    wb = excel_import.abrir_libro(await archivo.read())
    return {"hojas": excel_import.hojas_listado(wb)}


@router.post("/articulos/importar")
async def importar(archivo: UploadFile = File(...), hoja: str = Form(...), confirmar: bool = Form(False),
                   desactivar_ausentes: bool = Form(False), admin=Depends(solo_admin), db: Session = Depends(get_db)):
    """Sin `confirmar` devuelve la previsualización; con `confirmar=true` aplica los cambios."""
    wb = excel_import.abrir_libro(await archivo.read())
    filas = excel_import.leer_listado(wb, hoja)
    prev = excel_import.previsualizar_listado(db, filas, desactivar_ausentes, admin.centro_id)
    if not confirmar:
        return prev
    resumen = excel_import.aplicar_listado(db, prev)
    actividad(db, admin, f"Importó el listado maestro desde '{archivo.filename}' hoja {hoja}: "
                         f"{resumen['nuevos']} nuevos, {resumen['actualizados']} actualizados")
    db.commit()
    return {"aplicado": True, "resumen": resumen}


@router.post("/articulos/importar-historicos")
async def importar_historicos(archivo: UploadFile = File(...), anio: int = Form(...),
                              admin=Depends(solo_admin), db: Session = Depends(get_db)):
    wb = excel_import.abrir_libro(await archivo.read())
    n = excel_import.importar_historicos_estudio(db, wb, anio, f"Estudio de mercados {anio} ({archivo.filename})",
                                                 admin.centro_id)
    actividad(db, admin, f"Importó {n} precios históricos {anio}")
    db.commit()
    return {"importados": n}


# --- Propuestas de artículos nuevos -------------------------------------
class PropuestaIn(BaseModel):
    nombre: str
    unidad: str
    descripcion: str
    justificacion: str = ""


class RespuestaPropuesta(BaseModel):
    aprobar: bool
    respuesta: str = ""
    codigo_unspsc: str = ""
    nombre: str | None = None
    unidad: str | None = None
    descripcion: str | None = None


def propuesta_out(p: PropuestaArticulo) -> dict:
    return {"id": p.id, "lote": p.lote.nombre, "lote_id": p.lote_id, "lider": p.lider.nombre, "nombre": p.nombre,
            "unidad": p.unidad, "descripcion": p.descripcion, "justificacion": p.justificacion, "estado": p.estado,
            "respuesta": p.respuesta, "articulo_id": p.articulo_id, "creado": p.creado.isoformat() if p.creado else None}


@router.get("/propuestas")
def listar_propuestas(estado: str = "", centro_id: int | None = None, user=Depends(usuario_actual),
                      db: Session = Depends(get_db)):
    stmt = select(PropuestaArticulo).join(Lote).order_by(PropuestaArticulo.creado.desc())
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    if user.rol == "LIDER":
        stmt = stmt.where(PropuestaArticulo.lote_id == user.lote_id)
    if estado:
        stmt = stmt.where(PropuestaArticulo.estado == estado)
    return [propuesta_out(p) for p in db.scalars(stmt)]


@router.post("/propuestas", status_code=201)
def proponer(data: PropuestaIn, lider=Depends(solo_lider), db: Session = Depends(get_db)):
    if not data.nombre.strip() or not data.descripcion.strip() or not data.unidad.strip():
        raise HTTPException(422, "Nombre, unidad y ficha técnica son obligatorios")
    p = PropuestaArticulo(lote_id=lote_del_lider(lider), lider_id=lider.id, nombre=data.nombre.strip(),
                          unidad=excel_import.limpiar_unidad(data.unidad), descripcion=data.descripcion.strip(),
                          justificacion=data.justificacion.strip())
    db.add(p)
    notificar_admins(db, lider.centro_id, "Nueva propuesta de artículo", f"{lider.nombre} propone: {p.nombre}", "/admin/propuestas")
    actividad(db, lider, f"Propuso el artículo nuevo «{p.nombre}»", "/admin/propuestas")
    db.commit()
    db.refresh(p)
    return propuesta_out(p)


@router.post("/propuestas/{pid}/responder")
def responder(pid: int, data: RespuestaPropuesta, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    p = get_or_404(db, PropuestaArticulo, pid, "Propuesta")
    verificar_centro(admin, p.lote.centro_id, "La propuesta")
    if p.estado != "PENDIENTE":
        raise HTTPException(409, "La propuesta ya fue respondida")
    if data.aprobar:
        art_in = ArticuloIn(lote_id=p.lote_id, codigo_unspsc=data.codigo_unspsc, nombre=data.nombre or p.nombre,
                            unidad=data.unidad or p.unidad, descripcion=data.descripcion or p.descripcion)
        _validar(db, art_in, admin)
        a = Articulo(**art_in.model_dump())
        db.add(a)
        db.flush()
        p.articulo_id, p.estado = a.id, "APROBADA"
    else:
        if not data.respuesta.strip():
            raise HTTPException(422, "Indique el motivo del rechazo")
        p.estado = "RECHAZADA"
    p.respuesta = data.respuesta.strip()
    notificar(db, [p.lider_id], f"Propuesta {'aprobada' if data.aprobar else 'rechazada'}: {p.nombre}",
              p.respuesta, "/lider/mi-lote")
    db.commit()
    return propuesta_out(p)
