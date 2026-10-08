# Materiales de Formación — SENA CASA

PWA para el **estudio de mercados** y las **solicitudes por lote** de materiales de formación. Su punto de partida es el listado maestro de fichas técnicas del SENA (Centro de Atención al Sector Agropecuario, Regional Santander).

Funciona para **varios centros de formación**. Cada centro tiene su propio listado maestro, lotes, líderes, cotizaciones y solicitudes, y lo administra su administrador. Por encima de los administradores está el **manager**, que crea los centros y sus administradores, gestiona las vigencias y la configuración común, y consulta todos los centros.

Las reglas de negocio y las decisiones tomadas están en **[docs/REGLAS_NEGOCIO.md](docs/REGLAS_NEGOCIO.md)**.

## Qué hace

- **Listado maestro**: importación asistida desde el Excel del estudio (hojas `LM-AAAA`) con previsualización, CRUD, exportación y propuestas de artículos nuevos por parte de los líderes.
- **Cotizaciones**: un PDF por proveedor con precios para muchos artículos. Los precios se digitan o se cargan con la plantilla Excel.
- **Análisis de precios**: réplica del *Formato de análisis de precios y consolidación* (CV muestral, exclusión de atípicos, históricos indexados con IPC + puntos, precio de experto). Exporta a Excel con la misma estructura de las hojas L1…L11.
- **Solicitud por lote**: selección masiva desde el maestro, cantidades, autoguardado, plantilla Excel, clonación de la vigencia anterior y validaciones de envío.
- **Revisión**: aprobar, devolver o rechazar con observaciones. Al aprobar, los precios se congelan y pasan a ser históricos. Luego sigue el ciclo de compra configurable.
- **Dashboard, reportes y consolidado Excel**, notificaciones **en la aplicación y por correo** (incluido el correo de credenciales al crear un usuario) y PWA instalable con uso offline de consulta.

## Stack

FastAPI · SQLAlchemy 2 · SQLite (desarrollo) o MariaDB (producción) · Vue 3 + Vite + Pinia · openpyxl · Docker.

## Desarrollo local

```bash
# Backend
cd backend
python -m pip install -r requirements-dev.txt
python -m app.seed --excel "../contexto/ESTUDIO DE MERCADOS_BCTUCU_CASA_2026 (1).xlsx" --demo
python -m uvicorn app.main:app --reload --port 8000

# Frontend (otra terminal)
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxy /api → :8000)
```

Si `npm run build` genera `frontend/dist`, la API también sirve la PWA en http://localhost:8000.

Usuarios de la carga `--demo`:

| Rol | Correo | Clave |
|---|---|---|
| Manager (todos los centros) | manager@sena.edu.co | Manager123! |
| Administrador del centro CASA | admin@sena.edu.co | Admin123! |
| Líder (uno por lote, 11 lotes del centro CASA) | lider.agric@sena.edu.co, lider.pecua@sena.edu.co, … | Lider123! |

La carga demo crea la vigencia 2026 cerrada (los precios del estudio firmado quedan como históricos), la vigencia **2027 abierta** y 4 proveedores. El listado maestro del Excel se carga en el centro por defecto (`CENTRO_CODIGO`, CASA).

**Bases anteriores a los centros**: al arrancar, la aplicación migra el esquema sola (`app/migraciones.py`). Crea el centro por defecto y le asigna los lotes, usuarios y actividad existentes. Haga un respaldo antes de actualizar producción.

### Pruebas

```bash
cd backend
python -m pytest tests -q        # 27 pruebas: reglas de cálculo, seguridad, correo, flujo completo y aislamiento entre centros
```

## Producción (Docker)

```bash
cp .env.example .env     # defina claves reales
docker compose up -d --build
```

Se levantan dos servicios:

- `db`: MariaDB 11, con volumen `db_data`.
- `app`: API + PWA, con volumen `pdf_storage` para los PDF.

La primera vez, si `SEED_EXCEL` apunta al Excel (la carpeta `contexto/` se monta en `/seed`), el listado maestro se carga automáticamente.

**Correo**: configure `SMTP_*` y `APP_URL` en `.env`. Sin `SMTP_HOST`, las notificaciones quedan solo en la aplicación. Puede probar el envío en Configuración → Correo.

**Pendiente para producción**: HTTPS mediante un proxy inverso (el service worker lo exige fuera de localhost), respaldos de `db_data` y `pdf_storage`, y migraciones con Alembic si el esquema sigue cambiando (por ahora `app/migraciones.py` cubre el paso a centros de formación, en SQLite y MariaDB).

## Estructura

```
backend/app/
  models.py              entidades
  migraciones.py         migración del esquema a centros de formación
  routers/               auth, admin (centros, usuarios…), articulos, cotizaciones, analisis, solicitudes, tablero
  services/pricing.py    motor de análisis de precios
  services/excel_*.py    importación y exportación Excel
  seed.py                datos iniciales
backend/tests/           pruebas (pytest)
frontend/src/views/      pantallas manager/, admin/ y lider/
docs/REGLAS_NEGOCIO.md
contexto/                documentos fuente
```
