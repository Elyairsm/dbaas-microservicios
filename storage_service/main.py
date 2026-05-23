"""
Storage Service — implementación completa (Paso 5)

Recibe peticiones gRPC con google.protobuf.Struct para los registros
y filtros, los convierte a dicts de Python, llama al engine de SQLite
y devuelve los resultados como Structs.

Conversiones clave:
  Struct  → dict  (con _struct_to_dict)
  dict    → Struct (con _dict_to_struct)
"""
import logging
import os
from concurrent import futures

import grpc
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

import storage_pb2
import storage_pb2_grpc

import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [storage] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Conversores Protobuf ↔ Python ──────────────────────────────────

def _struct_to_dict(s: Struct) -> dict:
    """Convierte un protobuf Struct a dict de Python."""
    if s is None or not s.fields:
        return {}
    return json_format.MessageToDict(s)


def _dict_to_struct(d: dict) -> Struct:
    """Convierte un dict de Python a protobuf Struct."""
    s = Struct()
    # Struct no acepta None; convertimos a string vacío
    clean = {k: ("" if v is None else v) for k, v in d.items()}
    s.update(clean)
    return s


# ── Servicer ───────────────────────────────────────────────────────

class StorageServicer(storage_pb2_grpc.StorageServiceServicer):

    def Insert(self, request, context) -> storage_pb2.StorageResponse:
        record = _struct_to_dict(request.record)
        log.info(f"Insert → {request.db_name}.{request.table_name}")

        ok, msg, rowid = engine.insert(request.db_name, request.table_name, record)
        return storage_pb2.StorageResponse(
            success=ok,
            message=msg,
            affected_rows=1 if ok else 0,
        )

    def Find(self, request, context) -> storage_pb2.FindResponse:
        filter_dict = _struct_to_dict(request.filter)
        log.info(
            f"Find → {request.db_name}.{request.table_name} "
            f"filter={filter_dict} limit={request.limit}"
        )

        ok, msg, records = engine.find(
            request.db_name,
            request.table_name,
            filter_dict,
            limit=request.limit,
            offset=request.offset,
        )

        if not ok:
            return storage_pb2.FindResponse(success=False, message=msg)

        structs = [_dict_to_struct(r) for r in records]
        return storage_pb2.FindResponse(success=True, records=structs, message=msg)

    def Update(self, request, context) -> storage_pb2.StorageResponse:
        filter_dict = _struct_to_dict(request.filter)
        updates     = _struct_to_dict(request.updates)
        log.info(f"Update → {request.db_name}.{request.table_name} filter={filter_dict}")

        ok, msg, affected = engine.update(
            request.db_name, request.table_name, filter_dict, updates
        )
        return storage_pb2.StorageResponse(
            success=ok, message=msg, affected_rows=affected
        )

    def Delete(self, request, context) -> storage_pb2.StorageResponse:
        filter_dict = _struct_to_dict(request.filter)
        log.info(f"Delete → {request.db_name}.{request.table_name} filter={filter_dict}")

        ok, msg, affected = engine.delete(
            request.db_name, request.table_name, filter_dict
        )
        return storage_pb2.StorageResponse(
            success=ok, message=msg, affected_rows=affected
        )


# ── Server ─────────────────────────────────────────────────────────

def serve() -> None:
    port = os.getenv("GRPC_PORT", "50053")
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=20),
        options=[
            ("grpc.max_send_message_length",    32 * 1024 * 1024),
            ("grpc.max_receive_message_length", 32 * 1024 * 1024),
        ],
    )
    storage_pb2_grpc.add_StorageServiceServicer_to_server(StorageServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info(f"✅ Storage Service escuchando en puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
