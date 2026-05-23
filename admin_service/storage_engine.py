"""
storage_engine.py — operaciones DDL sobre los archivos SQLite del usuario.

Cada base de datos lógica = un archivo {db_name}.db en DATA_DIR.
Admin Service los crea/elimina. Storage Service los usa para DML.
Ambos servicios comparten el mismo volumen Docker (storage_data).

Mapeo de tipos:
  string → TEXT
  int    → INTEGER
  float  → REAL
  bool   → INTEGER  (SQLite no tiene booleano nativo)
"""
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")

_TYPE_MAP = {
    "string": "TEXT",
    "int":    "INTEGER",
    "float":  "REAL",
    "bool":   "INTEGER",
}


# ── Paths ──────────────────────────────────────────────────────────

def db_path(db_name: str) -> str:
    # Sanitizar para evitar path traversal
    safe = "".join(c for c in db_name if c.isalnum() or c == "_")
    return os.path.join(DATA_DIR, f"{safe}.db")


# ── Operaciones de base de datos ───────────────────────────────────

def create_database(db_name: str) -> None:
    """Crea el archivo SQLite vacío."""
    path = db_path(db_name)
    if os.path.exists(path):
        raise FileExistsError(f"El archivo de BD '{db_name}' ya existe en disco")
    conn = sqlite3.connect(path)
    conn.close()
    log.info(f"Archivo SQLite creado: {path}")


def delete_database(db_name: str) -> None:
    """Elimina el archivo SQLite y todos sus datos."""
    path = db_path(db_name)
    if os.path.exists(path):
        os.remove(path)
        log.info(f"Archivo SQLite eliminado: {path}")


# ── Operaciones de tabla ───────────────────────────────────────────

def create_table(db_name: str, table_name: str, columns: list[dict]) -> None:
    """
    Ejecuta CREATE TABLE dentro del SQLite de esa BD.

    columns: lista de dicts con keys: name, type, nullable, primary
    Si ninguna columna es primary, se agrega _id AUTOINCREMENT automáticamente.
    """
    path = db_path(db_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"BD '{db_name}' no encontrada en disco")

    col_defs = []
    has_primary = any(c.get("primary") for c in columns)

    # PK automática si el usuario no definió ninguna
    if not has_primary:
        col_defs.append('"_id" INTEGER PRIMARY KEY AUTOINCREMENT')

    for col in columns:
        sql_type   = _TYPE_MAP.get(col["type"], "TEXT")
        constraint = ""
        if col.get("primary"):
            constraint = " PRIMARY KEY"
        elif not col.get("nullable", True):
            constraint = " NOT NULL"
        col_defs.append(f'"{col["name"]}" {sql_type}{constraint}')

    sql = (
        f'CREATE TABLE IF NOT EXISTS "{table_name}" '
        f'({", ".join(col_defs)})'
    )
    log.debug(f"DDL: {sql}")

    with sqlite3.connect(path) as conn:
        conn.execute(sql)
        conn.commit()
    log.info(f"Tabla creada: {db_name}.{table_name}")


def delete_table(db_name: str, table_name: str) -> None:
    path = db_path(db_name)
    with sqlite3.connect(path) as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.commit()
    log.info(f"Tabla eliminada: {db_name}.{table_name}")


def list_physical_tables(db_name: str) -> list[str]:
    """Tablas reales en el SQLite (útil para diagnóstico)."""
    path = db_path(db_name)
    if not os.path.exists(path):
        return []
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    return [r[0] for r in rows]
