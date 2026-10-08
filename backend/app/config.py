"""Configuración por variables de entorno (con valores por defecto aptos para desarrollo)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'materiales.db'}")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "cambiar-en-produccion-esta-clave-no-es-segura")
    JWT_HORAS: int = int(os.getenv("JWT_HORAS", "8"))
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads")))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    FRONTEND_DIST: Path = Path(os.getenv("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist")))
    SEED_EXCEL: str = os.getenv("SEED_EXCEL", "")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@sena.edu.co")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "Admin123!")
    # Manager: por encima de los administradores de todos los centros de formación
    MANAGER_EMAIL: str = os.getenv("MANAGER_EMAIL", "manager@sena.edu.co")
    MANAGER_PASSWORD: str = os.getenv("MANAGER_PASSWORD", "Manager123!")
    # Centro por defecto: recibe el administrador inicial y, al migrar, los datos existentes
    CENTRO_CODIGO: str = os.getenv("CENTRO_CODIGO", "CASA")
    CENTRO_NOMBRE: str = os.getenv("CENTRO_NOMBRE", "Centro de Atención al Sector Agropecuario")
    CENTRO_REGIONAL: str = os.getenv("CENTRO_REGIONAL", "Santander")
    # Correo (SMTP). Si SMTP_HOST está vacío, las notificaciones sólo quedan en la aplicación.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")
    SMTP_FROM_NOMBRE: str = os.getenv("SMTP_FROM_NOMBRE", "SENA · Materiales de Formación")
    SMTP_STARTTLS: bool = os.getenv("SMTP_STARTTLS", "1") == "1"
    SMTP_SSL: bool = os.getenv("SMTP_SSL", "0") == "1"
    APP_URL: str = os.getenv("APP_URL", "http://localhost:8000")
    MAX_INTENTOS: int = 3
    BLOQUEO_MINUTOS: int = 15


settings = Settings()
