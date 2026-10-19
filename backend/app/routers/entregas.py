"""Entrega de materiales a instructores (formato GIL-F-014).

Flujo: el instructor solicita bienes de un lote (ENVIADA) → el coordinador de su coordinación aprueba con su firma
(APROBADA, reserva el material) o devuelve (DEVUELTA) → el líder del lote entrega, diligenciando la cantidad
entregada (ENTREGADA, descuenta cantidad y valor) → el instructor legaliza con el acta de entrega y 3 fotos en un
plazo de 15 días hábiles (LEGALIZADA). Si vence, el sistema le envía el aviso de legalización extemporánea."""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    Coordinacion, Entrega, EntregaEvidencia, EntregaHistorial, EntregaIntegrante, EntregaItem, Lote, Usuario,
)
from ..security import requiere, solo_lider
from ..services import entregas as srv
from ..services import pdf_entregas
from ..services.common import actividad, centro_de, get_or_404, notificar, verificar_centro

router = APIRouter(prefix="/entregas", tags=["entrega de materiales"])
solo_instructor = requiere("INSTRUCTOR")
solo_coordinador = requiere("COORDINADOR")
lider_admin_manager = requiere("LIDER", "ADMIN", "MANAGER")
ROLES_MODULO = ("INSTRUCTOR", "COORDINADOR", "LIDER", "ADMIN", "MANAGER")
modulo = requiere(*ROLES_MODULO)
EDITABLES = ("ENVIADA", "DEVUELTA")
MIN_FOTOS, MAX_FOTOS = 3, 5


# --- Acceso -------------------------------------------------------------------
def _acceso(user: Usuario, e: Entrega) -> None:
    ok = {"INSTRUCTOR": e.instructor_id == user.id, "COORDINADOR": e.coordinacion_id == user.coordinacion_id,
          "LIDER": e.lote_id == user.lote_id}.get(user.rol, True)
    if not ok:
        raise HTTPException(403, "La solicitud de bienes no le corresponde")
    verificar_centro(user, e.lote.centro_id, "La solicitud de bienes")


def _historial(db: Session, e: Entrega, nuevo: str, user: Usuario | None, obs: str = "", anterior: str | None = None):
    db.add(EntregaHistorial(entrega_id=e.id, estado_anterior=e.estado if anterior is None else anterior,
                            estado_nuevo=nuevo, usuario_id=user.id if user else None, observaciones=obs))


def _coordinadores(db: Session, coordinacion_id: int) -> list[int]:
    return list(db.scalars(select(Usuario.id).where(Usuario.rol == "COORDINADOR", Usuario.activo.is_(True),
                                                    Usuario.aprobado.is_(True),
                                                    Usuario.coordinacion_id == coordinacion_id)))


def _lideres(db: Session, lote_id: int) -> list[int]:
    return list(db.scalars(select(Usuario.id).where(Usuario.rol == "LIDER", Usuario.activo.is_(True),
                                                    Usuario.lote_id == lote_id)))


# --- Presentación -------------------------------------------------------------
def _valor(e: Entrega) -> float:
    cant = (lambda i: i.cantidad_entregada or 0) if e.estado in srv.SALIDA else (lambda i: i.cantidad_solicitada)
    return round(sum(cant(i) * (i.solicitud_item.precio_aprobado or 0) for i in e.items), 2)


def resumen_out(e: Entrega, hoy: date | None = None) -> dict:
    hoy = hoy or date.today()
    return {
        "id": e.id, "estado": e.estado, "fecha_solicitud": e.fecha_solicitud.isoformat(),
        "centro_id": e.lote.centro_id, "centro": e.lote.centro.nombre,
        "lote_id": e.lote_id, "lote": e.lote.nombre, "lote_numero": e.lote.numero, "lote_color": e.lote.color,
        "coordinacion_id": e.coordinacion_id, "coordinacion": e.coordinacion.nombre,
        "instructor_id": e.instructor_id, "instructor": e.instructor.nombre, "ficha": e.ficha,
        "n_items": len(e.items), "valor": _valor(e),
        "coordinador": e.coordinador.nombre if e.coordinador else None,
        "fecha_aprobacion": e.fecha_aprobacion.isoformat() if e.fecha_aprobacion else None,
        "fecha_entrega": e.fecha_entrega.isoformat() if e.fecha_entrega else None,
        "fecha_limite_legalizacion": e.fecha_limite_legalizacion.isoformat() if e.fecha_limite_legalizacion else None,
        "dias_habiles_restantes": srv.dias_habiles_entre(hoy, e.fecha_limite_legalizacion)
        if e.estado == "ENTREGADA" and e.fecha_limite_legalizacion and hoy < e.fecha_limite_legalizacion else 0,
        "extemporanea": srv.extemporanea(e, hoy),
        "fecha_legalizacion": e.fecha_legalizacion.isoformat() if e.fecha_legalizacion else None,
        "avisos_extemporaneo": e.avisos_extemporaneo,
    }


def detalle_out(db: Session, e: Entrega) -> dict:
    disp = srv.disponible_por_item(db, [i.solicitud_item_id for i in e.items], excluir_entrega=e.id)
    hist = db.scalars(select(EntregaHistorial).where(EntregaHistorial.entrega_id == e.id)
                      .order_by(EntregaHistorial.id)).all()
    return {
        **resumen_out(e),
        "tipo_cuentadante": e.tipo_cuentadante, "nombre_cuentadante": e.nombre_cuentadante,
        "documento_cuentadante": e.documento_cuentadante, "destino": e.destino,
        "integrantes": [{"nombre": i.nombre, "documento": i.documento} for i in e.integrantes],
        "observaciones_coordinador": e.observaciones_coordinador,
        "firmada": bool(e.firma_path),
        "items": [{
            "id": i.id, "solicitud_item_id": i.solicitud_item_id, "articulo_id": i.solicitud_item.articulo_id,
            "nombre": i.solicitud_item.articulo.nombre, "unidad": i.solicitud_item.articulo.unidad,
            "descripcion": i.solicitud_item.articulo.descripcion, "precio": i.solicitud_item.precio_aprobado or 0,
            "cantidad_solicitada": i.cantidad_solicitada, "cantidad_entregada": i.cantidad_entregada,
            "observacion": i.observacion,
            # Lo que podría entregarse de este ítem sin contar esta solicitud (reservado aparte)
            "disponible": max(disp.get(i.solicitud_item_id, 0), 0),
        } for i in sorted(e.items, key=lambda x: x.solicitud_item.articulo.nombre)],
        "evidencias": [{"id": v.id, "tipo": v.tipo, "nombre": v.nombre, "fecha": v.creado.isoformat() if v.creado else None}
                       for v in e.evidencias],
        "historial": [{"fecha": h.fecha.isoformat(), "estado_anterior": h.estado_anterior, "estado_nuevo": h.estado_nuevo,
                       "usuario": h.usuario.nombre if h.usuario else "Sistema", "observaciones": h.observaciones}
                      for h in hist],
    }


# --- Catálogo para solicitar ----------------------------------------------------
@router.get("/lotes")
def lotes_con_material(user=Depends(modulo), db: Session = Depends(get_db)):
    """Lotes del centro con material recibido y saldo disponible para solicitar."""
    centro = centro_de(user)
    stmt = select(Lote).where(Lote.activo.is_(True)).order_by(Lote.numero)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    out = []
    for l in db.scalars(stmt):
        inv = srv.inventario(db, l.id)
        if inv:
            out.append({"id": l.id, "numero": l.numero, "nombre": l.nombre, "color": l.color,
                        "articulos_disponibles": sum(1 for f in inv if f["disponible"] > 0)})
    return out


@router.get("/catalogo")
def catalogo(lote_id: int, user=Depends(modulo), db: Session = Depends(get_db)):
    lote = get_or_404(db, Lote, lote_id, "Lote")
    verificar_centro(user, lote.centro_id, "El lote")
    return [{k: f[k] for k in ("solicitud_item_id", "nombre", "unidad", "descripcion", "codigo_unspsc", "vigencia",
                               "disponible")} for f in srv.inventario(db, lote_id) if f["disponible"] > 0]


@router.get("/inventario")
def inventario(lote_id: int | None = None, user=Depends(lider_admin_manager), db: Session = Depends(get_db)):
    lote = _lote_consulta(db, user, lote_id)
    filas = srv.inventario(db, lote.id)
    tot = {k: round(sum(f[k] for f in filas), 2) for k in ("valor_recibido", "valor_entregado", "valor_disponible")}
    return {"lote": {"id": lote.id, "numero": lote.numero, "nombre": lote.nombre}, "items": filas, "totales": tot}


def _lote_consulta(db: Session, user: Usuario, lote_id: int | None) -> Lote:
    if user.rol == "LIDER":
        lote_id = user.lote_id
    if not lote_id:
        raise HTTPException(422, "Indique el lote")
    lote = get_or_404(db, Lote, lote_id, "Lote")
    verificar_centro(user, lote.centro_id, "El lote")
    return lote


# --- Solicitud del instructor --------------------------------------------------
class ItemIn(BaseModel):
    solicitud_item_id: int
    cantidad: float
    observacion: str = ""


class IntegranteIn(BaseModel):
    nombre: str
    documento: str


class EntregaIn(BaseModel):
    lote_id: int
    coordinacion_id: int | None = None  # por defecto la del instructor
    tipo_cuentadante: str = "UNIPERSONAL"
    nombre_cuentadante: str = ""
    documento_cuentadante: str = ""
    integrantes: list[IntegranteIn] = []
    destino: str = "FORMACION"
    ficha: str = ""
    items: list[ItemIn]


def _aplicar(db: Session, e: Entrega, data: EntregaIn, instructor: Usuario) -> None:
    lote = get_or_404(db, Lote, data.lote_id, "Lote")
    verificar_centro(instructor, lote.centro_id, "El lote")
    coord = get_or_404(db, Coordinacion, data.coordinacion_id or instructor.coordinacion_id or 0, "Coordinación")
    if coord.centro_id != instructor.centro_id or not coord.activo:
        raise HTTPException(422, "La coordinación no pertenece a su centro o está inactiva")
    if data.tipo_cuentadante not in ("UNIPERSONAL", "MULTIPLE"):
        raise HTTPException(422, "Tipo de cuentadante inválido")
    if data.destino not in pdf_entregas.DESTINOS:
        raise HTTPException(422, "Destino de los bienes inválido")
    if data.destino == "FORMACION" and not data.ficha.strip():
        raise HTTPException(422, "Indique el código de grupo o ficha de caracterización (destino Formación)")
    integrantes = [i for i in data.integrantes if i.nombre.strip() or i.documento.strip()]
    if data.tipo_cuentadante == "MULTIPLE":
        if not data.nombre_cuentadante.strip():
            raise HTTPException(422, "Indique el nombre del cuentadante múltiple")
        if len(integrantes) < 2 or any(not i.nombre.strip() or not i.documento.strip() for i in integrantes):
            raise HTTPException(422, "Relacione nombre y número de identificación de al menos dos integrantes")
    items = [i for i in data.items if i.cantidad]
    if not items:
        raise HTTPException(422, "Seleccione al menos un bien con cantidad")
    if len({i.solicitud_item_id for i in items}) != len(items):
        raise HTTPException(422, "Hay bienes repetidos en la solicitud")
    validos = {f["solicitud_item_id"]: f for f in srv.inventario(db, lote.id)}
    disp = srv.disponible_por_item(db, [i.solicitud_item_id for i in items], excluir_entrega=e.id)
    for i in items:
        f = validos.get(i.solicitud_item_id)
        if not f:
            raise HTTPException(422, "Uno de los bienes no hace parte del material recibido del lote")
        if i.cantidad < 0:
            raise HTTPException(422, f"Cantidad inválida para «{f['nombre']}»")
        if i.cantidad > disp[i.solicitud_item_id] + 1e-9:
            raise HTTPException(409, f"«{f['nombre']}»: sólo hay {disp[i.solicitud_item_id]:g} {f['unidad']} disponibles")

    if e.id:  # al corregir: primero se retiran los ítems anteriores (unicidad entrega + ítem)
        e.items.clear()
        e.integrantes.clear()
        db.flush()
    e.lote_id, e.coordinacion_id, e.tipo_cuentadante = lote.id, coord.id, data.tipo_cuentadante
    e.nombre_cuentadante = (data.nombre_cuentadante.strip() if data.tipo_cuentadante == "MULTIPLE" else instructor.nombre)
    e.documento_cuentadante = (data.documento_cuentadante.strip() if data.tipo_cuentadante == "MULTIPLE"
                               else instructor.documento)
    e.destino, e.ficha = data.destino, data.ficha.strip()[:60]
    e.integrantes = [EntregaIntegrante(nombre=i.nombre.strip()[:160], documento=i.documento.strip()[:30])
                     for i in integrantes] if data.tipo_cuentadante == "MULTIPLE" else []
    e.items = [EntregaItem(solicitud_item_id=i.solicitud_item_id, cantidad_solicitada=i.cantidad,
                           observacion=i.observacion.strip()[:300]) for i in items]


def _avisar_coordinadores(db: Session, e: Entrega, reenvio: bool) -> None:
    notificar(db, _coordinadores(db, e.coordinacion_id),
              f"Solicitud de bienes {'corregida' if reenvio else 'nueva'} N° {e.id} (GIL-F-014)",
              f"{e.instructor.nombre} solicita {len(e.items)} bien(es) del lote {e.lote.nombre} para la ficha "
              f"{e.ficha or '—'}. Revise y apruebe o devuelva la solicitud.", f"/entregas/{e.id}")


@router.post("", status_code=201)
def crear(data: EntregaIn, instructor=Depends(solo_instructor), db: Session = Depends(get_db)):
    if not instructor.documento:
        raise HTTPException(409, "Registre su número de identificación en su perfil antes de solicitar bienes")
    e = Entrega(instructor_id=instructor.id, fecha_solicitud=date.today(), estado="ENVIADA", nombre_cuentadante="")
    _aplicar(db, e, data, instructor)
    db.add(e)
    db.flush()
    _historial(db, e, "ENVIADA", instructor, anterior="")
    db.refresh(e)
    _avisar_coordinadores(db, e, False)
    actividad(db, instructor, f"Solicitó bienes del lote {e.lote.nombre} (GIL-F-014 N° {e.id})", f"/entregas/{e.id}")
    db.commit()
    return detalle_out(db, e)


@router.put("/{eid}")
def corregir(eid: int, data: EntregaIn, instructor=Depends(solo_instructor), db: Session = Depends(get_db)):
    """El instructor corrige una solicitud enviada o devuelta; queda nuevamente ENVIADA."""
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(instructor, e)
    if e.estado not in EDITABLES:
        raise HTTPException(409, "Sólo se puede corregir una solicitud enviada o devuelta")
    reenvio = e.estado == "DEVUELTA"
    _aplicar(db, e, data, instructor)
    e.fecha_solicitud = date.today()
    _historial(db, e, "ENVIADA", instructor, "Corregida y reenviada" if reenvio else "Corregida")
    e.estado = "ENVIADA"
    db.flush()
    db.refresh(e)
    _avisar_coordinadores(db, e, True)
    db.commit()
    return detalle_out(db, e)


@router.delete("/{eid}")
def anular(eid: int, instructor=Depends(solo_instructor), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(instructor, e)
    if e.estado not in EDITABLES:
        raise HTTPException(409, "Una solicitud aprobada no se puede anular")
    db.delete(e)
    db.commit()
    return {"ok": True}


# --- Consulta -------------------------------------------------------------------
@router.get("")
def listar(estado: str = "", lote_id: int | None = None, coordinacion_id: int | None = None,
           centro_id: int | None = None, user=Depends(modulo), db: Session = Depends(get_db)):
    stmt = select(Entrega).join(Lote).order_by(Entrega.id.desc())
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    filtro = {"INSTRUCTOR": Entrega.instructor_id == user.id, "COORDINADOR": Entrega.coordinacion_id == user.coordinacion_id,
              "LIDER": Entrega.lote_id == user.lote_id}.get(user.rol)
    if filtro is not None:
        stmt = stmt.where(filtro)
    if lote_id:
        stmt = stmt.where(Entrega.lote_id == lote_id)
    if coordinacion_id:
        stmt = stmt.where(Entrega.coordinacion_id == coordinacion_id)
    hoy = date.today()
    out = [resumen_out(e, hoy) for e in db.scalars(stmt)]
    if estado == "EXTEMPORANEA":
        return [x for x in out if x["extemporanea"]]
    return [x for x in out if not estado or x["estado"] == estado]


@router.get("/informe")
def informe(formato: str = "pdf", lote_id: int | None = None, desde: date | None = None, hasta: date | None = None,
            user=Depends(lider_admin_manager), db: Session = Depends(get_db)):
    """Informe de entrega de materiales del lote (PDF o CSV): saldo del inventario y entregas con su legalización."""
    lote = _lote_consulta(db, user, lote_id)
    stmt = select(Entrega).where(Entrega.lote_id == lote.id, Entrega.estado.in_(srv.SALIDA)).order_by(Entrega.fecha_entrega)
    if desde:
        stmt = stmt.where(Entrega.fecha_entrega >= desde)
    if hasta:
        stmt = stmt.where(Entrega.fecha_entrega <= hasta)
    entregas = db.scalars(stmt).all()
    hoy = date.today()

    def legalizacion(e: Entrega) -> str:
        if e.estado == "LEGALIZADA":
            return f"Legalizada el {e.fecha_legalizacion:%d/%m/%Y}"
        return (f"EXTEMPORÁNEA (venció el {e.fecha_limite_legalizacion:%d/%m/%Y})" if srv.extemporanea(e, hoy)
                else f"Pendiente, plazo hasta el {e.fecha_limite_legalizacion:%d/%m/%Y}")

    periodo = (f" · del {desde:%d/%m/%Y}" if desde else "") + (f" al {hasta:%d/%m/%Y}" if hasta else "")
    nombre = f"informe_entregas_L{lote.numero}_{lote.abreviatura}_{hoy:%Y%m%d}"
    if formato == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["N° solicitud", "Fecha entrega", "Instructor", "Documento", "Coordinación", "Ficha", "Destino",
                    "Artículo", "Unidad", "Cantidad solicitada", "Cantidad entregada", "Precio unitario", "Valor entregado",
                    "Legalización", "Fecha límite", "Fecha legalización"])
        for e in entregas:
            for i in e.items:
                precio = i.solicitud_item.precio_aprobado or 0
                w.writerow([e.id, f"{e.fecha_entrega:%d/%m/%Y}", e.instructor.nombre, e.instructor.documento,
                            e.coordinacion.nombre, e.ficha, pdf_entregas.DESTINOS.get(e.destino, e.destino),
                            i.solicitud_item.articulo.nombre, i.solicitud_item.articulo.unidad,
                            _coma(i.cantidad_solicitada), _coma(i.cantidad_entregada or 0), _coma(precio),
                            _coma(round((i.cantidad_entregada or 0) * precio, 2)), legalizacion(e),
                            f"{e.fecha_limite_legalizacion:%d/%m/%Y}",
                            f"{e.fecha_legalizacion:%d/%m/%Y}" if e.fecha_legalizacion else ""])
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}.csv"'})
    filas = [{"id": e.id, "fecha_entrega": f"{e.fecha_entrega:%d/%m/%Y}", "instructor": e.instructor.nombre,
              "coordinacion": e.coordinacion.nombre, "ficha": e.ficha,
              "articulos": "; ".join(f"{i.solicitud_item.articulo.nombre} ({_coma(i.cantidad_entregada or 0)} "
                                     f"{i.solicitud_item.articulo.unidad})" for i in e.items if i.cantidad_entregada),
              "valor": _valor(e), "legalizacion": legalizacion(e)} for e in entregas]
    data = pdf_entregas.informe(f"INFORME DE ENTREGA DE MATERIALES · LOTE {lote.numero} {lote.nombre.upper()}",
                                f"{lote.centro.nombre}{periodo}", srv.inventario(db, lote.id), filas)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}.pdf"'})


def _coma(v: float) -> str:
    return f"{v:g}".replace(".", ",")


@router.post("/avisos-extemporaneos")
def avisos_extemporaneos(user=Depends(requiere("ADMIN", "MANAGER")), db: Session = Depends(get_db)):
    """Ejecuta ya la revisión diaria de legalizaciones vencidas (también corre sola en segundo plano)."""
    return {"avisos": srv.avisar_extemporaneas(db)}


@router.get("/{eid}")
def detalle(eid: int, user=Depends(modulo), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(user, e)
    return detalle_out(db, e)


@router.get("/{eid}/f014.pdf")
def formato_pdf(eid: int, user=Depends(modulo), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(user, e)
    return Response(pdf_entregas.f014(e), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="GIL-F-014_N{e.id}.pdf"'})


# --- Coordinador -----------------------------------------------------------------
class DecisionIn(BaseModel):
    accion: str  # APROBAR | DEVOLVER
    observaciones: str = ""


@router.post("/{eid}/decidir")
def decidir(eid: int, data: DecisionIn, coord=Depends(solo_coordinador), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(coord, e)
    if e.estado != "ENVIADA":
        raise HTTPException(409, "Sólo se pueden decidir solicitudes enviadas")
    obs = data.observaciones.strip()
    if data.accion == "DEVOLVER":
        if not obs:
            raise HTTPException(422, "Indique al instructor qué debe corregir")
        _historial(db, e, "DEVUELTA", coord, obs)
        e.estado, e.observaciones_coordinador = "DEVUELTA", obs
        notificar(db, [e.instructor_id], f"Solicitud de bienes N° {e.id} devuelta para corrección", obs, f"/entregas/{e.id}")
    elif data.accion == "APROBAR":
        if not coord.firma_path or not (settings.UPLOAD_DIR / coord.firma_path).exists():
            raise HTTPException(409, "Cargue su firma digital en «Mi firma» antes de aprobar")
        disp = srv.disponible_por_item(db, [i.solicitud_item_id for i in e.items], excluir_entrega=e.id)
        faltan = [f"{i.solicitud_item.articulo.nombre} (disponible {max(disp[i.solicitud_item_id], 0):g})"
                  for i in e.items if i.cantidad_solicitada > disp[i.solicitud_item_id] + 1e-9]
        if faltan:
            raise HTTPException(409, {"mensaje": "No hay saldo suficiente en el lote; devuelva la solicitud para que "
                                                 "el instructor ajuste las cantidades", "errores": faltan})
        _historial(db, e, "APROBADA", coord, obs)
        e.estado, e.observaciones_coordinador = "APROBADA", obs
        e.coordinador_id, e.fecha_aprobacion = coord.id, datetime.now()
        e.firma_path = srv.copiar_archivo(coord.firma_path, "firmas_aprobadas")
        notificar(db, [e.instructor_id], f"Solicitud de bienes N° {e.id} aprobada",
                  f"{coord.nombre} aprobó y firmó su formato GIL-F-014. El líder del lote {e.lote.nombre} le "
                  "entregará los materiales.", f"/entregas/{e.id}")
        notificar(db, _lideres(db, e.lote_id), f"Materiales por entregar · solicitud N° {e.id}",
                  f"La solicitud de {e.instructor.nombre} fue aprobada por {coord.nombre}. Registre la entrega en el "
                  "sistema.", f"/entregas/{e.id}")
    else:
        raise HTTPException(422, "Acción inválida")
    actividad(db, coord, f"Solicitud de bienes N° {e.id} {e.estado.lower()}", f"/entregas/{e.id}")
    db.commit()
    return detalle_out(db, e)


# --- Líder: entrega ---------------------------------------------------------------
class EntregaItemIn(BaseModel):
    id: int
    cantidad_entregada: float


class EntregarIn(BaseModel):
    fecha_entrega: date | None = None
    items: list[EntregaItemIn]
    observaciones: str = ""


@router.post("/{eid}/entregar")
def entregar(eid: int, data: EntregarIn, lider=Depends(solo_lider), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(lider, e)
    if e.estado != "APROBADA":
        raise HTTPException(409, "Sólo se entregan solicitudes aprobadas por el coordinador")
    fecha = data.fecha_entrega or date.today()
    if fecha > date.today() or fecha < e.fecha_solicitud:
        raise HTTPException(422, "La fecha de entrega no puede ser futura ni anterior a la solicitud")
    cant = {x.id: x.cantidad_entregada for x in data.items}
    total = 0
    for i in e.items:
        c = cant.get(i.id, 0)
        if c < 0 or c > i.cantidad_solicitada + 1e-9:
            raise HTTPException(422, f"«{i.solicitud_item.articulo.nombre}»: la cantidad entregada debe estar entre 0 "
                                     f"y la solicitada ({i.cantidad_solicitada:g})")
        i.cantidad_entregada = c
        total += c
    if total <= 0:
        raise HTTPException(422, "Registre la cantidad entregada de al menos un bien")
    limite = srv.sumar_dias_habiles(fecha, settings.DIAS_HABILES_LEGALIZACION)
    _historial(db, e, "ENTREGADA", lider, data.observaciones.strip())
    e.estado, e.entregado_por, e.fecha_entrega, e.fecha_limite_legalizacion = "ENTREGADA", lider.id, fecha, limite
    notificar(db, [e.instructor_id], f"Materiales entregados · solicitud de bienes N° {e.id}",
              f"El líder del lote {e.lote.nombre} registró la entrega de los materiales el {fecha:%d/%m/%Y}.\n\n"
              f"Tiene plazo hasta el {limite:%d/%m/%Y} ({settings.DIAS_HABILES_LEGALIZACION} días hábiles) para legalizar "
              "la entrega: cargue en el sistema el acta de entrega firmada y tres fotos que evidencien la entrega de "
              "los materiales a los aprendices.", f"/entregas/{e.id}")
    actividad(db, lider, f"Entregó materiales del lote {e.lote.nombre} a {e.instructor.nombre} (N° {e.id})",
              f"/entregas/{e.id}")
    db.commit()
    return detalle_out(db, e)


# --- Instructor: legalización -------------------------------------------------------
@router.post("/{eid}/legalizar")
async def legalizar(eid: int, acta: UploadFile = File(...), fotos: list[UploadFile] = File(...),
                    observaciones: str = Form(""), instructor=Depends(solo_instructor), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(instructor, e)
    if e.estado != "ENTREGADA":
        raise HTTPException(409, "Sólo se legalizan solicitudes con materiales entregados")
    fotos = [f for f in fotos if f.filename]
    if not MIN_FOTOS <= len(fotos) <= MAX_FOTOS:
        raise HTTPException(422, f"Adjunte entre {MIN_FOTOS} y {MAX_FOTOS} fotos de la entrega a los aprendices")
    guardados = []
    try:
        guardados.append(("ACTA", *await srv.guardar_archivo(acta, "evidencias", ("pdf", "jpg", "png"), "Acta de entrega")))
        for n, f in enumerate(fotos, 1):
            guardados.append(("FOTO", *await srv.guardar_archivo(f, "evidencias", ("jpg", "png"), f"Foto {n}")))
    except HTTPException:
        for _, ruta, _ in guardados:
            srv.borrar_archivo(ruta)
        raise
    for tipo, ruta, nombre in guardados:
        e.evidencias.append(EntregaEvidencia(tipo=tipo, path=ruta, nombre=nombre))
    hoy = date.today()
    tarde = srv.extemporanea(e, hoy)
    obs = observaciones.strip() + (f"{' · ' if observaciones.strip() else ''}Extemporánea: venció el "
                                   f"{e.fecha_limite_legalizacion:%d/%m/%Y}" if tarde else "")
    _historial(db, e, "LEGALIZADA", instructor, obs)
    e.estado, e.fecha_legalizacion = "LEGALIZADA", datetime.now()
    notificar(db, _lideres(db, e.lote_id), f"Entrega legalizada · solicitud N° {e.id}",
              f"{instructor.nombre} cargó el acta de entrega y {len(fotos)} fotos"
              + (" (de forma extemporánea)." if tarde else "."), f"/entregas/{e.id}")
    actividad(db, instructor, f"Legalizó la entrega de materiales N° {e.id}", f"/entregas/{e.id}")
    db.commit()
    return detalle_out(db, e)


@router.get("/{eid}/evidencias/{vid}")
def evidencia(eid: int, vid: int, user=Depends(modulo), db: Session = Depends(get_db)):
    e = get_or_404(db, Entrega, eid, "Solicitud de bienes")
    _acceso(user, e)
    v = next((x for x in e.evidencias if x.id == vid), None)
    if not v or not (settings.UPLOAD_DIR / v.path).exists():
        raise HTTPException(404, "Archivo no encontrado")
    tipo = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}[v.path.rsplit(".", 1)[-1]]
    return FileResponse(settings.UPLOAD_DIR / v.path, media_type=tipo, filename=v.nombre, content_disposition_type="inline")

