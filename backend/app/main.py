import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import admin, analisis, articulos, auth, cotizaciones, solicitudes, tablero
from .seed import init_db



@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("SKIP_INIT_DB") != "1":
        init_db(settings.SEED_EXCEL, os.getenv("SEED_DEMO") == "1")
    yield


app = FastAPI(title="SENA · Materiales de Formación", version="1.0.0", lifespan=lifespan,
              description="Estudio de mercados y solicitudes de materiales de formación por lote")
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth, admin, articulos, cotizaciones, analisis, solicitudes, tablero):
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
