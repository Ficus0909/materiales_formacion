from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Actividad, Lote, Notificacion, Usuario, Vigencia
from . import correo


def notificar(db: Session, usuarios: list[int], titulo: str, mensaje: str = "", enlace: str = "") -> None:
    """Notificación en la aplicación + correo (se envía sólo si la transacción se confirma)."""
    for uid in set(usuarios):
        db.add(Notificacion(usuario_id=uid, titulo=titulo, mensaje=mensaje, enlace=enlace))
        u = db.get(Usuario, uid)
        if u and u.activo:
            correo.encolar(db, u.email, titulo, mensaje, enlace)


def notificar_admins(db: Session, centro_id: int, titulo: str, mensaje: str = "", enlace: str = "") -> None:
    """Notifica a los administradores del centro."""
    ids = db.scalars(select(Usuario.id).where(Usuario.rol == "ADMIN", Usuario.centro_id == centro_id,
                                              Usuario.activo.is_(True))).all()
    notificar(db, list(ids), titulo, mensaje, enlace)


def actividad(db: Session, usuario: Usuario | None, accion: str, enlace: str = "", centro_id: int | None = None) -> None:
    """Registra en la bitácora. Por defecto queda en el centro del usuario (None para acciones globales del manager)."""
    db.add(Actividad(usuario_id=usuario.id if usuario else None, accion=accion, enlace=enlace,
                     centro_id=centro_id or (usuario.centro_id if usuario else None)))


def vigencia_abierta(db: Session, requerida: bool = True) -> Vigencia | None:
    v = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    if requerida and not v:
        raise HTTPException(409, "No hay una vigencia abierta. El administrador debe abrir una vigencia.")
    return v


def lote_del_lider(user: Usuario) -> int:
    if not user.lote_id:
        raise HTTPException(409, "Su usuario no tiene un lote asignado. Contacte al administrador.")
    return user.lote_id


def centro_de(user: Usuario, centro_id: int | None = None) -> int | None:
    """Centro sobre el que consulta el usuario: el propio para administradores y líderes;
    el manager puede elegir uno (None = todos los centros)."""
    if user.rol == "MANAGER":
        return centro_id
    if not user.centro_id:
        raise HTTPException(409, "Su usuario no tiene un centro de formación asignado. Contacte al manager.")
    return user.centro_id


def verificar_centro(user: Usuario, centro_id: int, que: str = "El registro") -> None:
    if user.rol != "MANAGER" and centro_id != user.centro_id:
        raise HTTPException(403, f"{que} pertenece a otro centro de formación")


def lote_accesible(db: Session, user: Usuario, lote_id: int | None) -> Lote:
    """Lote que el usuario puede consultar: el líder sólo el suyo, el administrador los de su centro."""
    if user.rol == "LIDER":
        lote_id = lote_del_lider(user)
    if not lote_id:
        raise HTTPException(422, "Indique el lote")
    lote = get_or_404(db, Lote, lote_id, "Lote")
    verificar_centro(user, lote.centro_id, "El lote")
    return lote


def lotes_en_operacion():
    """Subconsulta de los lotes con al menos un líder activo. Un lote copiado del listado maestro
    entra en operación (tableros y reportes) cuando el administrador le asigna un líder."""
    return select(Usuario.lote_id).where(Usuario.rol == "LIDER", Usuario.activo.is_(True), Usuario.lote_id.is_not(None))


def get_or_404(db: Session, model, id_: int, nombre: str = "Registro"):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{nombre} no encontrado")
    return obj
