"""
grpc_clients.py — canales gRPC persistentes hacia cada microservicio.

Se crean una sola vez al arrancar la app (via lifespan en main.py)
y se reutilizan en todas las peticiones — abrir un canal por request
es costoso y se considera antipatrón en gRPC.
"""
import os
import grpc
import logging

import auth_pb2_grpc
import admin_pb2_grpc
import query_pb2_grpc

log = logging.getLogger(__name__)

# Direcciones desde variables de entorno
AUTH_ADDR  = os.getenv("AUTH_SERVICE_ADDR",  "localhost:50051")
ADMIN_ADDR = os.getenv("ADMIN_SERVICE_ADDR", "localhost:50052")
QUERY_ADDR = os.getenv("QUERY_SERVICE_ADDR", "localhost:50054")

_CHANNEL_OPTIONS = [
    ("grpc.max_send_message_length",    16 * 1024 * 1024),
    ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ("grpc.keepalive_time_ms",          30_000),
    ("grpc.keepalive_timeout_ms",       10_000),
]

# Canales singleton (inicializados en lifespan)
_channels: dict = {}


def init_channels() -> None:
    """Llamar una vez al arranque de la app."""
    _channels["auth"]  = grpc.insecure_channel(AUTH_ADDR,  options=_CHANNEL_OPTIONS)
    _channels["admin"] = grpc.insecure_channel(ADMIN_ADDR, options=_CHANNEL_OPTIONS)
    _channels["query"] = grpc.insecure_channel(QUERY_ADDR, options=_CHANNEL_OPTIONS)
    log.info(f"gRPC channels → auth:{AUTH_ADDR}  admin:{ADMIN_ADDR}  query:{QUERY_ADDR}")


def close_channels() -> None:
    """Llamar al apagar la app."""
    for ch in _channels.values():
        ch.close()


def auth_stub()  -> auth_pb2_grpc.AuthServiceStub:
    return auth_pb2_grpc.AuthServiceStub(_channels["auth"])

def admin_stub() -> admin_pb2_grpc.AdminServiceStub:
    return admin_pb2_grpc.AdminServiceStub(_channels["admin"])

def query_stub() -> query_pb2_grpc.QueryServiceStub:
    return query_pb2_grpc.QueryServiceStub(_channels["query"])


# ── Helper: convierte RpcError → HTTPException ─────────────────────
from fastapi import HTTPException
import grpc

def call(fn, *args, **kwargs):
    """
    Envuelve cualquier llamada gRPC y convierte errores a HTTPException.
    Uso: response = call(auth_stub().Login, request_proto)
    """
    try:
        return fn(*args, **kwargs)
    except grpc.RpcError as e:
        code = e.code()
        detail = e.details() or str(code)
        mapping = {
            grpc.StatusCode.UNAVAILABLE:    503,
            grpc.StatusCode.UNIMPLEMENTED:  501,
            grpc.StatusCode.UNAUTHENTICATED: 401,
            grpc.StatusCode.PERMISSION_DENIED: 403,
            grpc.StatusCode.NOT_FOUND:      404,
            grpc.StatusCode.ALREADY_EXISTS: 409,
        }
        http_code = mapping.get(code, 500)
        raise HTTPException(status_code=http_code, detail=detail)
