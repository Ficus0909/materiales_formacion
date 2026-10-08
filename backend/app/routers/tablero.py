"""Dashboard, reportes y notificaciones."""
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Actividad, Articulo, Centro, Cotizacion, CotizacionItem, Lote, Notificacion, PropuestaArticulo, Solicitud, Usuario,
    Vigencia,
)
from ..security import admin_o_manager, solo_lider, solo_manager, usuario_actual
from ..services.common import centro_de, get_or_404, lote_del_lider, lotes_en_operacion
from ..services.pricing import analizar
from .analisis import cobertura
from .solicitudes import PENDIENTES, estado_visible

router = APIRouter(tags=["tablero"])


def _vigencia_out(v: Vigencia | None):
    return {"id": v.id, "codigo": v.codigo, "fecha_cierre": v.fecha_cierre.isoformat(), "estado": v.estado} if v else None


def _vigencia_vista(db: Session, vigencia_id: int | None) -> Vigencia | None:
    return db.get(Vigencia, vigencia_id) if vigencia_id else db.scalar(
        select(Vigencia).where(Vigencia.estado == "ABIERTA")) or db.scalar(
        select(Vigencia).order_by(Vigencia.fecha_inicio.desc()))


def _solicitudes(db: Session, vig: Vigencia | None, centro: int | None) -> list[Solicitud]:
    if not vig:
        return []
    stmt = select(Solicitud).join(Lote).where(Solicitud.vigencia_id == vig.id)
    return db.scalars(stmt.where(Lote.centro_id == centro) if centro else stmt).all()


@router.get("/dashboard/admin")
def dashboard_admin(vigencia_id: int | None = None, centro_id: int | None = None, user=Depends(admin_o_manager),
                    db: Session = Depends(get_db)):
    """Tablero de un centro (el del administrador, o el que elija el manager; sin centro = todos)."""
    centro = centro_de(user, centro_id)
    vig = _vigencia_vista(db, vigencia_id)
    sols = _solicitudes(db, vig, centro)
    por_estado = Counter(estado_visible(s) for s in sols)

    def del_centro(stmt, col=Lote.centro_id):
        return stmt.where(col == centro) if centro else stmt

    act = db.scalars(del_centro(select(Actividad), Actividad.centro_id).order_by(Actividad.id.desc()).limit(15)).all()
    return {
        "vigencia": _vigencia_out(vig),
        "kpis": {
            "articulos": db.scalar(del_centro(select(func.count()).select_from(Articulo).join(Lote)
                                              .where(Articulo.activo.is_(True)))),
            "pendientes": sum(1 for s in sols if s.estado in PENDIENTES),
            "cotizaciones": db.scalar(del_centro(select(func.count()).select_from(Cotizacion).join(Lote).where(
                Cotizacion.vigencia_id == vig.id))) if vig else 0,
            "precios_cotizados": db.scalar(del_centro(
                select(func.count()).select_from(CotizacionItem).join(Cotizacion).join(Lote).where(
                    Cotizacion.vigencia_id == vig.id))) if vig else 0,
            "lideres": db.scalar(del_centro(select(func.count()).select_from(Usuario).where(
                Usuario.rol == "LIDER", Usuario.activo.is_(True)), Usuario.centro_id)),
            "propuestas": db.scalar(del_centro(select(func.count()).select_from(PropuestaArticulo).join(Lote).where(
                PropuestaArticulo.estado == "PENDIENTE"))),
        },
        "por_estado": [{"estado": k, "cantidad": v} for k, v in por_estado.items()],
        "lotes_sin_solicitud": [l.nombre for l in db.scalars(del_centro(select(Lote).where(
                                    Lote.activo.is_(True), Lote.id.in_(lotes_en_operacion()))))
                                if l.id not in {s.lote_id for s in sols if s.estado != "BORRADOR"}] if vig else [],
        "cobertura": cobertura(vig.id, centro, user, db) if vig else [],
        "actividad": [{"fecha": a.fecha.isoformat(), "accion": a.accion, "enlace": a.enlace,
                       "usuario": a.usuario.nombre if a.usuario else "Sistema"} for a in act],
    }


@router.get("/dashboard/manager")
def dashboard_manager(vigencia_id: int | None = None, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    """Resumen por centro de formación para el manager."""
    vig = _vigencia_vista(db, vigencia_id)
    centros = []
    for c in db.scalars(select(Centro).order_by(Centro.nombre)):
        sols = _solicitudes(db, vig, c.id)
        # La cobertura se mide sobre los lotes en operación (con líder), no sobre todo el listado copiado
        arts = db.scalars(select(Articulo).join(Lote).where(Lote.centro_id == c.id, Articulo.activo.is_(True),
                                                             Lote.activo.is_(True), Lote.id.in_(lotes_en_operacion()))).all()
        con_precio = sum(1 for r in analizar(db, vig, arts).values() if r.precio_estimado is not None) if vig else 0
        usuarios = dict(db.execute(select(Usuario.rol, func.count()).where(
            Usuario.centro_id == c.id, Usuario.activo.is_(True)).group_by(Usuario.rol)).all())
        n_lotes = db.scalar(select(func.count()).select_from(Lote).where(Lote.centro_id == c.id, Lote.activo.is_(True)))
        n_operacion = db.scalar(select(func.count()).select_from(Lote).where(
            Lote.centro_id == c.id, Lote.activo.is_(True), Lote.id.in_(lotes_en_operacion())))
        aprobadas = [s for s in sols if s.estado == "APROBADA"]
        centros.append({
            "id": c.id, "codigo": c.codigo, "nombre": c.nombre, "regional": c.regional, "activo": c.activo,
            "administradores": usuarios.get("ADMIN", 0), "lideres": usuarios.get("LIDER", 0), "lotes": n_lotes,
            "lotes_operacion": n_operacion,
            "articulos": len(arts),
            "cobertura": round(100 * con_precio / len(arts), 1) if arts else 0,
            "enviadas": sum(1 for s in sols if s.estado != "BORRADOR"),
            "pendientes": sum(1 for s in sols if s.estado in PENDIENTES),
            "aprobadas": len(aprobadas),
            "valor_aprobado": round(sum((i.precio_aprobado or 0) * i.cantidad for s in aprobadas for i in s.items), 2),
        })
    act = db.scalars(select(Actividad).order_by(Actividad.id.desc()).limit(15)).all()
    return {
        "vigencia": _vigencia_out(vig),
        "centros": centros,
        "kpis": {k: sum(c[k] for c in centros if c["activo"])
                 for k in ("administradores", "lideres", "pendientes", "aprobadas", "valor_aprobado")}
        | {"centros": sum(1 for c in centros if c["activo"])},
        "actividad": [{"fecha": a.fecha.isoformat(), "accion": a.accion, "enlace": a.enlace,
                       "usuario": a.usuario.nombre if a.usuario else "Sistema"} for a in act],
    }


@router.get("/dashboard/lider")
def dashboard_lider(lider=Depends(solo_lider), db: Session = Depends(get_db)):
    lote_id = lote_del_lider(lider)
    vig = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    arts = db.scalars(select(Articulo).where(Articulo.lote_id == lote_id, Articulo.activo.is_(True))).all()
    out = {"vigencia": _vigencia_out(vig), "lote": lider.lote.nombre, "articulos": len(arts), "solicitud": None,
           "cotizaciones": 0, "con_cotizacion": 0, "con_precio": 0, "sin_precio": 0}
    if vig:
        res = analizar(db, vig, arts)
        out["cotizaciones"] = db.scalar(select(func.count()).select_from(Cotizacion).where(
            Cotizacion.vigencia_id == vig.id, Cotizacion.lote_id == lote_id))
        out["con_cotizacion"] = sum(1 for r in res.values() if r.n_validas > 0)
        out["con_precio"] = sum(1 for r in res.values() if r.precio_estimado is not None)
        out["sin_precio"] = len(arts) - out["con_precio"]
        s = db.scalar(select(Solicitud).where(Solicitud.vigencia_id == vig.id, Solicitud.lote_id == lote_id))
        if s:
            out["solicitud"] = {"id": s.id, "estado": s.estado, "estado_visible": estado_visible(s),
                                "n_items": len(s.items), "observaciones_admin": s.observaciones_admin,
                                "actualizado": s.actualizado.isoformat() if s.actualizado else None}
    return out


@router.get("/reportes/vigencia")
def reporte_vigencia(vigencia_id: int, centro_id: int | None = None, user=Depends(usuario_actual),
                     db: Session = Depends(get_db)):
    """Datos para los gráficos de reportes: artículos solicitados y valor por lote, estados y cobertura."""
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    centro = centro_de(user, centro_id)
    sols = _solicitudes(db, vig, centro)
    if user.rol == "LIDER":
        sols = [s for s in sols if s.lote_id == user.lote_id]
    res = analizar(db, vig, [i.articulo for s in sols for i in s.items])
    varios = user.rol == "MANAGER" and not centro
    por_lote = []
    for s in sorted(sols, key=lambda x: (x.lote.centro.nombre, x.lote.numero)):
        valor = sum((i.precio_aprobado if i.precio_aprobado is not None else (res[i.articulo_id].precio_estimado or 0))
                    * i.cantidad for i in s.items)
        por_lote.append({"lote": f"{s.lote.centro.codigo} · {s.lote.nombre}" if varios else s.lote.nombre,
                         "centro": s.lote.centro.nombre, "color": s.lote.color, "articulos": len(s.items),
                         "valor": round(valor, 2), "estado": estado_visible(s), "lider": s.lider.nombre,
                         "reenvios": s.reenvios})
    return {"vigencia": vig.codigo, "por_lote": por_lote,
            "por_estado": [{"estado": k, "cantidad": v} for k, v in Counter(estado_visible(s) for s in sols).items()],
            "cobertura": cobertura(vig.id, centro, user, db)}


@router.get("/reportes/historico")
def reporte_historico(centro_id: int | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    """Evolución por vigencia: número de solicitudes aprobadas y artículos."""
    centro = centro_de(user, centro_id)
    out = []
    for v in db.scalars(select(Vigencia).order_by(Vigencia.fecha_inicio)):
        ss = _solicitudes(db, v, centro)
        if user.rol == "LIDER":
            ss = [s for s in ss if s.lote_id == user.lote_id]
        aprob = [s for s in ss if s.estado == "APROBADA"]
        out.append({"vigencia": v.codigo, "solicitudes": len(ss), "aprobadas": len(aprob),
                    "articulos": sum(len(s.items) for s in aprob),
                    "valor": round(sum((i.precio_aprobado or 0) * i.cantidad for s in aprob for i in s.items), 2)})
    return out


# --- Notificaciones ------------------------------------------------------
@router.get("/notificaciones")
def notificaciones(user=Depends(usuario_actual), db: Session = Depends(get_db)):
    ns = db.scalars(select(Notificacion).where(Notificacion.usuario_id == user.id)
                    .order_by(Notificacion.id.desc()).limit(30)).all()
    no_leidas = db.scalar(select(func.count()).select_from(Notificacion).where(
        Notificacion.usuario_id == user.id, Notificacion.leida.is_(False)))
    return {"no_leidas": no_leidas,
            "items": [{"id": n.id, "titulo": n.titulo, "mensaje": n.mensaje, "enlace": n.enlace, "leida": n.leida,
                       "fecha": n.fecha.isoformat()} for n in ns]}


@router.post("/notificaciones/leer")
def marcar_leidas(ids: list[int] | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    stmt = update(Notificacion).where(Notificacion.usuario_id == user.id)
    if ids:
        stmt = stmt.where(Notificacion.id.in_(ids))
    db.execute(stmt.values(leida=True))
    db.commit()
    return {"ok": True}
