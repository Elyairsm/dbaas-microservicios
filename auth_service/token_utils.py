"""
token_utils.py — generación y validación de JWTs.

Payload:
  sub   → username
  role  → admin | writer | reader
  iat   → issued at
  exp   → expiry (configurable vía JWT_EXPIRY_HOURS)
"""
import os
import logging
from datetime import datetime, timedelta, timezone

import jwt

log = logging.getLogger(__name__)

SECRET       = os.getenv("JWT_SECRET", "change_me_in_production")
EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
ALGORITHM    = "HS256"


def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub":  username,
        "role": role,
        "iat":  now,
        "exp":  now + timedelta(hours=EXPIRY_HOURS),
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    log.debug(f"Token generado para {username} ({role}), expira en {EXPIRY_HOURS}h")
    return token


def validate_token(token: str) -> tuple:
    """
    Retorna (True, {"username": ..., "role": ...}) si el token es válido.
    Retorna (False, {"error": ...})                si no lo es.
    """
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        return True, {
            "username": payload["sub"],
            "role":     payload["role"],
        }
    except jwt.ExpiredSignatureError:
        return False, {"error": "Token expirado"}
    except jwt.InvalidTokenError as exc:
        return False, {"error": f"Token inválido: {exc}"}
