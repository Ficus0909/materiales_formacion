"""Motor de análisis de precios.

Replica las reglas del "FORMATO ANÁLISIS DE PRECIOS Y CONSOLIDACIÓN DE BIENES DE
CARACTERÍSTICAS TÉCNICAS UNIFORMES" (hojas L1..L11 del Excel del estudio de mercados):

* Dispersión = coeficiente de variación muestral (desv. estándar muestral / promedio).
* Precio estimado = promedio de las cotizaciones válidas (no excluidas).
* Si no hay suficientes cotizaciones se usa el promedio de precios históricos de
  contratación de la entidad, indexados con IPC + puntos adicionales (PAAG).
* El analista puede excluir cotizaciones atípicas (con motivo) o fijar precio de experto.
"""
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AnalisisPrecio, Articulo, Cotizacion, CotizacionItem, IndiceAjuste, Parametro, PrecioHistorico,
    Proveedor, Vigencia,
)

PARAMETROS_DEFECTO = {
    "min_cotizaciones": ("2", "Cotizaciones válidas de proveedores diferentes para usar el método COTIZACIONES"),
    "max_cotizaciones": ("3", "Máximo de cotizaciones (proveedores) por artículo en una vigencia"),
    "umbral_dispersion_ok": ("0.25", "Coeficiente de variación máximo aceptable (verde)"),
    "umbral_dispersion_alerta": ("0.40", "Coeficiente de variación a partir del cual es crítico (rojo)"),
    "permitir_historicos": ("1", "Usar precios históricos indexados cuando faltan cotizaciones (1=sí, 0=no)"),
    "anios_historicos": ("3", "Cantidad de años anteriores de históricos a considerar"),
    "puntos_adicionales_defecto": ("0.02", "Puntos adicionales al IPC cuando el año no tiene índice registrado"),
    "ipc_defecto": ("0.051", "IPC a usar cuando el año no tiene índice registrado"),
}


def param(db: Session, clave: str) -> float:
    p = db.get(Parametro, clave)
    return float(p.valor if p else PARAMETROS_DEFECTO[clave][0])


def cv(valores: list[float]) -> float | None:
    """Coeficiente de variación muestral, igual que DESVEST/PROMEDIO en Excel."""
    if len(valores) < 2:
        return 0.0 if valores else None
    m = statistics.mean(valores)
    return statistics.stdev(valores) / m if m else None


def semaforo(db: Session, disp: float | None, ok: float | None = None, alerta: float | None = None) -> str:
    if disp is None:
        return "gris"
    if disp <= (ok if ok is not None else param(db, "umbral_dispersion_ok")):
        return "verde"
    if disp <= (alerta if alerta is not None else param(db, "umbral_dispersion_alerta")):
        return "naranja"
    return "rojo"


def factor_indexacion(indices: dict[int, IndiceAjuste], anio_origen: int, anio_destino: int,
                      ipc_def: float, pts_def: float) -> float:
    """VF = VP * (1+IPC1+pts) * (1+IPC2+pts) ... desde el año origen hasta el año anterior al destino."""
    f = 1.0
    for a in range(anio_origen, anio_destino):
        i = indices.get(a)
        f *= 1 + (i.ipc if i else ipc_def) + (i.puntos_adicionales if i else pts_def)
    return f


@dataclass
class ResultadoArticulo:
    articulo_id: int
    cotizaciones: list[dict] = field(default_factory=list)
    historicos: list[dict] = field(default_factory=list)
    metodo: str | None = None
    metodo_manual: bool = False
    precio_experto: float | None = None
    precio_promedio_inicial: float | None = None
    dispersion_inicial: float | None = None
    precio_estimado: float | None = None
    dispersion_final: float | None = None
    soporte: str = "SIN_PRECIO"  # COMPLETO | HISTORICO | EXPERTO | INSUFICIENTE | SIN_PRECIO
    semaforo: str = "gris"
    justificacion: str = ""
    atipico_sugerido: int | None = None  # id de CotizacionItem

    @property
    def n_validas(self) -> int:
        return sum(1 for c in self.cotizaciones if not c["excluido"])

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["n_cotizaciones"] = len(self.cotizaciones)
        d["n_validas"] = self.n_validas
        return d


def _texto_exclusion(excl: list[dict]) -> str:
    if not excl:
        return ""
    etiquetas = " y ".join(c["etiqueta"] for c in excl)
    plural = len(excl) > 1
    motivo = excl[0]["motivo"] or "su valor notoriamente atípico"
    return f"Se exclu{'yen' if plural else 'ye'} {etiquetas} por {motivo} y "


def analizar(db: Session, vigencia: Vigencia, articulos: list[Articulo]) -> dict[int, ResultadoArticulo]:
    ids = [a.id for a in articulos]
    if not ids:
        return {}
    min_cot = int(param(db, "min_cotizaciones"))
    permitir_hist = param(db, "permitir_historicos") >= 1
    anios_hist = int(param(db, "anios_historicos"))
    ipc_def, pts_def = param(db, "ipc_defecto"), param(db, "puntos_adicionales_defecto")
    u_ok, u_alerta = param(db, "umbral_dispersion_ok"), param(db, "umbral_dispersion_alerta")
    indices = {i.anio: i for i in db.scalars(select(IndiceAjuste))}

    cots: dict[int, list[dict]] = defaultdict(list)
    rows = db.execute(
        select(CotizacionItem, Cotizacion.etiqueta, Cotizacion.id, Cotizacion.fecha, Proveedor.razon_social)
        .join(Cotizacion, CotizacionItem.cotizacion_id == Cotizacion.id)
        .join(Proveedor, Cotizacion.proveedor_id == Proveedor.id)
        .where(Cotizacion.vigencia_id == vigencia.id, CotizacionItem.articulo_id.in_(ids))
        .order_by(Cotizacion.etiqueta)
    )
    for item, etiqueta, cot_id, fecha, prov in rows:
        cots[item.articulo_id].append({
            "item_id": item.id, "cotizacion_id": cot_id, "etiqueta": etiqueta, "proveedor": prov,
            "fecha": fecha.isoformat(), "precio": item.precio, "excluido": item.excluido,
            "motivo": item.motivo_exclusion,
        })

    hists: dict[int, list[dict]] = defaultdict(list)
    for h in db.scalars(select(PrecioHistorico).where(
        PrecioHistorico.articulo_id.in_(ids),
        PrecioHistorico.anio < vigencia.anio,
        PrecioHistorico.anio >= vigencia.anio - anios_hist,
    ).order_by(PrecioHistorico.anio.desc())):
        f = factor_indexacion(indices, h.anio, vigencia.anio, ipc_def, pts_def)
        hists[h.articulo_id].append({"anio": h.anio, "precio": h.precio, "indexado": round(h.precio * f, 2),
                                     "factor": round(f, 6), "fuente": h.fuente})

    overrides = {a.articulo_id: a for a in db.scalars(select(AnalisisPrecio).where(
        AnalisisPrecio.vigencia_id == vigencia.id, AnalisisPrecio.articulo_id.in_(ids)))}

    out: dict[int, ResultadoArticulo] = {}
    for aid in ids:
        r = ResultadoArticulo(articulo_id=aid, cotizaciones=cots.get(aid, []), historicos=hists.get(aid, []))
        ov = overrides.get(aid)
        if ov:
            r.precio_experto = ov.precio_experto
        validas = [c for c in r.cotizaciones if not c["excluido"]]
        excluidas = [c for c in r.cotizaciones if c["excluido"]]
        hist_vals = [h["indexado"] for h in r.historicos]

        if ov and ov.metodo:
            r.metodo, r.metodo_manual = ov.metodo, True
        elif len(validas) >= min_cot:
            r.metodo = "COTIZACIONES"
        elif hist_vals and permitir_hist:
            r.metodo = "HISTORICOS"
        elif validas:
            r.metodo = "COTIZACIONES"
        elif r.precio_experto:
            r.metodo = "EXPERTO"

        if r.metodo == "COTIZACIONES" and validas:
            todos = [c["precio"] for c in r.cotizaciones]
            usados = [c["precio"] for c in validas]
            r.precio_promedio_inicial, r.dispersion_inicial = statistics.mean(todos), cv(todos)
            r.precio_estimado, r.dispersion_final = statistics.mean(usados), cv(usados)
            r.soporte = "COMPLETO" if len(validas) >= min_cot else "INSUFICIENTE"
            r.justificacion = (
                _texto_exclusion(excluidas) + "se toma el precio promedio de las cotizaciones restantes, "
                "ya que reflejan la dinámica del mercado actual y garantizan razonabilidad."
                if excluidas else
                "Se toma el precio promedio entre las cotizaciones recibidas ya que reflejan la dinámica del "
                "mercado actual y por garantizar razonabilidad."
            )
        elif r.metodo == "HISTORICOS" and hist_vals:
            r.precio_promedio_inicial = r.precio_estimado = statistics.mean(hist_vals)
            r.dispersion_inicial = r.dispersion_final = cv(hist_vals)
            r.soporte = "HISTORICO"
            r.justificacion = (
                "Se toma el precio promedio entre los precios históricos de contratación de la entidad, ya que "
                "reflejan la dinámica del mercado y garantizan razonabilidad (valores indexados por IPC + puntos "
                "adicionales)."
            )
        elif r.metodo == "EXPERTO" and r.precio_experto:
            r.precio_estimado = r.precio_experto
            r.soporte = "EXPERTO"
            r.justificacion = "Se toma el precio de experto por no contar con cotizaciones ni históricos suficientes."
        else:
            r.metodo = None

        if ov and ov.justificacion:
            r.justificacion = ov.justificacion
        r.semaforo = semaforo(db, r.dispersion_final, u_ok, u_alerta) if r.precio_estimado is not None else "gris"

        # Sugerencia de atípico: con 3+ cotizaciones válidas y dispersión fuera del umbral,
        # se sugiere la más alejada de la mediana.
        if len(validas) >= 3 and (r.dispersion_final or 0) > u_ok:
            med = statistics.median(c["precio"] for c in validas)
            r.atipico_sugerido = max(validas, key=lambda c: abs(c["precio"] - med))["item_id"]

        if r.precio_estimado is not None:
            r.precio_estimado = round(r.precio_estimado, 2)
        out[aid] = r
    return out
