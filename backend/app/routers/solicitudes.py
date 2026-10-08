"""Solicitudes por lote: el líder arma su solicitud desde el listado maestro de su lote;
el administrador de su centro la revisa, aprueba/rechaza/devuelve y gestiona el ciclo de compra.
El manager consulta las solicitudes de todos los centros."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db import get_db
from ..models import (
    Articulo, EstadoPost, Lote, PrecioHistorico, Solicitud, SolicitudHistorial, SolicitudItem, Usuario, Vigencia,
)
from ..security import admin_o_manager, solo_admin, solo_lider, usuario_actual
from ..services import excel_export, excel_import
from ..services.common import (
    actividad, centro_de, get_or_404, lote_del_lider, notificar, notificar_admins, verificar_centro,
)
from ..services.pricing import analizar

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EDITABLES = ("BORRADOR", "DEVUELTA")
PENDIENTES = ("ENVIADA", "EN_REVISION")


def estado_visible(s: Solicitud) -> str:
    return s.estado_post.nombre if s.estado == "APROBADA" and s.estado_post else s.estado


def _historial(db: Session, s: Solicitud, nuevo: str, user: Usuario, obs: str = "") -> None:
    db.add(SolicitudHistorial(solicitud_id=s.id, estado_anterior=estado_visible(s), estado_nuevo=nuevo,
                              usuario_id=user.id, observaciones=obs))


def _acceso(user: Usuario, s: Solicitud) -> None:
    if user.rol == "LIDER" and s.lote_id != user.lote_id:
        raise HTTPException(403, "La solicitud no pertenece a su lote")
    verificar_centro(user, s.lote.centro_id, "La solicitud")


def _editable(db: Session, s: Solicitud, user: Usuario) -> None:
    _acceso(user, s)
    if user.rol != "LIDER":
        raise HTTPException(403, "Sólo el líder del lote edita la solicitud")
    if s.estado not in EDITABLES:
        raise HTTPException(409, f"La solicitud está en estado {s.estado} y no se puede editar")
    if db.get(Vigencia, s.vigencia_id).estado != "ABIERTA":
        raise HTTPException(409, "La vigencia no está abierta")


def resumen_out(s: Solicitud, total: float | None = None) -> dict:
    return {"id": s.id, "vigencia_id": s.vigencia_id, "vigencia": s.vigencia.codigo, "vigencia_estado": s.vigencia.estado,
            "centro_id": s.lote.centro_id, "centro": s.lote.centro.nombre,
            "lote_id": s.lote_id, "lote": s.lote.nombre, "lote_numero": s.lote.numero, "lote_color": s.lote.color,
            "lider_id": s.lider_id, "lider": s.lider.nombre, "estado": s.estado, "estado_visible": estado_visible(s),
            "estado_post_id": s.estado_post_id,
            "estado_post_color": s.estado_post.color if s.estado_post else None,
            "n_items": len(s.items), "reenvios": s.reenvios, "observaciones_admin": s.observaciones_admin,
            "fecha_envio": s.fecha_envio.isoformat() if s.fecha_envio else None,
            "fecha_aprobacion": s.fecha_aprobacion.isoformat() if s.fecha_aprobacion else None,
            "actualizado": s.actualizado.isoformat() if s.actualizado else None, "total": total}


def _precios(db: Session, s: Solicitud) -> dict:
    return analizar(db, s.vigencia, [i.articulo for i in s.items])


def _total(s: Solicitud, res: dict) -> float:
    return round(sum((i.precio_aprobado if i.precio_aprobado is not None else (res[i.articulo_id].precio_estimado or 0))
                     * i.cantidad for i in s.items), 2)


def detalle_out(db: Session, s: Solicitud, con_historial: bool = True) -> dict:
    res = _precios(db, s)
    items = []
    for i in sorted(s.items, key=lambda x: x.articulo.nombre):
        r = res[i.articulo_id]
        precio = i.precio_aprobado if i.precio_aprobado is not None else r.precio_estimado
        items.append({"id": i.id, "articulo_id": i.articulo_id, "codigo_unspsc": i.articulo.codigo_unspsc,
                      "nombre": i.articulo.nombre, "unidad": i.articulo.unidad, "activo": i.articulo.activo,
                      "cantidad": i.cantidad, "observacion": i.observacion, "precio_unitario": precio,
                      "subtotal": round((precio or 0) * i.cantidad, 2), "precio_congelado": i.precio_aprobado is not None,
                      "analisis": r.as_dict()})
    out = {**resumen_out(s, _total(s, res)), "items": items}
    if con_historial:
        hist = db.scalars(select(SolicitudHistorial).options(joinedload(SolicitudHistorial.usuario))
                          .where(SolicitudHistorial.solicitud_id == s.id).order_by(SolicitudHistorial.id)).all()
        out["historial"] = [{"fecha": h.fecha.isoformat(), "estado_anterior": h.estado_anterior,
                             "estado_nuevo": h.estado_nuevo, "usuario": h.usuario.nombre,
                             "observaciones": h.observaciones} for h in hist]
    return out


# --- Líder ---------------------------------------------------------------
@router.get("/mia")
def mi_solicitud(lider=Depends(solo_lider), db: Session = Depends(get_db)):
    """Solicitud del lote en la vigencia abierta (se crea en BORRADOR al primer ingreso) + catálogo del lote."""
    lote_id = lote_del_lider(lider)
    vig = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    if not vig:
        return {"vigencia": None, "solicitud": None, "catalogo": []}
    s = db.scalar(select(Solicitud).where(Solicitud.vigencia_id == vig.id, Solicitud.lote_id == lote_id))
    if not s:
        s = Solicitud(vigencia_id=vig.id, lote_id=lote_id, lider_id=lider.id, estado="BORRADOR")
        db.add(s)
        db.flush()
        db.add(SolicitudHistorial(solicitud_id=s.id, estado_nuevo="BORRADOR", usuario_id=lider.id,
                                  observaciones="Solicitud creada"))
        db.commit()
        db.refresh(s)
    arts = db.scalars(select(Articulo).where(Articulo.lote_id == lote_id, Articulo.activo.is_(True))
                      .order_by(Articulo.nombre)).all()
    res = analizar(db, vig, arts)
    sel = {i.articulo_id: i for i in s.items}
    catalogo = [{"id": a.id, "codigo_unspsc": a.codigo_unspsc, "nombre": a.nombre, "unidad": a.unidad,
                 "descripcion": a.descripcion, "n_cotizaciones": res[a.id].n_validas,
                 "precio_estimado": res[a.id].precio_estimado, "soporte": res[a.id].soporte,
                 "semaforo": res[a.id].semaforo, "seleccionado": a.id in sel,
                 "cantidad": sel[a.id].cantidad if a.id in sel else None,
                 "observacion": sel[a.id].observacion if a.id in sel else ""} for a in arts]
    # Ítems seleccionados cuyo artículo fue desactivado del maestro (deben retirarse antes de enviar)
    inactivos = [{"id": i.articulo_id, "nombre": i.articulo.nombre} for i in s.items if not i.articulo.activo]
    return {"vigencia": {"id": vig.id, "codigo": vig.codigo, "fecha_cierre": vig.fecha_cierre.isoformat()},
            "solicitud": resumen_out(s, _total(s, analizar(db, vig, [i.articulo for i in s.items]))),
            "catalogo": catalogo, "inactivos": inactivos}


@router.get("/historicas")
def mis_solicitudes(lider=Depends(solo_lider), db: Session = Depends(get_db)):
    ss = db.scalars(select(Solicitud).where(Solicitud.lote_id == lote_del_lider(lider))
                    .order_by(Solicitud.creado.desc())).all()
    return [resumen_out(s) for s in ss]


class ItemIn(BaseModel):
    articulo_id: int
    cantidad: float
    observacion: str = ""


def _upsert_items(db: Session, s: Solicitud, items: list[ItemIn]) -> dict:
    arts = {a.id: a for a in db.scalars(select(Articulo).where(Articulo.id.in_([i.articulo_id for i in items])))}
    actuales = {i.articulo_id: i for i in s.items}
    agregados = actualizados = retirados = 0
    for it in items:
        a = arts.get(it.articulo_id)
        if not a or a.lote_id != s.lote_id:
            raise HTTPException(422, f"El artículo {it.articulo_id} no pertenece al lote")
        if it.cantidad < 0:
            raise HTTPException(422, f"Cantidad negativa para «{a.nombre}»")
        if it.cantidad == 0:
            if it.articulo_id in actuales:
                s.items.remove(actuales.pop(it.articulo_id))
                retirados += 1
            continue
        if not a.activo:
            raise HTTPException(422, f"«{a.nombre}» está inactivo en el listado maestro")
        if it.articulo_id in actuales:
            actuales[it.articulo_id].cantidad = it.cantidad
            actuales[it.articulo_id].observacion = it.observacion[:300]
            actualizados += 1
        else:
            nuevo = SolicitudItem(articulo_id=it.articulo_id, cantidad=it.cantidad, observacion=it.observacion[:300])
            s.items.append(nuevo)
            actuales[it.articulo_id] = nuevo
            agregados += 1
    s.actualizado = datetime.now()
    return {"agregados": agregados, "actualizados": actualizados, "retirados": retirados}


@router.put("/{sid}/items")
def guardar_items(sid: int, items: list[ItemIn], lider=Depends(solo_lider), db: Session = Depends(get_db)):
    """Autoguardado por lotes: cantidad 0 retira el artículo de la solicitud."""
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _editable(db, s, lider)
    r = _upsert_items(db, s, items)
    db.commit()
    return {**r, "n_items": len(s.items), "actualizado": s.actualizado.isoformat()}


@router.get("/{sid}/plantilla")
def plantilla_cantidades(sid: int, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(user, s)
    arts = db.scalars(select(Articulo).where(Articulo.lote_id == s.lote_id, Articulo.activo.is_(True))
                      .order_by(Articulo.nombre)).all()
    data = excel_export.plantilla(
        f"SOLICITUD DE MATERIALES · Lote {s.lote.numero} {s.lote.nombre} · Vigencia {s.vigencia.codigo}", arts,
        "Cantidad", {i.articulo_id: i.cantidad for i in s.items},
        "Diligencie la cantidad requerida para la vigencia. Deje en blanco o en 0 los artículos que no necesita.")
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="solicitud_{s.lote.abreviatura}_{s.vigencia.codigo}.xlsx"'})


@router.post("/{sid}/importar")
async def importar_cantidades(sid: int, archivo: UploadFile = File(...), lider=Depends(solo_lider),
                              db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _editable(db, s, lider)
    valores = excel_import.leer_columnas_id_valor(await archivo.read(), "cantidad")
    # Lo que no viene en la plantilla se retira: la plantilla representa la solicitud completa
    items = [ItemIn(articulo_id=a, cantidad=c) for a, c in valores.items()]
    items += [ItemIn(articulo_id=i.articulo_id, cantidad=0) for i in s.items if i.articulo_id not in valores]
    r = _upsert_items(db, s, items)
    actividad(db, lider, f"Importó cantidades desde Excel en la solicitud #{s.id}")
    db.commit()
    return {**r, "n_items": len(s.items)}


def _vista_clonacion(db: Session, origen: Solicitud, vig: Vigencia) -> list[dict]:
    activos = [i.articulo for i in origen.items if i.articulo.activo]
    res = analizar(db, vig, activos)
    out = []
    for i in sorted(origen.items, key=lambda x: x.articulo.nombre):
        if not i.articulo.activo:
            estado = "NO_DISPONIBLE"
        elif res[i.articulo_id].precio_estimado is None:
            estado = "PENDIENTE_PRECIO"
        else:
            estado = "LISTO"
        out.append({"articulo_id": i.articulo_id, "nombre": i.articulo.nombre, "cantidad": i.cantidad, "estado": estado})
    return out


@router.get("/{sid}/clonables")
def clonables(sid: int, lider=Depends(solo_lider), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(lider, s)
    origenes = db.scalars(select(Solicitud).where(Solicitud.lote_id == s.lote_id, Solicitud.id != s.id,
                                                  Solicitud.estado == "APROBADA")
                          .order_by(Solicitud.creado.desc())).all()
    return [{**resumen_out(o), "vista": _vista_clonacion(db, o, s.vigencia)} for o in origenes]


class ClonarIn(BaseModel):
    origen_id: int


@router.post("/{sid}/clonar")
def clonar(sid: int, data: ClonarIn, lider=Depends(solo_lider), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _editable(db, s, lider)
    o = get_or_404(db, Solicitud, data.origen_id, "Solicitud origen")
    if o.lote_id != s.lote_id or o.estado != "APROBADA" or o.id == s.id:
        raise HTTPException(409, "Sólo se pueden clonar solicitudes aprobadas de vigencias anteriores del mismo lote")
    vista = _vista_clonacion(db, o, s.vigencia)
    ya = {i.articulo_id for i in s.items}
    nuevos = [ItemIn(articulo_id=v["articulo_id"], cantidad=v["cantidad"]) for v in vista
              if v["estado"] != "NO_DISPONIBLE" and v["articulo_id"] not in ya]
    r = _upsert_items(db, s, nuevos)
    actividad(db, lider, f"Clonó la solicitud de la vigencia {o.vigencia.codigo} en la #{s.id}")
    db.commit()
    return {**r, "omitidos": sum(1 for v in vista if v["estado"] == "NO_DISPONIBLE"),
            "ya_existian": sum(1 for v in vista if v["articulo_id"] in ya),
            "pendientes_precio": sum(1 for v in vista if v["estado"] == "PENDIENTE_PRECIO" and v["articulo_id"] not in ya)}


def validar_envio(db: Session, s: Solicitud) -> list[str]:
    errores = []
    if not s.items:
        errores.append("La solicitud no tiene artículos")
    res = _precios(db, s)
    for i in s.items:
        if not i.articulo.activo:
            errores.append(f"«{i.articulo.nombre}» fue retirado del listado maestro: quítelo de la solicitud")
        elif res[i.articulo_id].precio_estimado is None:
            errores.append(f"«{i.articulo.nombre}» no tiene precio de referencia (cargue al menos una cotización)")
        if i.cantidad <= 0:
            errores.append(f"«{i.articulo.nombre}» tiene cantidad inválida")
    return errores


@router.post("/{sid}/enviar")
def enviar(sid: int, lider=Depends(solo_lider), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _editable(db, s, lider)
    errores = validar_envio(db, s)
    if errores:
        raise HTTPException(422, {"mensaje": "La solicitud no se puede enviar", "errores": errores})
    reenvio = s.estado == "DEVUELTA"
    _historial(db, s, "ENVIADA", lider, "Reenviada tras correcciones" if reenvio else "")
    s.estado, s.fecha_envio = "ENVIADA", datetime.now()
    if reenvio:
        s.reenvios += 1
    notificar_admins(db, s.lote.centro_id, f"Solicitud {'reenviada' if reenvio else 'enviada'}: {s.lote.nombre}",
                     f"{lider.nombre} envió {len(s.items)} artículos para revisión.", f"/admin/solicitudes/{s.id}")
    actividad(db, lider, f"{'Reenvió' if reenvio else 'Envió'} la solicitud del lote {s.lote.nombre} "
                         f"({len(s.items)} artículos)", f"/admin/solicitudes/{s.id}")
    db.commit()
    return resumen_out(s)


# --- Administrador ------------------------------------------------------
@router.get("")
def bandeja(vigencia_id: int | None = None, lote_id: int | None = None, estado: str = "", lider_id: int | None = None,
            centro_id: int | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    stmt = (select(Solicitud).join(Lote)
            .order_by(Solicitud.fecha_envio.is_(None), Solicitud.fecha_envio.desc(), Solicitud.id.desc()))
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    if user.rol == "LIDER":
        lote_id = user.lote_id
    for col, val in ((Solicitud.vigencia_id, vigencia_id), (Solicitud.lote_id, lote_id), (Solicitud.lider_id, lider_id)):
        if val:
            stmt = stmt.where(col == val)
    if estado == "PENDIENTES":
        stmt = stmt.where(Solicitud.estado.in_(PENDIENTES))
    elif estado.startswith("POST:"):
        stmt = stmt.where(Solicitud.estado_post_id == int(estado[5:]))
    elif estado:
        stmt = stmt.where(Solicitud.estado == estado)
    out = []
    for s in db.scalars(stmt):
        out.append(resumen_out(s, _total(s, _precios(db, s))))
    return out


@router.get("/consolidado/exportar")
def exportar_consolidado(vigencia_id: int, centro_id: int | None = None, user=Depends(admin_o_manager),
                         db: Session = Depends(get_db)):
    """Consolidado del centro (administrador) o de todos los centros / uno elegido (manager)."""
    vig = get_or_404(db, Vigencia, vigencia_id, "Vigencia")
    stmt = (select(Solicitud).join(Lote).where(Solicitud.vigencia_id == vig.id,
                                               Solicitud.estado.not_in(("BORRADOR", "CANCELADA")))
            .order_by(Lote.centro_id, Lote.numero))
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    ss = db.scalars(stmt).all()
    arts = [i.articulo for s in ss for i in s.items]
    res = analizar(db, vig, arts)
    data = excel_export.consolidado(vig, ss, {k: v.precio_estimado for k, v in res.items()})
    sufijo = f"_{ss[0].lote.centro.codigo}" if centro and ss else ""
    return Response(data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="consolidado_{vig.codigo}{sufijo}.xlsx"'})


@router.get("/{sid}")
def detalle(sid: int, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(user, s)
    out = detalle_out(db, s)
    if s.estado in EDITABLES:
        out["errores_envio"] = validar_envio(db, s)
    return out


@router.post("/{sid}/revisar")
def tomar_revision(sid: int, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(admin, s)
    if s.estado != "ENVIADA":
        raise HTTPException(409, "Sólo una solicitud enviada puede pasar a revisión")
    _historial(db, s, "EN_REVISION", admin, f"Revisión iniciada por {admin.nombre}")
    s.estado = "EN_REVISION"
    notificar(db, [s.lider_id], "Su solicitud está en revisión", "", "/lider/seguimiento")
    db.commit()
    return resumen_out(s)


class DecisionIn(BaseModel):
    accion: str  # APROBAR | RECHAZAR | DEVOLVER
    observaciones: str = ""


@router.post("/{sid}/decidir")
def decidir(sid: int, data: DecisionIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(admin, s)
    if s.estado not in PENDIENTES:
        raise HTTPException(409, "Sólo se pueden decidir solicitudes enviadas o en revisión")
    obs = data.observaciones.strip()
    destino = {"APROBAR": "APROBADA", "RECHAZAR": "RECHAZADA", "DEVOLVER": "DEVUELTA"}.get(data.accion)
    if not destino:
        raise HTTPException(422, "Acción inválida")
    if destino != "APROBADA" and not obs:
        raise HTTPException(422, "Las observaciones son obligatorias para rechazar o devolver")
    if destino == "APROBADA":
        errores = validar_envio(db, s)
        if errores:
            raise HTTPException(422, {"mensaje": "No se puede aprobar", "errores": errores})
        res = _precios(db, s)
        for i in s.items:
            # Se congela el precio y se registra como histórico para próximas vigencias
            i.precio_aprobado = res[i.articulo_id].precio_estimado
            h = db.scalar(select(PrecioHistorico).where(PrecioHistorico.articulo_id == i.articulo_id,
                                                        PrecioHistorico.anio == s.vigencia.anio))
            if h:
                h.precio, h.fuente = i.precio_aprobado, f"Estudio de mercados vigencia {s.vigencia.codigo}"
            else:
                db.add(PrecioHistorico(articulo_id=i.articulo_id, anio=s.vigencia.anio, precio=i.precio_aprobado,
                                       fuente=f"Estudio de mercados vigencia {s.vigencia.codigo}"))
        s.fecha_aprobacion = datetime.now()
    _historial(db, s, destino, admin, obs)
    s.estado, s.observaciones_admin = destino, obs
    verbo = {"APROBADA": "aprobada", "RECHAZADA": "rechazada", "DEVUELTA": "devuelta para corrección"}[destino]
    notificar(db, [s.lider_id], f"Su solicitud fue {verbo}", obs,
              "/lider/mi-solicitud" if destino == "DEVUELTA" else "/lider/seguimiento")
    actividad(db, admin, f"Solicitud del lote {s.lote.nombre} {verbo}", f"/admin/solicitudes/{s.id}")
    db.commit()
    return detalle_out(db, s)


class AvanceIn(BaseModel):
    estado_post_id: int
    observaciones: str


@router.post("/{sid}/avanzar")
def avanzar(sid: int, data: AvanceIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    s = get_or_404(db, Solicitud, sid, "Solicitud")
    _acceso(admin, s)
    if s.estado != "APROBADA":
        raise HTTPException(409, "Sólo las solicitudes aprobadas entran al ciclo de compra")
    nuevo = get_or_404(db, EstadoPost, data.estado_post_id, "Estado")
    if not nuevo.activo:
        raise HTTPException(409, "El estado está inactivo")
    if s.estado_post and nuevo.orden <= s.estado_post.orden:
        raise HTTPException(409, "Los estados post-aprobación sólo avanzan, no se puede retroceder")
    if not data.observaciones.strip():
        raise HTTPException(422, "Las observaciones son obligatorias (ej. «OC #2026-045 emitida»)")
    _historial(db, s, nuevo.nombre, admin, data.observaciones.strip())
    s.estado_post_id = nuevo.id
    db.flush()
    db.refresh(s)
    notificar(db, [s.lider_id], f"Su solicitud avanzó a «{nuevo.nombre}»", data.observaciones.strip(),
              "/lider/seguimiento")
    actividad(db, admin, f"Solicitud del lote {s.lote.nombre} pasó a {nuevo.nombre}", f"/admin/solicitudes/{s.id}")
    db.commit()
    return detalle_out(db, s)
