"""
storage_client.py — obtiene registros del Storage Service vía gRPC.

El Aggregation Service no tiene acceso directo a los archivos SQLite;
pide los datos al Storage Service que los sirve vía gRPC.
"""
import logging
import os

import grpc
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

import storage_pb2
import storage_pb2_grpc

log = logging.getLogger(__name__)

STORAGE_ADDR = os.getenv("STORAGE_SERVICE_ADDR", "localhost:50053")

_channel = None
_stub    = None


def init_client() -> None:
    global _channel, _stub
    _channel = grpc.insecure_channel(
        STORAGE_ADDR,
        options=[
            ("grpc.max_send_message_length",    32 * 1024 * 1024),
            ("grpc.max_receive_message_length", 32 * 1024 * 1024),
        ],
    )
    _stub = storage_pb2_grpc.StorageServiceStub(_channel)
    log.info(f"Storage client → {STORAGE_ADDR}")


def close_client() -> None:
    if _channel:
        _channel.close()


def fetch_records(
    db_name:     str,
    table_name:  str,
    filter_dict: dict,
    limit:       int = 0,
) -> tuple[bool, str, list[dict]]:
    """
    Obtiene registros del Storage Service.
    Retorna (success, message, records_as_list_of_dicts).
    """
    filter_struct = Struct()
    if filter_dict:
        filter_struct.update(filter_dict)

    try:
        resp = _stub.Find(
            storage_pb2.FindRequest(
                db_name    = db_name,
                table_name = table_name,
                filter     = filter_struct,
                limit      = limit,
                offset     = 0,
            )
        )
    except grpc.RpcError as exc:
        return False, f"Error al obtener datos: {exc.details()}", []

    if not resp.success:
        return False, resp.message, []

    records = [json_format.MessageToDict(r) for r in resp.records]
    log.debug(f"Fetched {len(records)} registros de {db_name}.{table_name}")
    return True, resp.message, records
