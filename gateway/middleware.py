"""
middleware.py — dependencias FastAPI para autenticación y autorización.

Uso en rutas:
    @router.get("/algo")
    def ruta(user: CurrentUser = Depends(get_current_user)):
        ...

    @router.post("/admin-only")
    def ruta_admin(user: CurrentUser = Depends(require_admin)):
        ...

Jerarquía de roles:
    admin  → puede todo
    writer → puede leer y escribir, no puede admin
    reader → solo puede leer
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

import auth_pb2
import grpc_clients


# ── Modelo de usuario autenticado ──────────────────────────────────

@dataclass
class CurrentUser:
    username: str
    role: str

    @property
    def is_admin(self)  -> bool: return self.role == "admin"
    @property
    def is_writer(self) -> bool: return self.role in ("admin", "writer")
    @property
    def is_reader(self) -> bool: return self.role in ("admin", "writer", "reader")


# ── Dependencia base ───────────────────────────────────────────────

def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> CurrentUser:
    """
    Extrae el Bearer token del header Authorization y lo valida
    llamando al Auth Service via gRPC.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header Authorization requerido (Bearer <token>)",
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato inválido. Usa: Authorization: Bearer <token>",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacío")

    resp = grpc_clients.call(
        grpc_clients.auth_stub().ValidateToken,
        auth_pb2.ValidateTokenRequest(token=token),
    )

    if not resp.valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=resp.message or "Token inválido",
        )

    return CurrentUser(username=resp.username, role=resp.role)


# ── Dependencias por rol ───────────────────────────────────────────

def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado. Se requiere rol 'admin' (tienes '{user.role}')",
        )
    return user


def require_writer(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_writer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado. Se requiere rol 'writer' o 'admin' (tienes '{user.role}')",
        )
    return user


def require_reader(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Cualquier usuario autenticado puede leer."""
    if not user.is_reader:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return user
