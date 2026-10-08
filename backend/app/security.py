import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Usuario

PASSWORD_RE = re.compile(r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
PASSWORD_MSG = "La contraseña debe tener mínimo 8 caracteres, una mayúscula, un número y un carácter especial"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def validar_password(pw: str) -> None:
    if not PASSWORD_RE.match(pw):
        raise HTTPException(422, PASSWORD_MSG)


def crear_token(usuario: Usuario) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_HORAS)
    return jwt.encode({"sub": str(usuario.id), "rol": usuario.rol, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


def usuario_actual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.query_params.get("token")
    if not token:
        raise HTTPException(401, "No autenticado")
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesión inválida o expirada")
    user = db.get(Usuario, int(data["sub"]))
    if not user or not user.activo:
        raise HTTPException(401, "Usuario inactivo")
    if user.centro and not user.centro.activo:
        raise HTTPException(401, "El centro de formación está inactivo")
    return user


def requiere(*roles: str):
    def dep(user: Usuario = Depends(usuario_actual)) -> Usuario:
        if user.rol not in roles:
            raise HTTPException(403, "No tiene permisos para esta acción")
        return user

    return dep


solo_manager = requiere("MANAGER")
solo_admin = requiere("ADMIN")
solo_lider = requiere("LIDER")
admin_o_manager = requiere("ADMIN", "MANAGER")
operador = requiere("ADMIN", "LIDER")  # operan dentro de su centro; el manager sólo consulta
