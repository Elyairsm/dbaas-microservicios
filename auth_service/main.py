"""
Auth Service — implementación completa (Paso 2)

Endpoints gRPC:
  Register      → crea usuario, retorna JWT
  Login         → valida credenciales, retorna JWT
  ValidateToken → decodifica JWT, retorna username + role

Reglas de negocio:
  • Cualquier cliente puede registrarse como 'reader'.
  • Registrar 'writer' o 'admin' requiere token de admin
    (el Gateway valida eso antes de llamar aquí).
  • Contraseñas hasheadas con bcrypt (12 rondas).
  • JWTs firmados con HS256, expiry configurable.
"""

import grpc
import logging
import os
from concurrent import futures

import auth_pb2
import auth_pb2_grpc

from db           import init_db, create_user, get_user, verify_password
from token_utils  import create_token, validate_token

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [auth] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Servicer ───────────────────────────────────────────────────────

class AuthServicer(auth_pb2_grpc.AuthServiceServicer):

    def Register(self, request: auth_pb2.RegisterRequest, context) -> auth_pb2.AuthResponse:
        log.info(f"Register: username='{request.username}' role='{request.role}'")

        ok, msg = create_user(request.username, request.password, request.role)
        if not ok:
            log.warning(f"Register failed for '{request.username}': {msg}")
            return auth_pb2.AuthResponse(success=False, message=msg)

        token = create_token(request.username, request.role)
        return auth_pb2.AuthResponse(
            success=True,
            token=token,
            role=request.role,
            message="Registro exitoso",
        )

    def Login(self, request: auth_pb2.LoginRequest, context) -> auth_pb2.AuthResponse:
        log.info(f"Login: username='{request.username}'")

        user = get_user(request.username)

        # Tiempo constante para evitar timing attacks:
        # si el usuario no existe comparamos contra un hash dummy.
        dummy_hash = "$2b$12$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        stored_hash = user["password_hash"] if user else dummy_hash

        password_ok = verify_password(request.password, stored_hash)

        if not user or not password_ok:
            log.warning(f"Login fallido para '{request.username}'")
            return auth_pb2.AuthResponse(success=False, message="Credenciales inválidas")

        token = create_token(user["username"], user["role"])
        log.info(f"Login exitoso: '{user['username']}' ({user['role']})")
        return auth_pb2.AuthResponse(
            success=True,
            token=token,
            role=user["role"],
            message="Login exitoso",
        )

    def ValidateToken(self, request: auth_pb2.ValidateTokenRequest, context) -> auth_pb2.ValidateTokenResponse:
        valid, data = validate_token(request.token)

        if valid:
            log.debug(f"Token válido: '{data['username']}' ({data['role']})")
            return auth_pb2.ValidateTokenResponse(
                valid=True,
                username=data["username"],
                role=data["role"],
                message="Token válido",
            )

        log.warning(f"Token inválido: {data.get('error')}")
        return auth_pb2.ValidateTokenResponse(
            valid=False,
            message=data.get("error", "Token inválido"),
        )


# ── Server ─────────────────────────────────────────────────────────

def serve() -> None:
    init_db()   # crea tabla + seed admin si es primera ejecución

    port = os.getenv("GRPC_PORT", "50051")
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length",    10 * 1024 * 1024),
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
        ],
    )
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info(f"✅ Auth Service escuchando en puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
