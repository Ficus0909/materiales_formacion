from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Usuario
from ..security import crear_token, hash_password, usuario_actual, validar_password, verify_password

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
