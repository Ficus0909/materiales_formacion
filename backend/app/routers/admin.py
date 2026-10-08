"""Catálogos administrativos: centros, usuarios, lotes, vigencias, proveedores, estados post-aprobación y parámetros.

Jerarquía: el MANAGER administra los centros, sus administradores y lo que es común a todos (vigencias,
parámetros, estados, índices). El ADMIN de cada centro administra los líderes, lotes y el listado maestro
de su centro."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    ROLES, Articulo, Centro, Cotizacion, EstadoPost, IndiceAjuste, Lote, Parametro, Proveedor, Solicitud,
    SolicitudHistorial, Usuario, Vigencia,
)
from ..security import (
    admin_o_manager, hash_password, solo_admin, solo_manager, usuario_actual, validar_password,
)
from ..services import correo
from ..services.common import actividad, centro_de, get_or_404, notificar, verificar_centro
from ..services.pricing import PARAMETROS_DEFECTO
from .auth import usuario_out

router = APIRouter(tags=["administración"])
NOMBRE_ROL = {"MANAGER": "Manager", "ADMIN": "Administrador / Analista", "LIDER": "Líder de lote"}


# --- Centros de formación -----------------------------------------------
class CentroIn(BaseModel):
    codigo: str
    nombre: str
    regional: str = ""
    activo: bool = True
    # Sólo al crear: carga el listado maestro (lotes y artículos activos) de otro centro.
    # Por defecto se copia el del centro por defecto (CENTRO_CODIGO).
    cargar_listado: bool = True
    listado_desde: int | None = None


def centro_out(db: Session, c: Centro) -> dict:
    usuarios = dict(db.execute(select(Usuario.rol, func.count()).where(Usuario.centro_id == c.id, Usuario.activo.is_(True))
                               .group_by(Usuario.rol)).all())
    return {"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "regional": c.regional, "activo": c.activo,
            "por_defecto": c.codigo == settings.CENTRO_CODIGO,
            "lotes": db.scalar(select(func.count()).select_from(Lote).where(Lote.centro_id == c.id)),
            "articulos": db.scalar(select(func.count()).select_from(Articulo).join(Lote).where(
                Lote.centro_id == c.id, Articulo.activo.is_(True))),
            "administradores": usuarios.get("ADMIN", 0), "lideres": usuarios.get("LIDER", 0)}


def _validar_centro(db: Session, data: CentroIn, cid: int | None = None) -> None:
    if not data.codigo.strip() or not data.nombre.strip():
        raise HTTPException(422, "Código y nombre del centro son obligatorios")
    if db.scalar(select(Centro).where((func.lower(Centro.codigo) == data.codigo.strip().lower())
                                      | (func.lower(Centro.nombre) == data.nombre.strip().lower()),
                                      Centro.id != (cid or 0))):
        raise HTTPException(409, "Ya existe un centro con ese código o nombre")


@router.get("/centros")
def listar_centros(user=Depends(usuario_actual), db: Session = Depends(get_db)):
    stmt = select(Centro).order_by(Centro.nombre)
    if user.rol != "MANAGER":
        stmt = stmt.where(Centro.id == user.centro_id)
    return [centro_out(db, c) for c in db.scalars(stmt)]


def _centro_origen_listado(db: Session, origen_id: int | None) -> Centro | None:
    if origen_id:
        return get_or_404(db, Centro, origen_id, "Centro de origen del listado")
    return db.scalar(select(Centro).where(Centro.codigo == settings.CENTRO_CODIGO)) or db.scalar(
        select(Centro).order_by(Centro.id))


def copiar_listado(db: Session, origen: Centro, destino: Centro) -> dict:
    """Copia los lotes y los artículos activos del listado maestro de un centro a otro.
    No copia cotizaciones, históricos, análisis ni solicitudes: cada centro hace su propio estudio de mercados."""
    lotes = artics = 0
    for l in db.scalars(select(Lote).where(Lote.centro_id == origen.id).order_by(Lote.numero)):
        nuevo = Lote(centro_id=destino.id, numero=l.numero, nombre=l.nombre, abreviatura=l.abreviatura,
                     color=l.color, activo=l.activo)
        db.add(nuevo)
        db.flush()
        lotes += 1
        for a in db.scalars(select(Articulo).where(Articulo.lote_id == l.id, Articulo.activo.is_(True))):
            db.add(Articulo(lote_id=nuevo.id, codigo_unspsc=a.codigo_unspsc, nombre=a.nombre, unidad=a.unidad,
                            descripcion=a.descripcion, activo=True))
            artics += 1
    return {"lotes": lotes, "articulos": artics, "origen": origen.nombre}


@router.post("/centros", status_code=201)
def crear_centro(data: CentroIn, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    _validar_centro(db, data)
    origen = _centro_origen_listado(db, data.listado_desde) if data.cargar_listado else None
    c = Centro(codigo=data.codigo.strip(), nombre=data.nombre.strip(), regional=data.regional.strip(), activo=data.activo)
    db.add(c)
    db.flush()
    copiado = copiar_listado(db, origen, c) if origen else None
    actividad(db, manager, f"Creó el centro de formación {c.nombre}"
              + (f" con el listado maestro de {origen.nombre} ({copiado['articulos']} artículos en "
                 f"{copiado['lotes']} lotes)" if copiado else " sin listado maestro"))
    db.commit()
    return {**centro_out(db, c), "listado_copiado": copiado}


class CargarListadoIn(BaseModel):
    listado_desde: int | None = None  # None = centro por defecto


@router.post("/centros/{cid}/cargar-listado")
def cargar_listado(cid: int, data: CargarListadoIn, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    """Carga el listado maestro de otro centro en un centro existente que aún no tiene lotes."""
    c = get_or_404(db, Centro, cid, "Centro")
    if db.scalar(select(func.count()).select_from(Lote).where(Lote.centro_id == cid)):
        raise HTTPException(409, "El centro ya tiene lotes: su administrador puede actualizar el listado con el importador")
    origen = _centro_origen_listado(db, data.listado_desde)
    if not origen or origen.id == cid:
        raise HTTPException(422, "Elija otro centro de origen para el listado maestro")
    copiado = copiar_listado(db, origen, c)
    if not copiado["articulos"]:
        raise HTTPException(422, f"{origen.nombre} no tiene artículos activos en su listado maestro")
    actividad(db, manager, f"Cargó en {c.nombre} el listado maestro de {origen.nombre} "
                           f"({copiado['articulos']} artículos en {copiado['lotes']} lotes)", centro_id=c.id)
    db.commit()
    return {**centro_out(db, c), "listado_copiado": copiado}


@router.put("/centros/{cid}")
def editar_centro(cid: int, data: CentroIn, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    c = get_or_404(db, Centro, cid, "Centro")
    _validar_centro(db, data, cid)
    if c.activo and not data.activo:
        actividad(db, manager, f"Desactivó el centro de formación {c.nombre}: sus usuarios ya no pueden ingresar")
    c.codigo, c.nombre, c.regional, c.activo = data.codigo.strip(), data.nombre.strip(), data.regional.strip(), data.activo
    db.commit()
    return centro_out(db, c)


@router.delete("/centros/{cid}")
def eliminar_centro(cid: int, _=Depends(solo_manager), db: Session = Depends(get_db)):
    c = get_or_404(db, Centro, cid, "Centro")
    if centro_out(db, c)["lotes"] or db.scalar(select(func.count()).select_from(Usuario).where(Usuario.centro_id == cid)):
        raise HTTPException(409, "El centro tiene lotes o usuarios: sólo puede desactivarse")
    db.delete(c)
    db.commit()
    return {"ok": True}


# --- Usuarios ------------------------------------------------------------
class UsuarioIn(BaseModel):
    nombre: str
    email: EmailStr
    rol: str
    centro_id: int | None = None
    lote_id: int | None = None
    activo: bool = True
    password: str | None = None

    @field_validator("rol")
    @classmethod
    def _rol(cls, v):
        if v not in ROLES:
            raise ValueError("Rol inválido")
        return v


def _puede_gestionar(actor: Usuario, rol: str, centro_id: int | None) -> None:
    """El manager gestiona a todos; el administrador sólo a los líderes de su centro."""
    if actor.rol == "MANAGER":
        return
    if rol != "LIDER" or centro_id != actor.centro_id:
        raise HTTPException(403, "Sólo puede gestionar los líderes de su centro. "
                                 "Los administradores los gestiona el manager.")


def _validar_usuario(db: Session, data: UsuarioIn, actor: Usuario, uid: int | None = None) -> None:
    if actor.rol == "ADMIN":
        data.centro_id = actor.centro_id
    if data.rol == "MANAGER":
        data.centro_id, data.lote_id = None, None
    else:
        if not data.centro_id:
            raise HTTPException(422, "Los administradores y líderes deben pertenecer a un centro de formación")
        if not get_or_404(db, Centro, data.centro_id, "Centro").activo:
            raise HTTPException(409, "El centro de formación está inactivo")
    _puede_gestionar(actor, data.rol, data.centro_id)
    if data.rol == "LIDER":
        if not data.lote_id:
            raise HTTPException(422, "Un Líder de Lote debe tener un lote asignado")
        if get_or_404(db, Lote, data.lote_id, "Lote").centro_id != data.centro_id:
            raise HTTPException(422, "El lote asignado no pertenece al centro del usuario")
    else:
        data.lote_id = None
    existe = db.scalar(select(Usuario).where(func.lower(Usuario.email) == data.email.lower(), Usuario.id != (uid or 0)))
    if existe:
        raise HTTPException(409, "Ya existe un usuario con ese correo")


def _tiene_historial(db: Session, uid: int) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Solicitud).where(Solicitud.lider_id == uid)) or
                db.scalar(select(func.count()).select_from(SolicitudHistorial).where(SolicitudHistorial.usuario_id == uid)) or
                db.scalar(select(func.count()).select_from(Cotizacion).where(Cotizacion.cargada_por == uid)))


def _correo_credenciales(db: Session, u: Usuario, password: str, nuevo: bool) -> None:
    centro = db.get(Centro, u.centro_id).nombre if u.centro_id else ""
    rol = {"MANAGER": "Manager de los centros de formación",
           "ADMIN": f"Administrador / Analista del {centro}",
           "LIDER": f"Líder del lote {db.get(Lote, u.lote_id).nombre if u.lote_id else ''} ({centro})"}[u.rol]
    correo.encolar(
        db, u.email,
        "Su acceso al sistema" if nuevo else "Su contraseña fue restablecida",
        f"Hola {u.nombre}:\n\n"
        + ("Se le creó una cuenta" if nuevo else "Se le asignó una nueva contraseña temporal")
        + f" como {rol}.\n\nUsuario: {u.email}\nContraseña temporal: {password}\n\n"
        "Por seguridad, el sistema le pedirá cambiarla en su primer ingreso.",
        "/login", "Ingresar")


@router.get("/usuarios")
def listar_usuarios(q: str = "", rol: str = "", centro_id: int | None = None, user=Depends(admin_o_manager),
                    db: Session = Depends(get_db)):
    stmt = select(Usuario).order_by(Usuario.nombre)
    centro = centro_de(user, centro_id)
    if centro:
        stmt = stmt.where(Usuario.centro_id == centro)
    if q:
        stmt = stmt.where((Usuario.nombre.ilike(f"%{q}%")) | (Usuario.email.ilike(f"%{q}%")))
    if rol:
        stmt = stmt.where(Usuario.rol == rol)
    return [usuario_out(u) for u in db.scalars(stmt)]


@router.post("/usuarios", status_code=201)
def crear_usuario(data: UsuarioIn, actor=Depends(admin_o_manager), db: Session = Depends(get_db)):
    _validar_usuario(db, data, actor)
    if not data.password:
        raise HTTPException(422, "Debe indicar una contraseña temporal")
    validar_password(data.password)
    u = Usuario(nombre=data.nombre.strip(), email=data.email.lower(), rol=data.rol, centro_id=data.centro_id,
                lote_id=data.lote_id, activo=data.activo, password_hash=hash_password(data.password),
                debe_cambiar_password=True)
    db.add(u)
    actividad(db, actor, f"Creó el usuario {u.nombre} ({NOMBRE_ROL[u.rol]})", centro_id=data.centro_id)
    _correo_credenciales(db, u, data.password, nuevo=True)
    db.commit()
    db.refresh(u)
    return {**usuario_out(u), "correo_enviado": correo.habilitado()}


@router.put("/usuarios/{uid}")
def editar_usuario(uid: int, data: UsuarioIn, actor=Depends(admin_o_manager), db: Session = Depends(get_db)):
    u = get_or_404(db, Usuario, uid, "Usuario")
    _puede_gestionar(actor, u.rol, u.centro_id)
    _validar_usuario(db, data, actor, uid)
    if u.id == actor.id and (data.rol != actor.rol or not data.activo):
        raise HTTPException(409, "No puede cambiarse a sí mismo el rol ni desactivarse")
    if data.centro_id != u.centro_id and _tiene_historial(db, uid):
        raise HTTPException(409, "El usuario tiene solicitudes o cotizaciones en su centro: no se puede trasladar. "
                                 "Desactívelo y cree un usuario nuevo en el otro centro.")
    u.nombre, u.email, u.rol, u.activo = data.nombre.strip(), data.email.lower(), data.rol, data.activo
    u.centro_id, u.lote_id = data.centro_id, data.lote_id
    if data.password:
        validar_password(data.password)
        u.password_hash, u.debe_cambiar_password = hash_password(data.password), True
        u.intentos_fallidos, u.bloqueado_hasta = 0, None
        _correo_credenciales(db, u, data.password, nuevo=False)
    db.commit()
    db.refresh(u)
    return {**usuario_out(u), "correo_enviado": bool(data.password) and correo.habilitado()}


@router.delete("/usuarios/{uid}")
def eliminar_usuario(uid: int, actor=Depends(admin_o_manager), db: Session = Depends(get_db)):
    u = get_or_404(db, Usuario, uid, "Usuario")
    _puede_gestionar(actor, u.rol, u.centro_id)
    if u.id == actor.id:
        raise HTTPException(409, "No puede eliminarse a sí mismo")
    if _tiene_historial(db, uid):
        raise HTTPException(409, "El usuario tiene solicitudes o cotizaciones asociadas: sólo puede desactivarse")
    db.delete(u)
    db.commit()
    return {"ok": True}


# --- Lotes (propios de cada centro) --------------------------------------
class LoteIn(BaseModel):
    numero: int
    nombre: str
    abreviatura: str
    color: str = "#39A909"
    activo: bool = True


def _lote_duplicado(db: Session, centro_id: int, data: LoteIn, lid: int = 0) -> None:
    if db.scalar(select(Lote).where(Lote.centro_id == centro_id, Lote.id != lid,
                                    (Lote.numero == data.numero) | (Lote.abreviatura == data.abreviatura))):
        raise HTTPException(409, "Ya existe un lote con ese número o abreviatura en el centro")


@router.get("/lotes")
def listar_lotes(centro_id: int | None = None, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    centro = centro_de(user, centro_id)
    conteo = dict(db.execute(select(Articulo.lote_id, func.count()).where(Articulo.activo.is_(True))
                             .group_by(Articulo.lote_id)).all())
    stmt = select(Lote).order_by(Lote.centro_id, Lote.numero)
    if centro:
        stmt = stmt.where(Lote.centro_id == centro)
    out = []
    for l in db.scalars(stmt):
        out.append({"id": l.id, "centro_id": l.centro_id, "centro": l.centro.nombre, "numero": l.numero,
                    "nombre": l.nombre, "abreviatura": l.abreviatura, "color": l.color, "activo": l.activo,
                    "articulos": conteo.get(l.id, 0),
                    "lideres": [{"id": u.id, "nombre": u.nombre} for u in l.lideres if u.activo]})
    return out


@router.post("/lotes", status_code=201)
def crear_lote(data: LoteIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    _lote_duplicado(db, admin.centro_id, data)
    l = Lote(**data.model_dump(), centro_id=admin.centro_id)
    db.add(l)
    db.commit()
    return {"id": l.id}


@router.put("/lotes/{lid}")
def editar_lote(lid: int, data: LoteIn, admin=Depends(solo_admin), db: Session = Depends(get_db)):
    l = get_or_404(db, Lote, lid, "Lote")
    verificar_centro(admin, l.centro_id, "El lote")
    _lote_duplicado(db, l.centro_id, data, lid)
    for k, v in data.model_dump().items():
        setattr(l, k, v)
    db.commit()
    return {"ok": True}


# --- Vigencias (comunes a todos los centros; las gestiona el manager) ----
class VigenciaIn(BaseModel):
    codigo: str
    anio: int
    fecha_inicio: date
    fecha_cierre: date


def vigencia_out(db: Session, v: Vigencia, centro_id: int | None = None) -> dict:
    """Los conteos se limitan al centro indicado (None = todos)."""
    sols = select(func.count()).select_from(Solicitud).join(Lote).where(Solicitud.vigencia_id == v.id)
    cots = select(func.count()).select_from(Cotizacion).join(Lote).where(Cotizacion.vigencia_id == v.id)
    if centro_id:
        sols, cots = sols.where(Lote.centro_id == centro_id), cots.where(Lote.centro_id == centro_id)
    return {
        "id": v.id, "codigo": v.codigo, "anio": v.anio, "estado": v.estado,
        "fecha_inicio": v.fecha_inicio.isoformat(), "fecha_cierre": v.fecha_cierre.isoformat(),
        "solicitudes": db.scalar(sols), "cotizaciones": db.scalar(cots),
    }


def _validar_vigencia(db: Session, data: VigenciaIn, vid: int | None = None):
    if data.fecha_cierre <= data.fecha_inicio:
        raise HTTPException(422, "La fecha de cierre debe ser posterior a la de inicio")
    if db.scalar(select(Vigencia).where(Vigencia.codigo == data.codigo, Vigencia.id != (vid or 0))):
        raise HTTPException(409, "Ya existe una vigencia con ese código")


@router.get("/vigencias")
def listar_vigencias(user=Depends(usuario_actual), db: Session = Depends(get_db)):
    centro = centro_de(user)
    return [vigencia_out(db, v, centro) for v in db.scalars(select(Vigencia).order_by(Vigencia.fecha_inicio.desc()))]


@router.get("/vigencias/activa")
def vigencia_activa(user=Depends(usuario_actual), db: Session = Depends(get_db)):
    v = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    return vigencia_out(db, v, centro_de(user)) if v else None


@router.post("/vigencias", status_code=201)
def crear_vigencia(data: VigenciaIn, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    _validar_vigencia(db, data)
    v = Vigencia(**data.model_dump(), estado="PROGRAMADA")
    db.add(v)
    actividad(db, manager, f"Creó la vigencia {v.codigo}")
    db.commit()
    return vigencia_out(db, v)


@router.put("/vigencias/{vid}")
def editar_vigencia(vid: int, data: VigenciaIn, _=Depends(solo_manager), db: Session = Depends(get_db)):
    v = get_or_404(db, Vigencia, vid, "Vigencia")
    if v.estado == "CERRADA":
        raise HTTPException(409, "Una vigencia cerrada no se puede editar")
    _validar_vigencia(db, data, vid)
    if v.estado == "ABIERTA" and (data.codigo != v.codigo or data.anio != v.anio or data.fecha_inicio != v.fecha_inicio):
        raise HTTPException(409, "En una vigencia abierta sólo se puede modificar (extender) la fecha de cierre")
    for k, val in data.model_dump().items():
        setattr(v, k, val)
    db.commit()
    return vigencia_out(db, v)


def _usuarios_operativos(db: Session, rol: str) -> list[int]:
    """Usuarios activos de un rol en centros activos."""
    return list(db.scalars(select(Usuario.id).join(Centro, Usuario.centro_id == Centro.id).where(
        Usuario.rol == rol, Usuario.activo.is_(True), Centro.activo.is_(True))))


@router.post("/vigencias/{vid}/abrir")
def abrir_vigencia(vid: int, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    v = get_or_404(db, Vigencia, vid, "Vigencia")
    if v.estado != "PROGRAMADA":
        raise HTTPException(409, "Sólo se puede abrir una vigencia programada")
    otra = db.scalar(select(Vigencia).where(Vigencia.estado == "ABIERTA"))
    if otra:
        raise HTTPException(409, f"Ya existe una vigencia abierta ({otra.codigo}). Ciérrela primero.")
    v.estado = "ABIERTA"
    notificar(db, _usuarios_operativos(db, "LIDER"), f"Vigencia {v.codigo} abierta",
              f"Ya puede cargar cotizaciones y crear su solicitud hasta el {v.fecha_cierre:%d/%m/%Y}.", "/lider")
    notificar(db, _usuarios_operativos(db, "ADMIN"), f"Vigencia {v.codigo} abierta",
              f"Los líderes de su centro ya pueden cotizar y solicitar hasta el {v.fecha_cierre:%d/%m/%Y}.", "/admin")
    actividad(db, manager, f"Abrió la vigencia {v.codigo}")
    db.commit()
    return vigencia_out(db, v)


@router.post("/vigencias/{vid}/cerrar")
def cerrar_vigencia(vid: int, manager=Depends(solo_manager), db: Session = Depends(get_db)):
    v = get_or_404(db, Vigencia, vid, "Vigencia")
    if v.estado != "ABIERTA":
        raise HTTPException(409, "Sólo se puede cerrar una vigencia abierta")
    v.estado = "CERRADA"
    canceladas = 0
    for s in db.scalars(select(Solicitud).where(Solicitud.vigencia_id == vid,
                                                Solicitud.estado.in_(("BORRADOR", "DEVUELTA")))):
        db.add(SolicitudHistorial(solicitud_id=s.id, estado_anterior=s.estado, estado_nuevo="CANCELADA",
                                  usuario_id=manager.id, observaciones=f"Cancelada por cierre de la vigencia {v.codigo}"))
        s.estado = "CANCELADA"
        notificar(db, [s.lider_id], "Solicitud cancelada",
                  f"Su solicitud no fue enviada antes del cierre de la vigencia {v.codigo}.", f"/lider/seguimiento")
        canceladas += 1
    actividad(db, manager, f"Cerró la vigencia {v.codigo} ({canceladas} solicitudes no enviadas canceladas)")
    db.commit()
    return {**vigencia_out(db, v), "canceladas": canceladas}


@router.delete("/vigencias/{vid}")
def eliminar_vigencia(vid: int, _=Depends(solo_manager), db: Session = Depends(get_db)):
    v = get_or_404(db, Vigencia, vid, "Vigencia")
    out = vigencia_out(db, v)
    if out["solicitudes"] or out["cotizaciones"]:
        raise HTTPException(409, "No se puede eliminar una vigencia con solicitudes o cotizaciones")
    db.delete(v)
    db.commit()
    return {"ok": True}


# --- Proveedores ---------------------------------------------------------
class ProveedorIn(BaseModel):
    nit: str
    razon_social: str
    contacto: str = ""
    email: str = ""
    telefono: str = ""
    activo: bool = True


def proveedor_out(p: Proveedor) -> dict:
    return {k: getattr(p, k) for k in ("id", "nit", "razon_social", "contacto", "email", "telefono", "activo")}


@router.get("/proveedores")
def listar_proveedores(q: str = "", _=Depends(usuario_actual), db: Session = Depends(get_db)):
    stmt = select(Proveedor).order_by(Proveedor.razon_social)
    if q:
        stmt = stmt.where(Proveedor.razon_social.ilike(f"%{q}%") | Proveedor.nit.ilike(f"%{q}%"))
    return [proveedor_out(p) for p in db.scalars(stmt)]


@router.post("/proveedores", status_code=201)
def crear_proveedor(data: ProveedorIn, user=Depends(usuario_actual), db: Session = Depends(get_db)):
    """Admin y líderes pueden registrar proveedores (el líder es quien gestiona las cotizaciones)."""
    nit = data.nit.strip()
    if not nit or not data.razon_social.strip():
        raise HTTPException(422, "NIT y razón social son obligatorios")
    if db.scalar(select(Proveedor).where(Proveedor.nit == nit)):
        raise HTTPException(409, "Ya existe un proveedor con ese NIT")
    p = Proveedor(**{**data.model_dump(), "nit": nit, "razon_social": data.razon_social.strip()})
    db.add(p)
    actividad(db, user, f"Registró el proveedor {p.razon_social}")
    db.commit()
    return proveedor_out(p)


@router.put("/proveedores/{pid}")
def editar_proveedor(pid: int, data: ProveedorIn, _=Depends(admin_o_manager), db: Session = Depends(get_db)):
    p = get_or_404(db, Proveedor, pid, "Proveedor")
    if db.scalar(select(Proveedor).where(Proveedor.nit == data.nit.strip(), Proveedor.id != pid)):
        raise HTTPException(409, "Ya existe un proveedor con ese NIT")
    for k, v in data.model_dump().items():
        setattr(p, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return proveedor_out(p)


# --- Estados post-aprobación (comunes; los gestiona el manager) ---------
class EstadoPostIn(BaseModel):
    nombre: str
    color: str = "#71277A"
    activo: bool = True


def _estados(db):
    return [{"id": e.id, "nombre": e.nombre, "color": e.color, "orden": e.orden, "activo": e.activo}
            for e in db.scalars(select(EstadoPost).order_by(EstadoPost.orden))]


@router.get("/estados-post")
def listar_estados(_=Depends(usuario_actual), db: Session = Depends(get_db)):
    return _estados(db)


@router.post("/estados-post", status_code=201)
def crear_estado(data: EstadoPostIn, _=Depends(solo_manager), db: Session = Depends(get_db)):
    if db.scalar(select(EstadoPost).where(EstadoPost.nombre == data.nombre.strip())):
        raise HTTPException(409, "Ya existe un estado con ese nombre")
    orden = (db.scalar(select(func.max(EstadoPost.orden))) or 0) + 1
    db.add(EstadoPost(nombre=data.nombre.strip(), color=data.color, activo=data.activo, orden=orden))
    db.commit()
    return _estados(db)


@router.put("/estados-post/{eid}")
def editar_estado(eid: int, data: EstadoPostIn, _=Depends(solo_manager), db: Session = Depends(get_db)):
    e = get_or_404(db, EstadoPost, eid, "Estado")
    e.nombre, e.color, e.activo = data.nombre.strip(), data.color, data.activo
    db.commit()
    return _estados(db)


@router.post("/estados-post/reordenar")
def reordenar_estados(ids: list[int], _=Depends(solo_manager), db: Session = Depends(get_db)):
    en_curso = db.scalar(select(func.count()).select_from(Solicitud).join(Vigencia).where(
        Vigencia.estado == "ABIERTA", Solicitud.estado_post_id.is_not(None)))
    if en_curso:
        raise HTTPException(409, "No se puede reordenar mientras haya solicitudes de la vigencia abierta en el ciclo de compra")
    for i, eid in enumerate(ids, 1):
        get_or_404(db, EstadoPost, eid, "Estado").orden = i
    db.commit()
    return _estados(db)


# --- Parámetros e índices (comunes; los gestiona el manager) -----------
@router.get("/parametros")
def listar_parametros(_=Depends(usuario_actual), db: Session = Depends(get_db)):
    guardados = {p.clave: p.valor for p in db.scalars(select(Parametro))}
    return [{"clave": k, "valor": guardados.get(k, d), "descripcion": desc} for k, (d, desc) in PARAMETROS_DEFECTO.items()]


@router.put("/parametros")
def guardar_parametros(valores: dict[str, str], admin=Depends(solo_manager), db: Session = Depends(get_db)):
    for k, v in valores.items():
        if k not in PARAMETROS_DEFECTO:
            raise HTTPException(422, f"Parámetro desconocido: {k}")
        try:
            float(v)
        except ValueError:
            raise HTTPException(422, f"El parámetro {k} debe ser numérico")
        p = db.get(Parametro, k)
        if p:
            p.valor = str(v)
        else:
            db.add(Parametro(clave=k, valor=str(v), descripcion=PARAMETROS_DEFECTO[k][1]))
    actividad(db, admin, "Actualizó los parámetros del análisis de precios")
    db.commit()
    return listar_parametros(admin, db)


class IndiceIn(BaseModel):
    anio: int
    ipc: float
    puntos_adicionales: float = 0.02


@router.get("/indices")
def listar_indices(_=Depends(usuario_actual), db: Session = Depends(get_db)):
    return [{"anio": i.anio, "ipc": i.ipc, "puntos_adicionales": i.puntos_adicionales}
            for i in db.scalars(select(IndiceAjuste).order_by(IndiceAjuste.anio.desc()))]


@router.put("/indices")
def guardar_indice(data: IndiceIn, _=Depends(solo_manager), db: Session = Depends(get_db)):
    if not (-0.5 < data.ipc < 1 and 0 <= data.puntos_adicionales < 1):
        raise HTTPException(422, "Use valores decimales (ej. 0.051 para 5,1 %)")
    i = db.get(IndiceAjuste, data.anio)
    if i:
        i.ipc, i.puntos_adicionales = data.ipc, data.puntos_adicionales
    else:
        db.add(IndiceAjuste(**data.model_dump()))
    db.commit()
    return listar_indices(_, db)


# --- Correo --------------------------------------------------------------
@router.get("/correo/estado")
def estado_correo(_=Depends(admin_o_manager)):
    from ..config import settings
    return {"habilitado": correo.habilitado(), "remitente": settings.SMTP_FROM, "servidor": settings.SMTP_HOST,
            "puerto": settings.SMTP_PORT, "app_url": settings.APP_URL}


@router.post("/correo/prueba")
def probar_correo(admin=Depends(admin_o_manager)):
    """Envío síncrono a la cuenta del administrador para validar la configuración SMTP."""
    if not correo.habilitado():
        raise HTTPException(409, "El correo no está configurado (variables SMTP_HOST y SMTP_FROM)")
    try:
        correo.enviar_lote([{
            "para": admin.email, "asunto": "[Materiales SENA] Correo de prueba",
            "html": correo.plantilla("Correo de prueba", "La configuración de correo funciona correctamente."),
            "texto": "La configuración de correo funciona correctamente.",
        }])
    except Exception as e:
        raise HTTPException(502, f"No se pudo enviar: {e}")
    return {"ok": True, "para": admin.email}
