"""
routes/query.py — interfaces SQL-like y NoSQL-like.

POST /query/sql    → recibe un string SQL, lo reenvía al Query Service
POST /query/nosql  → recibe un documento JSON con la operación

Permisos:
  • SELECT / find / aggregate  → require_reader
  • INSERT / UPDATE / DELETE / insert / update / delete → require_writer
"""
import logging
from typing import Any
from fastapi import APIRouter, Depends

import query_pb2
import grpc_clients
from google.protobuf.struct_pb2 import Struct
from models    import SQLRequest, NoSQLRequest, QueryResponse
from middleware import require_reader, require_writer, CurrentUser, get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/query", tags=["Consultas"])


# ── Helpers ────────────────────────────────────────────────────────

def _dict_to_struct(d: dict) -> Struct:
    s = Struct()
    s.update(d)
    return s

def _struct_to_dict(s: Struct) -> dict:
    return dict(s)

def _rows_to_list(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]

# Palabras clave que indican operación de escritura en SQL
_WRITE_KEYWORDS = {"insert", "update", "delete", "create", "drop", "alter"}

def _sql_is_write(sql: str) -> bool:
    first_word = sql.strip().split()[0].lower() if sql.strip() else ""
    return first_word in _WRITE_KEYWORDS

# Operaciones NoSQL de escritura
_NOSQL_WRITE_OPS = {"insert", "update", "delete"}


# ── SQL interface ──────────────────────────────────────────────────

@router.post(
    "/sql",
    response_model=QueryResponse,
    summary="Ejecutar consulta SQL",
    description="""
Acepta SQL estándar:

```sql
-- CRUD
SELECT * FROM usuarios WHERE edad > 18
INSERT INTO usuarios (nombre, edad) VALUES ('Ana', 25)
UPDATE usuarios SET edad = 26 WHERE nombre = 'Ana'
DELETE FROM usuarios WHERE nombre = 'Ana'

-- Agregaciones
SELECT COUNT(*) FROM pedidos
SELECT SUM(total) FROM pedidos WHERE status = 'pagado'
SELECT AVG(precio) FROM productos
SELECT DISTINCT categoria FROM productos

-- Join
SELECT u.nombre, p.total
FROM usuarios u
INNER JOIN pedidos p ON u.id = p.usuario_id
```
""",
)
def execute_sql(
    body: SQLRequest,
    user: CurrentUser = Depends(get_current_user),
):
    # Verificar permiso según tipo de operación
    if _sql_is_write(body.sql) and not user.is_writer:
        from fastapi import HTTPException
        raise HTTPException(403, "Operaciones de escritura requieren rol writer o admin")

    resp = grpc_clients.call(
        grpc_clients.query_stub().ExecuteSQL,
        query_pb2.SQLRequest(sql=body.sql, token="internal"),
    )
    return QueryResponse(
        success=resp.success,
        rows=_rows_to_list(resp.rows),
        affected_rows=resp.affected_rows,
        message=resp.message,
    )


# ── NoSQL interface ────────────────────────────────────────────────

@router.post(
    "/nosql",
    response_model=QueryResponse,
    summary="Ejecutar operación NoSQL (JSON)",
    description="""
Operaciones disponibles:

```json
// Insertar
{"db_name":"mi_db","collection":"usuarios","operation":"insert",
 "payload":{"record":{"nombre":"Ana","edad":25}}}

// Buscar
{"db_name":"mi_db","collection":"usuarios","operation":"find",
 "payload":{"filter":{"edad":25}}}

// Actualizar
{"db_name":"mi_db","collection":"usuarios","operation":"update",
 "payload":{"filter":{"nombre":"Ana"},"updates":{"edad":26}}}

// Eliminar
{"db_name":"mi_db","collection":"usuarios","operation":"delete",
 "payload":{"filter":{"nombre":"Ana"}}}

// Agregación
{"db_name":"mi_db","collection":"pedidos","operation":"aggregate",
 "payload":{"op":"SUM","field":"total","filter":{}}}
```
""",
)
def execute_nosql(
    body: NoSQLRequest,
    user: CurrentUser = Depends(get_current_user),
):
    if body.operation in _NOSQL_WRITE_OPS and not user.is_writer:
        from fastapi import HTTPException
        raise HTTPException(403, "Operaciones de escritura requieren rol writer o admin")

    resp = grpc_clients.call(
        grpc_clients.query_stub().ExecuteNoSQL,
        query_pb2.NoSQLRequest(
            db_name=body.db_name,
            collection=body.collection,
            operation=body.operation,
            payload=_dict_to_struct(body.payload),
            token="internal",
        ),
    )
    return QueryResponse(
        success=resp.success,
        rows=_rows_to_list(resp.rows),
        affected_rows=resp.affected_rows,
        message=resp.message,
    )
