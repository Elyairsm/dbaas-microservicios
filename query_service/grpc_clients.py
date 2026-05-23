"""
grpc_clients.py — canales gRPC persistentes del Query Service.

Conecta con:
  - Storage Service     (CRUD)
  - Aggregation Service (COUNT, SUM, AVG, DISTINCT, INNER JOIN)

RabbitMQ se integra en Paso 8 para despacho asíncrono de agregaciones.
"""
import os
import grpc
import logging

import storage_pb2_grpc
import aggregation_pb2_grpc

log = logging.getLogger(__name__)

STORAGE_ADDR     = os.getenv("STORAGE_SERVICE_ADDR",     "localhost:50053")
AGGREGATION_ADDR = os.getenv("AGGREGATION_SERVICE_ADDR", "localhost:50055")

_OPTS = [
    ("grpc.max_send_message_length",    32 * 1024 * 1024),
    ("grpc.max_receive_message_length", 32 * 1024 * 1024),
]

_channels: dict = {}


def init_channels() -> None:
    _channels["storage"]     = grpc.insecure_channel(STORAGE_ADDR,     options=_OPTS)
    _channels["aggregation"] = grpc.insecure_channel(AGGREGATION_ADDR, options=_OPTS)
    log.info(f"gRPC → storage:{STORAGE_ADDR}  aggregation:{AGGREGATION_ADDR}")


def close_channels() -> None:
    for ch in _channels.values():
        ch.close()


def storage_stub() -> storage_pb2_grpc.StorageServiceStub:
    return storage_pb2_grpc.StorageServiceStub(_channels["storage"])


def aggregation_stub() -> aggregation_pb2_grpc.AggregationServiceStub:
    return aggregation_pb2_grpc.AggregationServiceStub(_channels["aggregation"])
