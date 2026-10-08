"""Modelo de datos. Ver docs/REGLAS_NEGOCIO.md para el porqué de cada entidad."""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# --- Catálogos de estados -------------------------------------------------
ROLES = ("MANAGER", "ADMIN", "LIDER")
VIGENCIA_ESTADOS = ("PROGRAMADA", "ABIERTA", "CERRADA")
SOLICITUD_ESTADOS = ("BORRADOR", "ENVIADA", "EN_REVISION", "DEVUELTA", "APROBADA", "RECHAZADA", "CANCELADA")
METODOS_PRECIO = ("COTIZACIONES", "HISTORICOS", "EXPERTO")


class Centro(Base):
    """Centro de formación (sucursal). Cada centro tiene su propio listado maestro, lotes, usuarios,
    cotizaciones y solicitudes. El manager está por encima de los administradores de todos los centros."""
    __tablename__ = "centros"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(160), unique=True)
    regional: Mapped[str] = mapped_column(String(120), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Lote(Base):
    __tablename__ = "lotes"
    __table_args__ = (UniqueConstraint("centro_id", "numero", name="uq_lote_centro_numero"),
                      UniqueConstraint("centro_id", "abreviatura", name="uq_lote_centro_abrev"))
    id: Mapped[int] = mapped_column(primary_key=True)
    centro_id: Mapped[int] = mapped_column(ForeignKey("centros.id", ondelete="RESTRICT"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    nombre: Mapped[str] = mapped_column(String(120))
    abreviatura: Mapped[str] = mapped_column(String(10))
    color: Mapped[str] = mapped_column(String(9), default="#39A909")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    centro: Mapped[Centro] = relationship()
    lideres: Mapped[list["Usuario"]] = relationship(back_populates="lote")


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    rol: Mapped[str] = mapped_column(String(10))
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id", ondelete="RESTRICT"), index=True)  # None = MANAGER
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes.id", ondelete="RESTRICT"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    centro: Mapped[Centro | None] = relationship()
    lote: Mapped[Lote | None] = relationship(back_populates="lideres")


class Vigencia(Base):
    __tablename__ = "vigencias"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    anio: Mapped[int] = mapped_column(Integer)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_cierre: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(12), default="PROGRAMADA")
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Articulo(Base):
    """Ítem del listado maestro de fichas técnicas."""
    __tablename__ = "articulos"
    __table_args__ = (UniqueConstraint("lote_id", "nombre", name="uq_articulo_lote_nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id", ondelete="RESTRICT"), index=True)
    codigo_unspsc: Mapped[str] = mapped_column(String(8), index=True)
    nombre: Mapped[str] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(10))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    lote: Mapped[Lote] = relationship()


class PropuestaArticulo(Base):
    """El líder propone un artículo nuevo; el administrador asigna UNSPSC y lo aprueba."""
    __tablename__ = "propuestas_articulo"
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id", ondelete="RESTRICT"))
    lider_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nombre: Mapped[str] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(10))
    descripcion: Mapped[str] = mapped_column(Text)
    justificacion: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")  # PENDIENTE | APROBADA | RECHAZADA
    respuesta: Mapped[str] = mapped_column(Text, default="")
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lote: Mapped[Lote] = relationship()
    lider: Mapped["Usuario"] = relationship()


class Proveedor(Base):
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str] = mapped_column(String(20), unique=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    contacto: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    telefono: Mapped[str] = mapped_column(String(40), default="")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Cotizacion(Base):
    """Una cotización = un documento (PDF) de UN proveedor, para UN lote, en UNA vigencia,
    con precios para muchos artículos (CotizacionItem)."""
    __tablename__ = "cotizaciones"
    __table_args__ = (UniqueConstraint("vigencia_id", "lote_id", "proveedor_id", name="uq_cotizacion"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vigencia_id: Mapped[int] = mapped_column(ForeignKey("vigencias.id", ondelete="RESTRICT"), index=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id", ondelete="RESTRICT"), index=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id", ondelete="RESTRICT"))
    etiqueta: Mapped[str] = mapped_column(String(5))  # P1, P2, ... dentro de (vigencia, lote)
    fecha: Mapped[date] = mapped_column(Date)
    pdf_path: Mapped[str] = mapped_column(String(300))
    pdf_nombre: Mapped[str] = mapped_column(String(200))
    cargada_por: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    proveedor: Mapped[Proveedor] = relationship()
    lote: Mapped[Lote] = relationship()
    items: Mapped[list["CotizacionItem"]] = relationship(back_populates="cotizacion", cascade="all, delete-orphan")


class CotizacionItem(Base):
    __tablename__ = "cotizacion_items"
    __table_args__ = (UniqueConstraint("cotizacion_id", "articulo_id", name="uq_cot_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id", ondelete="CASCADE"), index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="RESTRICT"), index=True)
    precio: Mapped[float] = mapped_column(Float)  # unitario, IVA incluido, COP
    excluido: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_exclusion: Mapped[str] = mapped_column(String(300), default="")

    cotizacion: Mapped[Cotizacion] = relationship(back_populates="items")


class PrecioHistorico(Base):
    """Precio de contratación de un año anterior (valor nominal, sin indexar)."""
    __tablename__ = "precios_historicos"
    __table_args__ = (UniqueConstraint("articulo_id", "anio", name="uq_hist"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"), index=True)
    anio: Mapped[int] = mapped_column(Integer)
    precio: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String(120), default="")


class IndiceAjuste(Base):
    """IPC anual + puntos adicionales, para indexar históricos (PAAG)."""
    __tablename__ = "indices_ajuste"
    anio: Mapped[int] = mapped_column(Integer, primary_key=True)
    ipc: Mapped[float] = mapped_column(Float)  # 0.051 = 5,1 %
    puntos_adicionales: Mapped[float] = mapped_column(Float, default=0.02)


class AnalisisPrecio(Base):
    """Decisión del analista sobre el precio de un artículo en una vigencia
    (sólo existe si el analista sobrescribe el cálculo automático)."""
    __tablename__ = "analisis_precios"
    __table_args__ = (UniqueConstraint("vigencia_id", "articulo_id", name="uq_analisis"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vigencia_id: Mapped[int] = mapped_column(ForeignKey("vigencias.id", ondelete="CASCADE"))
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"))
    metodo: Mapped[str | None] = mapped_column(String(15))  # None = automático
    precio_experto: Mapped[float | None] = mapped_column(Float)
    justificacion: Mapped[str] = mapped_column(Text, default="")
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class EstadoPost(Base):
    __tablename__ = "estados_post"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#71277A")
    orden: Mapped[int] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Solicitud(Base):
    __tablename__ = "solicitudes"
    __table_args__ = (UniqueConstraint("vigencia_id", "lote_id", name="uq_solicitud_vigencia_lote"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vigencia_id: Mapped[int] = mapped_column(ForeignKey("vigencias.id", ondelete="RESTRICT"), index=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes.id", ondelete="RESTRICT"), index=True)
    lider_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(12), default="BORRADOR", index=True)
    estado_post_id: Mapped[int | None] = mapped_column(ForeignKey("estados_post.id"))
    reenvios: Mapped[int] = mapped_column(Integer, default=0)
    observaciones_admin: Mapped[str] = mapped_column(Text, default="")
    fecha_envio: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime)
    creado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    vigencia: Mapped[Vigencia] = relationship()
    lote: Mapped[Lote] = relationship()
    lider: Mapped[Usuario] = relationship()
    estado_post: Mapped[EstadoPost | None] = relationship()
    items: Mapped[list["SolicitudItem"]] = relationship(back_populates="solicitud", cascade="all, delete-orphan")


class SolicitudItem(Base):
    __tablename__ = "solicitud_items"
    __table_args__ = (UniqueConstraint("solicitud_id", "articulo_id", name="uq_sol_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id", ondelete="CASCADE"), index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="RESTRICT"))
    cantidad: Mapped[float] = mapped_column(Float, default=1)
    observacion: Mapped[str] = mapped_column(String(300), default="")
    precio_aprobado: Mapped[float | None] = mapped_column(Float)  # se congela al aprobar

    solicitud: Mapped[Solicitud] = relationship(back_populates="items")
    articulo: Mapped[Articulo] = relationship()


class SolicitudHistorial(Base):
    """Bitácora inmutable de cambios de estado."""
    __tablename__ = "solicitud_historial"
    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id", ondelete="CASCADE"), index=True)
    estado_anterior: Mapped[str] = mapped_column(String(60), default="")
    estado_nuevo: Mapped[str] = mapped_column(String(60))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    observaciones: Mapped[str] = mapped_column(Text, default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    usuario: Mapped[Usuario] = relationship()


class Parametro(Base):
    __tablename__ = "parametros"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(String(300), default="")


class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    titulo: Mapped[str] = mapped_column(String(160))
    mensaje: Mapped[str] = mapped_column(Text, default="")
    enlace: Mapped[str] = mapped_column(String(200), default="")
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Actividad(Base):
    """Bitácora general para el panel de actividad reciente y auditoría."""
    __tablename__ = "actividad"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id", ondelete="SET NULL"), index=True)  # None = global
    accion: Mapped[str] = mapped_column(String(300))
    enlace: Mapped[str] = mapped_column(String(200), default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    usuario: Mapped[Usuario | None] = relationship()
