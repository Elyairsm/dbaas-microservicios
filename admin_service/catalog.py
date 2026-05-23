"""
catalog.py — catálogo central de metadatos.

Guarda en _catalog.db qué bases de datos y tablas existen
y cuál es el schema de cada tabla (tipos de columnas).

Estructura:
  databases(name PK, created_at)
  tables(db_name, table_name, schema_json, created_at)
"""
import json
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
CATALOG_PATH = os.path.join(DATA_DIR, "_catalog.db")


# ── Inicialización ─────────────────────────────────────────────────

def init_catalog() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS databases (
                name       TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tables (
                db_name     TEXT NOT NULL,
                table_name  TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (db_name, table_name)
            );
        """)
    log.info(f"Catálogo listo en {CATALOG_PATH}")


# ── Bases de datos ─────────────────────────────────────────────────

def db_exists(name: str) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM databases WHERE name = ?", (name,)
        ).fetchone() is not None


def register_db(name: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO databases (name) VALUES (?)", (name,))
        c.commit()


def unregister_db(name: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM tables    WHERE db_name = ?", (name,))
        c.execute("DELETE FROM databases WHERE name    = ?", (name,))
        c.commit()


def list_dbs() -> list[str]:
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT name FROM databases ORDER BY name"
        ).fetchall()]


# ── Tablas ─────────────────────────────────────────────────────────

def table_exists(db_name: str, table_name: str) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM tables WHERE db_name = ? AND table_name = ?",
            (db_name, table_name),
        ).fetchone() is not None


def register_table(db_name: str, table_name: str, columns: list[dict]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO tables (db_name, table_name, schema_json) VALUES (?,?,?)",
            (db_name, table_name, json.dumps(columns)),
        )
        c.commit()


def unregister_table(db_name: str, table_name: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM tables WHERE db_name = ? AND table_name = ?",
            (db_name, table_name),
        )
        c.commit()


def list_tables(db_name: str) -> list[str]:
    with _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT table_name FROM tables WHERE db_name = ? ORDER BY table_name",
            (db_name,),
        ).fetchall()]


def get_schema(db_name: str, table_name: str) -> list[dict] | None:
    """Retorna la lista de ColumnDef o None si no existe."""
    with _conn() as c:
        row = c.execute(
            "SELECT schema_json FROM tables WHERE db_name=? AND table_name=?",
            (db_name, table_name),
        ).fetchone()
    return json.loads(row[0]) if row else None


# ── Helper ─────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(CATALOG_PATH)
