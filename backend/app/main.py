import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import SessionLocal
from .routers import admin, analisis, articulos, auth, cotizaciones, entregas, solicitudes, tablero
from .seed import init_db
from .services.entregas import avisar_extemporaneas



def _revisar_legalizaciones() -> None:
    with SessionLocal() as db:
        avisar_extemporaneas(db)


async def _revision_periodica(cada_horas: float = 6) -> None:
    """Revisa varias veces al día las legalizaciones vencidas (cada aviso se envía como máximo una vez por semana)."""
    while True:
        try:
            await asyncio.to_thread(_revisar_legalizaciones)
        except Exception:  # un fallo nunca debe detener la aplicación
            logging.getLogger("entregas").exception("Error revisando legalizaciones vencidas")
        await asyncio.sleep(cada_horas * 3600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tarea = None
    if os.getenv("SKIP_INIT_DB") != "1":
        init_db(settings.SEED_EXCEL, os.getenv("SEED_DEMO") == "1")
        tarea = asyncio.create_task(_revision_periodica())
    yield
    if tarea:
        tarea.cancel()


app = FastAPI(title="SENA · Materiales de Formación", version="1.0.0", lifespan=lifespan,
              description="Estudio de mercados y solicitudes de materiales de formación por lote")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, admin, articulos, cotizaciones, analisis, solicitudes, tablero, entregas):
    app.include_router(r.router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    errores = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": {"mensaje": "Datos inválidos", "errores": errores}})


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Sirve la PWA compilada (frontend/dist) cuando existe: despliegue en un solo contenedor.
if settings.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=settings.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        if ruta.startswith("api/"):
            raise HTTPException(404)
        archivo = settings.FRONTEND_DIST / ruta
        if ruta and archivo.is_file() and settings.FRONTEND_DIST.resolve() in archivo.resolve().parents:
            return FileResponse(archivo)
        return FileResponse(settings.FRONTEND_DIST / "index.html", headers={"Cache-Control": "no-cache"})
