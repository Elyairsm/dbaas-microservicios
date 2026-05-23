"""
Admin Service — implementación completa (Paso 4)

Gestiona el ciclo de vida de bases de datos y tablas:
  1. Mantiene el catálogo de metadatos (_catalog.db)
  2. Ejecuta DDL real en los archivos SQLite del usuario

El directorio DATA_DIR es compartido con Storage Service
(ambos montan el mismo volumen Docker storage_data).
"""
import grpc
import logging
import os
from concurrent import futures

import admin_pb2
import admin_pb2_grpc

from catalog        import (init_catalog, db_exists, register_db, unregister_db,
                             list_dbs, table_exists, register_table, unregister_table,
                             list_tables)
from storage_engine import (create_database, delete_database,
                             create_table, delete_table)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [admin] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Servicer ───────────────────────────────────────────────────────

class AdminServicer(admin_pb2_grpc.AdminServiceServicer):

    # ── Bases de datos ─────────────────────────────────────────────

    def CreateDatabase(self, request, context) -> admin_pb2.AdminResponse:
        name = request.db_name.strip()
        if not name:
            return admin_pb2.AdminResponse(success=False, message="Nombre de BD vacío")
        if db_exists(name):
            return admin_pb2.AdminResponse(
                success=False, message=f"La base de datos '{name}' ya existe"
            )
        try:
            create_database(name)
            register_db(name)
            log.info(f"CreateDatabase: '{name}'")
            return admin_pb2.AdminResponse(
                success=True, message=f"Base de datos '{name}' creada exitosamente"
            )
        except Exception as exc:
            log.error(f"CreateDatabase error: {exc}")
            return admin_pb2.AdminResponse(success=False, message=str(exc))

    def ListDatabases(self, request, context) -> admin_pb2.ListResponse:
        dbs = list_dbs()
        return admin_pb2.ListResponse(
            success=True,
            items=dbs,
            message=f"{len(dbs)} base(s) de datos",
        )

    def DeleteDatabase(self, request, context) -> admin_pb2.AdminResponse:
        name = request.db_name
        if not db_exists(name):
            return admin_pb2.AdminResponse(
                success=False, message=f"La base de datos '{name}' no existe"
            )
        try:
            delete_database(name)
            unregister_db(name)
            log.info(f"DeleteDatabase: '{name}'")
            return admin_pb2.AdminResponse(
                success=True, message=f"Base de datos '{name}' eliminada"
            )
        except Exception as exc:
            log.error(f"DeleteDatabase error: {exc}")
            return admin_pb2.AdminResponse(success=False, message=str(exc))

    # ── Tablas ─────────────────────────────────────────────────────

    def CreateTable(self, request, context) -> admin_pb2.AdminResponse:
        db_name    = request.db_name
        table_name = request.table_name

        if not db_exists(db_name):
            return admin_pb2.AdminResponse(
                success=False, message=f"La base de datos '{db_name}' no existe"
            )
        if table_exists(db_name, table_name):
            return admin_pb2.AdminResponse(
                success=False,
                message=f"La tabla '{table_name}' ya existe en '{db_name}'",
            )
        if not request.columns:
            return admin_pb2.AdminResponse(
                success=False, message="Debes definir al menos una columna"
            )

        columns = [
            {
                "name":     col.name,
                "type":     col.type,
                "nullable": col.nullable,
                "primary":  col.primary,
            }
            for col in request.columns
        ]

        try:
            create_table(db_name, table_name, columns)
            register_table(db_name, table_name, columns)
            log.info(f"CreateTable: '{db_name}'.'{table_name}' ({len(columns)} columnas)")
            return admin_pb2.AdminResponse(
                success=True,
                message=f"Tabla '{table_name}' creada en '{db_name}'",
            )
        except Exception as exc:
            log.error(f"CreateTable error: {exc}")
            return admin_pb2.AdminResponse(success=False, message=str(exc))

    def ListTables(self, request, context) -> admin_pb2.ListResponse:
        db_name = request.db_name
        if not db_exists(db_name):
            return admin_pb2.ListResponse(
                success=False, items=[],
                message=f"La base de datos '{db_name}' no existe",
            )
        tables = list_tables(db_name)
        return admin_pb2.ListResponse(
            success=True,
            items=tables,
            message=f"{len(tables)} tabla(s) en '{db_name}'",
        )

    def DeleteTable(self, request, context) -> admin_pb2.AdminResponse:
        db_name    = request.db_name
        table_name = request.table_name

        if not db_exists(db_name):
            return admin_pb2.AdminResponse(
                success=False, message=f"La base de datos '{db_name}' no existe"
            )
        if not table_exists(db_name, table_name):
            return admin_pb2.AdminResponse(
                success=False,
                message=f"La tabla '{table_name}' no existe en '{db_name}'",
            )
        try:
            delete_table(db_name, table_name)
            unregister_table(db_name, table_name)
            log.info(f"DeleteTable: '{db_name}'.'{table_name}'")
            return admin_pb2.AdminResponse(
                success=True, message=f"Tabla '{table_name}' eliminada"
            )
        except Exception as exc:
            log.error(f"DeleteTable error: {exc}")
            return admin_pb2.AdminResponse(success=False, message=str(exc))


# ── Server ─────────────────────────────────────────────────────────

def serve() -> None:
    init_catalog()

    port = os.getenv("GRPC_PORT", "50052")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    admin_pb2_grpc.add_AdminServiceServicer_to_server(AdminServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info(f"✅ Admin Service escuchando en puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
