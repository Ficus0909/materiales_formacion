"""PDF del formato GIL-F-014 (Formato solicitud de bienes para uso de cuentadantes, versión 07) y del informe
de entrega de materiales del líder de lote. Replica la estructura de contexto/FORMATO GIL 014 MODELO.xlsx."""
import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import settings

LOGO = Path(__file__).resolve().parent.parent / "static" / "logo-sena.png"
VERDE = colors.HexColor("#39A900")
GRIS = colors.HexColor("#D9D9D9")
NEGRO = colors.black

_base = ParagraphStyle("base", fontName="Helvetica", fontSize=7.5, leading=9)
_neg = ParagraphStyle("neg", parent=_base, fontName="Helvetica-Bold")
_cen = ParagraphStyle("cen", parent=_neg, alignment=TA_CENTER)
_titulo = ParagraphStyle("tit", parent=_neg, fontSize=9, leading=11, alignment=TA_CENTER)
_peq = ParagraphStyle("peq", parent=_base, fontSize=6.5, leading=8)

DESTINOS = {"FORMACION": "Formación", "ADMINISTRATIVA": "Área administrativa"}


def _p(txt, estilo=_base):
    from xml.sax.saxutils import escape
    return Paragraph(escape(str(txt if txt is not None else "")).replace("\n", "<br/>"), estilo)


def _num(v) -> str:
    if v is None:
        return ""
    return f"{v:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")


def _rejilla(extra=()):
    return TableStyle([("GRID", (0, 0), (-1, -1), 0.6, NEGRO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                       ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), *extra])


def _logo(alto: float):
    if not LOGO.exists():
        return ""
    img = Image(str(LOGO))
    img.drawWidth, img.drawHeight = alto * img.imageWidth / img.imageHeight, alto
    return img


def cargo_coordinador(coordinacion: str) -> str:
    """Cargo por defecto a partir del nombre de la coordinación:
    «Coordinación de Programas Especiales» → «COORDINADOR DE PROGRAMAS ESPECIALES»,
    «Coordinación Académica» → «COORDINADOR ACADÉMICO»."""
    resto = coordinacion.replace("Coordinación", "", 1).strip()
    if resto and " " not in resto and resto.lower().endswith("a"):  # adjetivo: concuerda con «Coordinador»
        resto = resto[:-1] + "o"
    return f"Coordinador {resto}".strip().upper()


def f014(e) -> bytes:
    """Genera el GIL-F-014 diligenciado para una solicitud de bienes (Entrega)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm,
                            bottomMargin=10 * mm, title=f"GIL-F-014 N° {e.id}", author="SENA · Materiales de Formación")
    ancho = A4[0] - 24 * mm
    centro = e.lote.centro
    h = []

    # Encabezado institucional
    enc = Table([[_logo(16 * mm), _p("Versión: 07\nCódigo: GIL-F-014", _neg)],
                 [_p("PROCESO", _cen), ""], [_p("GESTIÓN DE INFRAESTRUCTURA Y LOGÍSTICA", _titulo), ""],
                 [_p("NOMBRE DEL FORMATO", _cen), ""],
                 [_p("FORMATO SOLICITUD DE BIENES PARA USO DE CUENTADANTES", _titulo), ""],
                 [_p("CLASIFICACIÓN DE LA INFORMACIÓN", _cen), ""]],
                colWidths=[ancho - 45 * mm, 45 * mm])
    enc.setStyle(_rejilla([("SPAN", (0, i), (1, i)) for i in range(1, 6)] + [
        ("ALIGN", (0, 0), (0, 0), "CENTER"), ("BACKGROUND", (0, 1), (-1, 1), GRIS),
        ("BACKGROUND", (0, 3), (-1, 3), GRIS), ("BACKGROUND", (0, 5), (-1, 5), GRIS)]))
    h.append(enc)
    clas = Table([[_p("Pública:", _neg), _p("X", _cen), _p("Pública Clasificada:", _neg), "",
                   _p("Pública Reservada:", _neg), ""]],
                 colWidths=[ancho * f for f in (0.18, 0.08, 0.24, 0.08, 0.34, 0.08)])
    clas.setStyle(_rejilla())
    h.append(clas)
    h.append(Spacer(1, 3 * mm))

    # Datos de la solicitud
    w = [ancho * f for f in (0.22, 0.28, 0.2, 0.3)]
    datos = Table([
        [_p("FECHA SOLICITUD", _neg), _p(f"{e.fecha_solicitud:%d/%m/%Y}"), _p("AREA", _neg), _p(e.coordinacion.nombre)],
        [_p("CODIGO REGIONAL", _neg), _p(centro.codigo_regional), _p("NOMBRE REGIONAL", _neg), _p(centro.regional)],
        [_p("COD CENTRO DE COSTOS", _neg), _p(centro.centro_costo), _p("NOMBRE CENTRO DE COSTO", _neg),
         _p(centro.nombre.upper())],
        [_p("NOMBRE DE JEFE DE OFICINA O COORDINADOR DE AREA:", _neg),
         _p(e.coordinador.nombre if e.coordinador else ""), "", ""],
        [_p("TIPO DE CUENTADANTE", _neg), _p("MÚLTIPLE" if e.tipo_cuentadante == "MULTIPLE" else "UNIPERSONAL"), "", ""],
        [_p("NOMBRE DEL CUENTADANTE UNIPERSONAL O CUENTADANTE MÚLTIPLE", _neg), _p(e.nombre_cuentadante),
         _p("N° DE IDENTIFICIACIÓN", _neg), _p(e.documento_cuentadante)],
    ], colWidths=w)
    datos.setStyle(_rejilla([("SPAN", (1, 3), (3, 3)), ("SPAN", (1, 4), (3, 4))]))
    h.append(datos)
    h.append(Spacer(1, 2 * mm))

    integrantes = list(e.integrantes) or [None] * 3
    mult = [[_p("PARA EL CASO DE CUENTADANTE MÚLTIPLES EN EL SIGUIENTE CAMPO RELACIONE EL NOMBRE Y NÚMERO DE "
                "IDENTIFICACIÓN DE LAS PERSONAS QUE LO CONFORMAN", _cen), "", "", ""]]
    for i in integrantes:
        mult.append([_p("NOMBRE", _neg), _p(i.nombre if i else ""), _p("N° DE IDENTIFICIACIÓN", _neg),
                     _p(i.documento if i else "")])
    t = Table(mult, colWidths=w)
    t.setStyle(_rejilla([("SPAN", (0, 0), (3, 0)), ("BACKGROUND", (0, 0), (-1, 0), GRIS)]))
    h.append(t)
    h.append(Spacer(1, 2 * mm))

    t = Table([[_p("DESTINO DE LOS BIENES SOLICITADOS", _neg), _p(DESTINOS.get(e.destino, e.destino))],
               [_p("CÓDIGO DE GRUPO O FICHA DE CARACTERIZACIÓN", _neg), _p(e.ficha)]],
              colWidths=[ancho * 0.5, ancho * 0.5])
    t.setStyle(_rejilla())
    h.append(t)
    h.append(Spacer(1, 2 * mm))

    # Bienes solicitados
    filas = [[_p(x, _cen) for x in ("ITEM", "CÓDIGO SENA", "DESCRIPCION DE BIEN", "UNIDA DE MEDIDA",
                                    "CANTIDAD SOLICITADA", "CANTIDAD ENTREGADA", "OBSERVACIONES")]]
    items = sorted(e.items, key=lambda x: x.solicitud_item.articulo.nombre)
    for n, it in enumerate(items, 1):
        a = it.solicitud_item.articulo
        desc = f"{a.nombre}: {a.descripcion}" if a.descripcion else a.nombre
        desc = desc if len(desc) <= 200 else desc[:197].rstrip() + "…"
        filas.append([_p(n, _cen), "", _p(desc, _peq), _p(a.unidad, _cen), _p(_num(it.cantidad_solicitada), _cen),
                      _p(_num(it.cantidad_entregada), _cen), _p(it.observacion, _peq)])
    for n in range(len(items) + 1, 11):  # el formato trae filas en blanco
        filas.append([_p(n, _cen), "", "", "", "", "", ""])
    t = Table(filas, colWidths=[ancho * f for f in (0.06, 0.09, 0.33, 0.08, 0.12, 0.12, 0.2)], repeatRows=1)
    t.setStyle(_rejilla([("BACKGROUND", (0, 0), (-1, 0), GRIS), ("VALIGN", (0, 1), (-1, -1), "TOP")]))
    h.append(t)
    h.append(Spacer(1, 4 * mm))

    # Autorización (coordinador)
    firma = ""
    if e.firma_path and (settings.UPLOAD_DIR / e.firma_path).exists():
        firma = Image(str(settings.UPLOAD_DIR / e.firma_path))
        alto = 14 * mm
        firma.drawWidth, firma.drawHeight = min(alto * firma.imageWidth / firma.imageHeight, 60 * mm), alto
    fin = Table([[_p("NOMBRE:", _neg), _p(e.coordinador.nombre if e.coordinador else ""), _p("CARGO", _neg),
                  _p((e.coordinador.cargo or cargo_coordinador(e.coordinacion.nombre)).upper() if e.coordinador else "")],
                 [_p("FIRMA:", _neg), firma, "", ""]],
                colWidths=[ancho * f for f in (0.1, 0.4, 0.1, 0.4)], rowHeights=[None, 18 * mm])
    fin.setStyle(_rejilla([("SPAN", (1, 1), (3, 1))]))
    h.append(fin)
    if e.estado in ("ENVIADA", "DEVUELTA"):
        h.append(Spacer(1, 2 * mm))
        h.append(_p("PENDIENTE DE APROBACIÓN DEL COORDINADOR: este formato no es válido hasta que sea aprobado y firmado.",
                    ParagraphStyle("alerta", parent=_neg, textColor=colors.HexColor("#C00000"))))
    h.append(Spacer(1, 3 * mm))
    h.append(_p("Nota: La cantidad de bienes entregada puede ser inferior a la cantidad de bienes solicitados toda vez "
                "que la solicitud se atiende de acuerdo a las existencias.", _peq))
    h.append(_p(f"Solicitud de bienes N° {e.id} · generado por el sistema Materiales de Formación el "
                f"{date.today():%d/%m/%Y}", _peq))
    doc.build(h)
    return buf.getvalue()


def informe(titulo: str, subtitulo: str, inventario: list[dict], entregas: list[dict]) -> bytes:
    """Informe de entrega de materiales del lote: saldo del inventario y entregas con su legalización."""
    buf = io.BytesIO()
    pag = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=pag, leftMargin=10 * mm, rightMargin=10 * mm, topMargin=10 * mm,
                            bottomMargin=10 * mm, title=titulo, author="SENA · Materiales de Formación")
    ancho = pag[0] - 20 * mm
    h = []
    enc = Table([[_logo(14 * mm), [_p("SERVICIO NACIONAL DE APRENDIZAJE - SENA", _titulo), _p(titulo, _titulo),
                                  _p(subtitulo, _cen)]]], colWidths=[22 * mm, ancho - 22 * mm])
    enc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    h += [enc, Spacer(1, 4 * mm)]

    tot = {k: sum(f[k] for f in inventario) for k in ("valor_recibido", "valor_entregado", "valor_disponible")}
    h.append(_p(f"Valor recibido: ${_num(tot['valor_recibido'])} · entregado: ${_num(tot['valor_entregado'])} · "
                f"saldo: ${_num(tot['valor_disponible'])}", _neg))
    h.append(Spacer(1, 2 * mm))
    filas = [[_p(x, _cen) for x in ("Artículo", "Unidad", "Recibido", "Entregado", "Reservado", "Saldo",
                                    "Precio unit.", "Valor entregado", "Valor saldo")]]
    for f in inventario:
        filas.append([_p(f["nombre"], _peq), _p(f["unidad"], _cen), _p(_num(f["recibido"]), _cen),
                      _p(_num(f["entregado"]), _cen), _p(_num(f["reservado"]), _cen), _p(_num(f["disponible"]), _cen),
                      _p(f"${_num(f['precio'])}", _cen), _p(f"${_num(f['valor_entregado'])}", _cen),
                      _p(f"${_num(f['valor_disponible'])}", _cen)])
    if not inventario:
        filas.append([_p("El lote aún no tiene material recibido (solicitud al final del ciclo de compra)."),
                      "", "", "", "", "", "", "", ""])
    t = Table(filas, colWidths=[ancho * x for x in (0.34, 0.06, 0.07, 0.07, 0.07, 0.07, 0.1, 0.11, 0.11)], repeatRows=1)
    t.setStyle(_rejilla([("BACKGROUND", (0, 0), (-1, 0), GRIS)] + ([("SPAN", (0, 1), (-1, 1))] if not inventario else [])))
    h += [_p("Saldo del inventario", _titulo), Spacer(1, 1 * mm), t, Spacer(1, 5 * mm)]

    filas = [[_p(x, _cen) for x in ("N°", "Fecha entrega", "Instructor", "Coordinación", "Ficha", "Artículos entregados",
                                    "Valor", "Legalización")]]
    for e in entregas:
        filas.append([_p(e["id"], _cen), _p(e["fecha_entrega"], _cen), _p(e["instructor"], _peq),
                      _p(e["coordinacion"], _peq), _p(e["ficha"], _peq), _p(e["articulos"], _peq),
                      _p(f"${_num(e['valor'])}", _cen), _p(e["legalizacion"], _peq)])
    if not entregas:
        filas.append([_p("No hay entregas en el periodo."), "", "", "", "", "", "", ""])
    t = Table(filas, colWidths=[ancho * x for x in (0.05, 0.08, 0.15, 0.14, 0.08, 0.3, 0.09, 0.11)], repeatRows=1)
    t.setStyle(_rejilla([("BACKGROUND", (0, 0), (-1, 0), GRIS), ("VALIGN", (0, 1), (-1, -1), "TOP")]
                        + ([("SPAN", (0, 1), (-1, 1))] if not entregas else [])))
    h += [_p("Entregas a instructores", _titulo), Spacer(1, 1 * mm), t, Spacer(1, 3 * mm),
          _p(f"Generado el {date.today():%d/%m/%Y} por el sistema Materiales de Formación.", _peq)]
    doc.build(h)
    return buf.getvalue()
