from datetime import datetime, timedelta

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Centro, Coordinacion, Usuario
from ..security import crear_token, hash_password, requiere, usuario_actual, validar_password, verify_password
from ..services import correo
from ..services.common import notificar

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class CambioIn(BaseModel):
    actual: str
    nueva: str


def usuario_out(u: Usuario) -> dict:
    return {
        "id": u.id, "nombre": u.nombre, "email": u.email, "rol": u.rol, "activo": u.activo,
        "centro_id": u.centro_id, "centro": {"id": u.centro.id, "codigo": u.centro.codigo, "nombre": u.centro.nombre,
                                             "regional": u.centro.regional} if u.centro else None,
        "lote_id": u.lote_id, "lote": {"id": u.lote.id, "nombre": u.lote.nombre, "numero": u.lote.numero,
                                       "abreviatura": u.lote.abreviatura, "color": u.lote.color} if u.lote else None,
        "coordinacion_id": u.coordinacion_id,
        "coordinacion": {"id": u.coordinacion.id, "nombre": u.coordinacion.nombre} if u.coordinacion else None,
        "documento": u.documento, "cargo": u.cargo, "aprobado": u.aprobado, "tiene_firma": bool(u.firma_path),
        "debe_cambiar_password": u.debe_cambiar_password,
    }


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == data.email.strip().lower()))
    ahora = datetime.now()
    if u and u.bloqueado_hasta and u.bloqueado_hasta > ahora:
        mins = int((u.bloqueado_hasta - ahora).total_seconds() // 60) + 1
        raise HTTPException(423, f"Cuenta bloqueada por intentos fallidos. Intente en {mins} minuto(s).")
    if not u or not verify_password(data.password, u.password_hash):
        if u:
            u.intentos_fallidos += 1
            if u.intentos_fallidos >= settings.MAX_INTENTOS:
                u.bloqueado_hasta = ahora + timedelta(minutes=settings.BLOQUEO_MINUTOS)
                u.intentos_fallidos = 0
            db.commit()
        raise HTTPException(401, "Correo o contraseña incorrectos")
    if not u.aprobado:
        raise HTTPException(403, "Su registro está pendiente de aprobación por el coordinador de su coordinación. "
                                 "Recibirá un correo cuando su cuenta sea activada.")
    if not u.activo:
        raise HTTPException(403, "Usuario inactivo. Contacte al administrador.")
    if u.centro and not u.centro.activo:
        raise HTTPException(403, "El centro de formación está inactivo. Contacte al manager.")
    u.intentos_fallidos, u.bloqueado_hasta = 0, None
    db.commit()
    return {"token": crear_token(u), "usuario": usuario_out(u)}


@router.get("/me")
def me(u: Usuario = Depends(usuario_actual)):
    return usuario_out(u)


@router.post("/cambiar-password")
def cambiar_password(data: CambioIn, u: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    if not verify_password(data.actual, u.password_hash):
        raise HTTPException(422, "La contraseña actual no es correcta")
    if data.actual == data.nueva:
        raise HTTPException(422, "La nueva contraseña debe ser diferente a la actual")
    validar_password(data.nueva)
    u.password_hash = hash_password(data.nueva)
    u.debe_cambiar_password = False
    db.commit()
    return {"ok": True}


# --- Autorregistro de instructores -------------------------------------------------
@router.get("/registro/opciones")
def opciones_registro(db: Session = Depends(get_db)):
    """Centros activos con sus coordinaciones (formulario público de registro)."""
    out = []
    for c in db.scalars(select(Centro).where(Centro.activo.is_(True)).order_by(Centro.nombre)):
        coords = db.scalars(select(Coordinacion).where(Coordinacion.centro_id == c.id, Coordinacion.activo.is_(True))
                            .order_by(Coordinacion.nombre)).all()
        if coords:
            out.append({"id": c.id, "nombre": c.nombre, "coordinaciones": [{"id": x.id, "nombre": x.nombre} for x in coords]})
    return {"centros": out, "dominios": settings.REGISTRO_DOMINIOS}


class RegistroIn(BaseModel):
    nombre: str
    email: EmailStr
    documento: str
    password: str
    centro_id: int
    coordinacion_id: int


def validar_documento(doc: str) -> str:
    doc = re.sub(r"[\s.]", "", doc or "")
    if not re.fullmatch(r"\d{5,15}", doc):
        raise HTTPException(422, "El número de identificación debe tener entre 5 y 15 dígitos")
    return doc


@router.post("/registro", status_code=201)
def registro(data: RegistroIn, db: Session = Depends(get_db)):
    """El instructor se registra; la cuenta queda pendiente hasta que el coordinador de su coordinación la aprueba."""
    email = data.email.lower()
    if settings.REGISTRO_DOMINIOS and email.rsplit("@", 1)[-1] not in settings.REGISTRO_DOMINIOS:
        raise HTTPException(422, "Use su correo institucional (" + ", ".join("@" + d for d in settings.REGISTRO_DOMINIOS) + ")")
    if not data.nombre.strip():
        raise HTTPException(422, "Indique su nombre completo")
    documento = validar_documento(data.documento)
    validar_password(data.password)
    if db.scalar(select(Usuario).where(func.lower(Usuario.email) == email)):
        raise HTTPException(409, "Ya existe una cuenta con ese correo. Si olvidó su contraseña, contacte a su coordinador.")
    centro = db.get(Centro, data.centro_id)
    coord = db.get(Coordinacion, data.coordinacion_id)
    if not centro or not centro.activo or not coord or coord.centro_id != centro.id or not coord.activo:
        raise HTTPException(422, "Seleccione un centro y una coordinación válidos")
    u = Usuario(nombre=data.nombre.strip()[:120], email=email, rol="INSTRUCTOR", centro_id=centro.id,
                coordinacion_id=coord.id, documento=documento, password_hash=hash_password(data.password),
                aprobado=False, activo=True, debe_cambiar_password=False)
    db.add(u)
    db.flush()
    revisores = list(db.scalars(select(Usuario.id).where(Usuario.rol == "COORDINADOR", Usuario.activo.is_(True),
                                                         Usuario.coordinacion_id == coord.id)))
    if not revisores:  # sin coordinador asignado: lo aprueba el administrador del centro
        revisores = list(db.scalars(select(Usuario.id).where(Usuario.rol == "ADMIN", Usuario.activo.is_(True),
                                                             Usuario.centro_id == centro.id)))
    notificar(db, revisores, "Instructor pendiente de aprobación",
              f"{u.nombre} ({u.email}, documento {documento}) se registró en la {coord.nombre}. Apruebe o rechace su cuenta.",
              "/coordinador/instructores")
    correo.encolar(db, email, "Recibimos su registro",
                   f"Hola {u.nombre}:\n\nSu registro como instructor de la {coord.nombre} del {centro.nombre} quedó "
                   "pendiente de aprobación. Le avisaremos por correo cuando su coordinador active su cuenta.", "/login")
    db.commit()
    return {"ok": True, "pendiente": True}


# --- Perfil ---------------------------------------------------------------------------
class PerfilIn(BaseModel):
    documento: str
    cargo: str | None = None  # coordinador: cargo que aparece en el GIL-F-014


@router.put("/perfil")
def perfil(data: PerfilIn, u: Usuario = Depends(usuario_actual), db: Session = Depends(get_db)):
    if data.documento.strip() or u.rol == "INSTRUCTOR":  # obligatorio sólo para el instructor (cuentadante)
        u.documento = validar_documento(data.documento)
    if data.cargo is not None and u.rol == "COORDINADOR":
        u.cargo = data.cargo.strip()[:120]
    db.commit()
    return usuario_out(u)


@router.post("/firma")
async def subir_firma(archivo: UploadFile = File(...), u: Usuario = Depends(requiere("COORDINADOR")),
                      db: Session = Depends(get_db)):
    """El coordinador carga (o reemplaza) la imagen de su firma; se estampa en los GIL-F-014 que apruebe."""
    from ..services.entregas import borrar_archivo, guardar_archivo
    ruta, _ = await guardar_archivo(archivo, "firmas", ("png", "jpg"), "Firma")
    anterior, u.firma_path = u.firma_path, ruta
    db.commit()
    borrar_archivo(anterior)  # las solicitudes ya aprobadas conservan su propia copia
    return usuario_out(u)


@router.get("/firma")
def ver_firma(u: Usuario = Depends(requiere("COORDINADOR"))):
    if not u.firma_path or not (settings.UPLOAD_DIR / u.firma_path).exists():
        raise HTTPException(404, "No ha cargado su firma")
    return FileResponse(settings.UPLOAD_DIR / u.firma_path,
                        media_type="image/png" if u.firma_path.endswith(".png") else "image/jpeg")
