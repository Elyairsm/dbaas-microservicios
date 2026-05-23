"""
routes/admin.py — administración de bases de datos y tablas/colecciones.

Todas las rutas requieren autenticación.
Crear y eliminar requieren rol admin.
Listar requiere cualquier rol autenticado.

POST   /admin/databases
GET    /admin/databases
DELETE /admin/databases/{db_name}

POST   /admin/databases/{db_name}/tables
GET    /admin/databases/{db_name}/tables
DELETE /admin/databases/{db_name}/tables/{table_name}
"""
import logging
from fastapi import APIRouter, Depends

import admin_pb2
import grpc_clients
from models    import (CreateDatabaseRequest, CreateTableRequest,
                       AdminResponse, ListResponse, ColumnDef)
from middleware import require_admin, require_reader, CurrentUser

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Administración"])


# ── Bases de datos ─────────────────────────────────────────────────

@router.post(
    "/databases",
    response_model=AdminResponse,
    status_code=201,
    summary="Crear base de datos",
)
def create_database(
    body: CreateDatabaseRequest,
    user: CurrentUser = Depends(require_admin),
):
    resp = grpc_clients.call(
        grpc_clients.admin_stub().CreateDatabase,
        admin_pb2.DatabaseRequest(db_name=body.db_name, token="internal"),
    )
    log.info(f"[{user.username}] CreateDatabase: {body.db_name}")
    return AdminResponse(success=resp.success, message=resp.message)


@router.get(
    "/databases",
    response_model=ListResponse,
    summary="Listar bases de datos",
)
def list_databases(user: CurrentUser = Depends(require_reader)):
    resp = grpc_clients.call(
        grpc_clients.admin_stub().ListDatabases,
        admin_pb2.ListRequest(token="internal"),
    )
    return ListResponse(success=resp.success, items=list(resp.items), message=resp.message)


@router.delete(
    "/databases/{db_name}",
    response_model=AdminResponse,
    summary="Eliminar base de datos",
)
def delete_database(
    db_name: str,
    user: CurrentUser = Depends(require_admin),
):
    resp = grpc_clients.call(
        grpc_clients.admin_stub().DeleteDatabase,
        admin_pb2.DatabaseRequest(db_name=db_name, token="internal"),
    )
    log.info(f"[{user.username}] DeleteDatabase: {db_name}")
    return AdminResponse(success=resp.success, message=resp.message)


# ── Tablas / colecciones ───────────────────────────────────────────

@router.post(
    "/databases/{db_name}/tables",
    response_model=AdminResponse,
    status_code=201,
    summary="Crear tabla o colección",
)
def create_table(
    db_name: str,
    body:    CreateTableRequest,
    user:    CurrentUser = Depends(require_admin),
):
    cols = [
        admin_pb2.ColumnDef(
            name=c.name,
            type=c.type,
            nullable=c.nullable,
            primary=c.primary,
        )
        for c in body.columns
    ]
    resp = grpc_clients.call(
        grpc_clients.admin_stub().CreateTable,
        admin_pb2.TableRequest(
            db_name=db_name,
            table_name=body.table_name,
            columns=cols,
            token="internal",
        ),
    )
    log.info(f"[{user.username}] CreateTable: {db_name}.{body.table_name}")
    return AdminResponse(success=resp.success, message=resp.message)


@router.get(
    "/databases/{db_name}/tables",
    response_model=ListResponse,
    summary="Listar tablas o colecciones",
)
def list_tables(
    db_name: str,
    user:    CurrentUser = Depends(require_reader),
):
    resp = grpc_clients.call(
        grpc_clients.admin_stub().ListTables,
        admin_pb2.ListTablesRequest(db_name=db_name, token="internal"),
    )
    return ListResponse(success=resp.success, items=list(resp.items), message=resp.message)


@router.delete(
    "/databases/{db_name}/tables/{table_name}",
    response_model=AdminResponse,
    summary="Eliminar tabla o colección",
)
def delete_table(
    db_name:    str,
    table_name: str,
    user:       CurrentUser = Depends(require_admin),
):
    resp = grpc_clients.call(
        grpc_clients.admin_stub().DeleteTable,
        admin_pb2.TableRequest(
            db_name=db_name,
            table_name=table_name,
            token="internal",
        ),
    )
    log.info(f"[{user.username}] DeleteTable: {db_name}.{table_name}")
    return AdminResponse(success=resp.success, message=resp.message)
