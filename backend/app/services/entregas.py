"""Entrega de materiales a instructores (formato GIL-F-014): inventario del lote, días hábiles,
archivos de evidencia y avisos de legalización extemporánea."""
import logging
import shutil
import uuid
from collections import defaultdict
from datetime import date, timedelta

import holidays
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Entrega, EntregaItem, EstadoPost, Solicitud, SolicitudItem
from .common import notificar

log = logging.getLogger("entregas")

# Estados de la solicitud de bienes que comprometen material del lote
RESERVA = ("APROBADA",)  # aprobada por el coordinador y pendiente de entrega: reserva la cantidad solicitada
SALIDA = ("ENTREGADA", "LEGALIZADA")  # descuenta la cantidad entregada


# --- Días hábiles (Colombia) -------------------------------------------------
def _festivos(anios: range):
    return holidays.CO(years=anios)


def sumar_dias_habiles(desde: date, dias: int) -> date:
    """Fecha del día hábil número `dias` contado después de `desde` (sin fines de semana ni festivos de Colombia)."""
    festivos = _festivos(range(desde.year, desde.year + 2))
    fecha, contados = desde, 0
    while contados < dias:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5 and fecha not in festivos:
            contados += 1
    return fecha


def dias_habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles transcurridos después de `desde` y hasta `hasta` inclusive (0 si hasta <= desde)."""
    if hasta <= desde:
        return 0
    festivos = _festivos(range(desde.year, hasta.year + 1))
    return sum(1 for i in range(1, (hasta - desde).days + 1)
               if (d := desde + timedelta(days=i)).weekday() < 5 and d not in festivos)


def extemporanea(e: Entrega, hoy: date | None = None) -> bool:
    return e.estado == "ENTREGADA" and e.fecha_limite_legalizacion is not None \
        and (hoy or date.today()) > e.fecha_limite_legalizacion


# --- Inventario del lote -----------------------------------------------------
def fin_ciclo_compra(db: Session) -> EstadoPost | None:
    """Último estado activo del ciclo de compra (por defecto «En el Punto»): el material ya está en el centro."""
    return db.scalar(select(EstadoPost).where(EstadoPost.activo.is_(True)).order_by(EstadoPost.orden.desc()))


def solicitudes_con_material(db: Session, lote_id: int) -> list[Solicitud]:
    fin = fin_ciclo_compra(db)
    if not fin:
        return []
    return db.scalars(select(Solicitud).where(Solicitud.lote_id == lote_id, Solicitud.estado == "APROBADA",
                                              Solicitud.estado_post_id == fin.id)
                      .order_by(Solicitud.creado.desc())).all()


def _comprometido(db: Session, item_ids: list[int], excluir_entrega: int | None = None) -> tuple[dict, dict]:
    """(entregado, reservado) por ítem de solicitud."""
    entregado, reservado = defaultdict(float), defaultdict(float)
    if not item_ids:
        return entregado, reservado
    stmt = (select(EntregaItem.solicitud_item_id, Entrega.estado,
                   func.sum(EntregaItem.cantidad_entregada), func.sum(EntregaItem.cantidad_solicitada))
            .join(Entrega).where(EntregaItem.solicitud_item_id.in_(item_ids), Entrega.estado.in_(RESERVA + SALIDA))
            .group_by(EntregaItem.solicitud_item_id, Entrega.estado))
    if excluir_entrega:
        stmt = stmt.where(Entrega.id != excluir_entrega)
    for sid, estado, entregada, solicitada in db.execute(stmt):
        if estado in SALIDA:
            entregado[sid] += entregada or 0
        else:
            reservado[sid] += solicitada or 0
    return entregado, reservado


def inventario(db: Session, lote_id: int) -> list[dict]:
    """Material recibido del lote (solicitudes al final del ciclo de compra) con lo entregado, reservado y disponible,
    en cantidad y en valor (precio aprobado congelado)."""
    filas = []
    sols = solicitudes_con_material(db, lote_id)
    items = [i for s in sols for i in s.items]
    entregado, reservado = _comprometido(db, [i.id for i in items])
    for s in sols:
        for i in sorted(s.items, key=lambda x: x.articulo.nombre):
            precio = i.precio_aprobado or 0
            disponible = max(i.cantidad - entregado[i.id] - reservado[i.id], 0)
            filas.append({
                "solicitud_item_id": i.id, "articulo_id": i.articulo_id, "vigencia": s.vigencia.codigo,
                "codigo_unspsc": i.articulo.codigo_unspsc, "nombre": i.articulo.nombre, "unidad": i.articulo.unidad,
                "descripcion": i.articulo.descripcion, "precio": precio,
                "recibido": i.cantidad, "entregado": entregado[i.id], "reservado": reservado[i.id],
                "disponible": disponible,
                "valor_recibido": round(i.cantidad * precio, 2), "valor_entregado": round(entregado[i.id] * precio, 2),
                "valor_disponible": round(disponible * precio, 2),
            })
    return filas


def disponible_por_item(db: Session, item_ids: list[int], excluir_entrega: int | None = None) -> dict[int, float]:
    items = {i.id: i for i in db.scalars(select(SolicitudItem).where(SolicitudItem.id.in_(item_ids)))}
    entregado, reservado = _comprometido(db, list(items), excluir_entrega)
    return {iid: i.cantidad - entregado[iid] - reservado[iid] for iid, i in items.items()}


# --- Archivos (firmas y evidencias) ------------------------------------------
TIPOS = {b"\x89PNG": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"%PDF": ("pdf", "application/pdf")}


def tipo_archivo(contenido: bytes) -> tuple[str, str] | None:
    return next((t for firma, t in TIPOS.items() if contenido.startswith(firma)), None)


async def guardar_archivo(archivo: UploadFile, carpeta: str, permitidos: tuple[str, ...], que: str) -> tuple[str, str]:
    """Valida tipo real (firma del archivo) y tamaño; devuelve (ruta relativa a UPLOAD_DIR, nombre original)."""
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(422, f"{que}: el archivo está vacío")
    if len(contenido) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"{que}: supera el máximo de {settings.MAX_UPLOAD_MB} MB")
    tipo = tipo_archivo(contenido)
    if not tipo or tipo[0] not in permitidos:
        raise HTTPException(422, f"{que}: el archivo debe ser {' o '.join(p.upper() for p in permitidos)}")
    destino = settings.UPLOAD_DIR / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    nombre = f"{carpeta}/{uuid.uuid4().hex}.{tipo[0]}"
    (settings.UPLOAD_DIR / nombre).write_bytes(contenido)
    return nombre, (archivo.filename or f"archivo.{tipo[0]}")[:200]


def copiar_archivo(ruta: str, carpeta: str) -> str:
    """Copia inmutable (p. ej. la firma del coordinador en el momento de aprobar)."""
    ext = ruta.rsplit(".", 1)[-1]
    nuevo = f"{carpeta}/{uuid.uuid4().hex}.{ext}"
    (settings.UPLOAD_DIR / carpeta).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(settings.UPLOAD_DIR / ruta, settings.UPLOAD_DIR / nuevo)
    return nuevo


def borrar_archivo(ruta: str) -> None:
    if ruta:
        (settings.UPLOAD_DIR / ruta).unlink(missing_ok=True)


# --- Avisos de legalización extemporánea -------------------------------------
def avisar_extemporaneas(db: Session, hoy: date | None = None) -> int:
    """Correo (y aviso en la aplicación) al instructor cuya legalización venció: el día siguiente al vencimiento
    y luego cada DIAS_RECORDATORIO_EXTEMPORANEO días mientras no legalice. Devuelve cuántos avisos envió."""
    hoy = hoy or date.today()
    n = 0
    pendientes = db.scalars(select(Entrega).where(Entrega.estado == "ENTREGADA",
                                                  Entrega.fecha_limite_legalizacion < hoy)).all()
    for e in pendientes:
        if e.ultimo_aviso_extemporaneo and (hoy - e.ultimo_aviso_extemporaneo).days < settings.DIAS_RECORDATORIO_EXTEMPORANEO:
            continue
        dias = dias_habiles_entre(e.fecha_limite_legalizacion, hoy)
        notificar(db, [e.instructor_id], f"Legalización extemporánea · solicitud de bienes N° {e.id}",
                  f"El proceso de legalización de la entrega de materiales del lote {e.lote.nombre}, recibidos el "
                  f"{e.fecha_entrega:%d/%m/%Y}, se encuentra EXTEMPORÁNEO: el plazo de "
                  f"{settings.DIAS_HABILES_LEGALIZACION} días hábiles venció el {e.fecha_limite_legalizacion:%d/%m/%Y} "
                  f"({dias} día(s) hábil(es) de retraso).\n\nRealícelo de inmediato: cargue en el sistema el acta de "
                  "entrega firmada y las tres fotos que evidencian la entrega de los materiales a los aprendices.",
                  f"/entregas/{e.id}")
        e.ultimo_aviso_extemporaneo, e.avisos_extemporaneo = hoy, (e.avisos_extemporaneo or 0) + 1
        n += 1
    db.commit()
    if n:
        log.info("Avisos de legalización extemporánea enviados: %d", n)
    return n
