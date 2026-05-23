"""
models.py — modelos Pydantic de entrada y salida para el Gateway.

Separarlos de las rutas permite reutilizarlos y facilita los tests.
"""
from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


# ── Auth ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: str     = Field("reader", pattern="^(admin|writer|reader)$")

class LoginRequest(BaseModel):
    username: str
    password: str

class AuthResponse(BaseModel):
    success: bool
    token:   Optional[str] = None
    role:    Optional[str] = None
    message: str


# ── Admin ──────────────────────────────────────────────────────────

class CreateDatabaseRequest(BaseModel):
    db_name: str = Field(..., min_length=1, max_length=64,
                         pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")

class ColumnDef(BaseModel):
    name:     str  = Field(..., min_length=1)
    type:     str  = Field(..., pattern="^(string|int|float|bool)$")
    nullable: bool = True
    primary:  bool = False

class CreateTableRequest(BaseModel):
    table_name: str               = Field(..., min_length=1, max_length=64,
                                          pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    columns:    List[ColumnDef]   = Field(..., min_length=1)

class AdminResponse(BaseModel):
    success: bool
    message: str

class ListResponse(BaseModel):
    success: bool
    items:   List[str]
    message: str


# ── Query ──────────────────────────────────────────────────────────

class SQLRequest(BaseModel):
    sql: str = Field(..., min_length=1)

class NoSQLRequest(BaseModel):
    db_name:    str            = Field(..., min_length=1)
    collection: str            = Field(..., min_length=1)
    operation:  str            = Field(..., pattern="^(insert|find|update|delete|aggregate)$")
    payload:    dict[str, Any] = Field(default_factory=dict)

class QueryResponse(BaseModel):
    success:       bool
    rows:          List[dict[str, Any]] = []
    affected_rows: int                  = 0
    message:       str                  = ""
