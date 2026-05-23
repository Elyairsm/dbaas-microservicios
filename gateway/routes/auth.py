"""
routes/auth.py — registro y login.

POST /auth/register
POST /auth/login

Regla de negocio para Register:
  • role='reader'  → cualquiera puede registrarse sin token.
  • role='writer'  → requiere token de admin.
  • role='admin'   → requiere token de admin.
"""
import logging
from fastapi import APIRouter, Depends, Header, HTTPException

import auth_pb2
import grpc_clients
from models    import RegisterRequest, LoginRequest, AuthResponse
from middleware import get_current_user, require_admin, CurrentUser
from typing import Optional

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/register", response_model=AuthResponse, summary="Registrar nuevo usuario")
def register(
    body: RegisterRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Registra un nuevo usuario.
    - `reader`: no requiere autenticación.
    - `writer` / `admin`: requiere un token de admin en el header.
    """
    # Si el rol requiere privilegios, validar que quien llama es admin
    if body.role in ("writer", "admin"):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=403,
                detail=f"Crear usuarios con rol '{body.role}' requiere token de admin",
            )
        token = authorization.split(" ", 1)[1]
        val = grpc_clients.call(
            grpc_clients.auth_stub().ValidateToken,
            auth_pb2.ValidateTokenRequest(token=token),
        )
        if not val.valid or val.role != "admin":
            raise HTTPException(status_code=403, detail="Solo un admin puede crear este rol")

    resp = grpc_clients.call(
        grpc_clients.auth_stub().Register,
        auth_pb2.RegisterRequest(
            username=body.username,
            password=body.password,
            role=body.role,
        ),
    )
    if not resp.success:
        raise HTTPException(status_code=409, detail=resp.message)

    log.info(f"Nuevo usuario registrado: {body.username} ({body.role})")
    return AuthResponse(
        success=True,
        token=resp.token,
        role=resp.role,
        message=resp.message,
    )


@router.post("/login", response_model=AuthResponse, summary="Iniciar sesión")
def login(body: LoginRequest):
    """
    Retorna un JWT Bearer token que debes incluir en el header
    `Authorization: Bearer <token>` en las demás peticiones.
    """
    resp = grpc_clients.call(
        grpc_clients.auth_stub().Login,
        auth_pb2.LoginRequest(username=body.username, password=body.password),
    )
    if not resp.success:
        raise HTTPException(status_code=401, detail=resp.message)

    log.info(f"Login exitoso: {body.username}")
    return AuthResponse(
        success=True,
        token=resp.token,
        role=resp.role,
        message=resp.message,
    )
