"""
API Gateway — implementación completa (Paso 3)

Punto de entrada HTTP para el sistema DBaaS.
Traduce peticiones REST → llamadas gRPC a los microservicios.

Rutas disponibles:
  POST   /auth/register
  POST   /auth/login

  POST   /admin/databases
  GET    /admin/databases
  DELETE /admin/databases/{db_name}
  POST   /admin/databases/{db_name}/tables
  GET    /admin/databases/{db_name}/tables
  DELETE /admin/databases/{db_name}/tables/{table_name}

  POST   /query/sql
  POST   /query/nosql
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import grpc_clients
from routes.auth  import router as auth_router
from routes.admin import router as admin_router
from routes.query import router as query_router

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [gateway] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Lifespan: abre/cierra canales gRPC ────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Iniciando API Gateway...")
    grpc_clients.init_channels()
    yield
    log.info("Cerrando canales gRPC...")
    grpc_clients.close_channels()


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="DBaaS — API Gateway",
    version="1.0.0",
    description=(
        "Plataforma distribuida de almacenamiento y consulta de datos.\n\n"
        "Usa `POST /auth/login` para obtener tu token y luego inclúyelo como:\n"
        "`Authorization: Bearer <token>`"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(query_router)


# ── Health check ───────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "service": "api-gateway", "version": "1.0.0"}
