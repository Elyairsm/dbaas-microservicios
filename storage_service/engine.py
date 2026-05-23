"""
engine.py — operaciones DML sobre los archivos SQLite del usuario.

Cada base de datos lógica = un archivo {db_name}.db en DATA_DIR.
Este módulo no sabe nada de gRPC ni de protobuf;
trabaja solo con dicts de Python y retorna dicts de Python.
"""
from __future__ import annotations

import logging
import os
import sqlite3

from filter_builder import build_where

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")


# ── Helpers ────────────────────────────────────────────────────────

def _db_path(db_name: str) -> str:
    safe = "".join(c for c in db_name if c.isalnum() or c == "_")
    return os.path.join(DATA_DIR, f"{safe}.db")


def _open(db_name: str) -> sqlite3.Connection:
    path = _db_path(db_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Base de datos '{db_name}' no encontrada")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row   # acceso por nombre de columna
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convierte una Row a dict limpio (None → omitido para Struct)."""
    return {k: row[k] for k in row.keys() if row[k] is not None}


# ── INSERT ─────────────────────────────────────────────────────────

def insert(db_name: str, table_name: str, record: dict) -> tuple[bool, str, int]:
    """
    Inserta un registro.
    Retorna (success, message, rowid).
    """
    if not record:
        return False, "El registro no puede estar vacío", 0

    cols         = ", ".join(f'"{k}"' for k in record)
    placeholders = ", ".join("?" * len(record))
    values       = list(record.values())
    sql          = f'INSERT INTO "{table_name}" ({cols}) VALUES ({placeholders})'

    try:
        with _open(db_name) as conn:
            cursor = conn.execute(sql, values)
            conn.commit()
            rowid = cursor.lastrowid
        log.debug(f"INSERT {db_name}.{table_name} → rowid={rowid}")
        return True, f"Registro insertado (id={rowid})", rowid
    except sqlite3.OperationalError as e:
        return False, f"Error al insertar: {e}", 0
    except sqlite3.IntegrityError as e:
        return False, f"Violación de integridad: {e}", 0


# ── FIND ───────────────────────────────────────────────────────────

def find(
    db_name:     str,
    table_name:  str,
    filter_dict: dict,
    limit:       int = 0,
    offset:      int = 0,
) -> tuple[bool, str, list[dict]]:
    """
    Busca registros que coincidan con el filtro.
    limit=0 → sin límite.
    """
    try:
        where, params = build_where(filter_dict)
    except ValueError as e:
        return False, str(e), []

    sql = f'SELECT * FROM "{table_name}"'
    if where:
        sql += f" WHERE {where}"
    if limit > 0:
        sql += f" LIMIT {limit}"
        if offset > 0:
            sql += f" OFFSET {offset}"

    try:
        with _open(db_name) as conn:
            rows = conn.execute(sql, params).fetchall()
        records = [_row_to_dict(r) for r in rows]
        log.debug(f"FIND {db_name}.{table_name} → {len(records)} registros")
        return True, f"{len(records)} registro(s) encontrado(s)", records
    except FileNotFoundError as e:
        return False, str(e), []
    except sqlite3.OperationalError as e:
        return False, f"Error al buscar: {e}", []


# ── UPDATE ─────────────────────────────────────────────────────────

def update(
    db_name:     str,
    table_name:  str,
    filter_dict: dict,
    updates:     dict,
) -> tuple[bool, str, int]:
    """
    Actualiza los campos de 'updates' en los registros que coincidan con filter_dict.
    Retorna (success, message, affected_rows).
    """
    if not updates:
        return False, "No hay campos a actualizar", 0

    try:
        where, where_params = build_where(filter_dict)
    except ValueError as e:
        return False, str(e), 0

    set_clause = ", ".join(f'"{k}" = ?' for k in updates)
    set_params = list(updates.values())

    sql = f'UPDATE "{table_name}" SET {set_clause}'
    if where:
        sql += f" WHERE {where}"

    try:
        with _open(db_name) as conn:
            cursor = conn.execute(sql, set_params + where_params)
            conn.commit()
            affected = cursor.rowcount
        log.debug(f"UPDATE {db_name}.{table_name} → {affected} filas")
        return True, f"{affected} registro(s) actualizado(s)", affected
    except FileNotFoundError as e:
        return False, str(e), 0
    except sqlite3.OperationalError as e:
        return False, f"Error al actualizar: {e}", 0


# ── DELETE ─────────────────────────────────────────────────────────

def delete(
    db_name:     str,
    table_name:  str,
    filter_dict: dict,
) -> tuple[bool, str, int]:
    """
    Elimina registros que coincidan con filter_dict.
    Si filter_dict está vacío, elimina TODOS (truncate).
    """
    try:
        where, params = build_where(filter_dict)
    except ValueError as e:
        return False, str(e), 0

    sql = f'DELETE FROM "{table_name}"'
    if where:
        sql += f" WHERE {where}"

    try:
        with _open(db_name) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            affected = cursor.rowcount
        log.debug(f"DELETE {db_name}.{table_name} → {affected} filas")
        return True, f"{affected} registro(s) eliminado(s)", affected
    except FileNotFoundError as e:
        return False, str(e), 0
    except sqlite3.OperationalError as e:
        return False, f"Error al eliminar: {e}", 0
