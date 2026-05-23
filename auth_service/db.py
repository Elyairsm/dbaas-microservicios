"""
db.py — persistencia de usuarios en SQLite.

Esquema:
  users(id, username UNIQUE, password_hash, role, created_at)

Roles permitidos: admin | writer | reader

Al arrancar por primera vez se crea un usuario admin/admin123
para que el sistema no quede sin acceso.
"""
import os
import sqlite3
import bcrypt
import logging

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_PATH  = os.path.join(DATA_DIR, "auth.db")

VALID_ROLES = {"admin", "writer", "reader"}


# ── Inicialización ─────────────────────────────────────────────────

def init_db() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL
                                CHECK(role IN ('admin','writer','reader')),
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    _seed_admin()
    log.info(f"Auth DB ready at {DB_PATH}")


def _seed_admin() -> None:
    """Crea admin/admin123 si la tabla está vacía."""
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            pw_hash = _hash("admin123")
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                ("admin", pw_hash, "admin"),
            )
            conn.commit()
            log.warning("Seeded default admin user (admin/admin123) — ¡cámbialo en producción!")


# ── CRUD de usuarios ───────────────────────────────────────────────

def create_user(username: str, password: str, role: str) -> tuple[bool, str]:
    if role not in VALID_ROLES:
        return False, f"Rol inválido '{role}'. Usa: {', '.join(VALID_ROLES)}"
    if not username or len(username) < 3:
        return False, "Username debe tener al menos 3 caracteres"
    if not password or len(password) < 6:
        return False, "Password debe tener al menos 6 caracteres"

    pw_hash = _hash(password)
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
                (username, pw_hash, role),
            )
            conn.commit()
        log.info(f"Usuario creado: {username} ({role})")
        return True, "Usuario creado exitosamente"
    except sqlite3.IntegrityError:
        return False, f"El username '{username}' ya existe"


def get_user(username: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row:
        return {"username": row[0], "password_hash": row[1], "role": row[2]}
    return None


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def list_users() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [{"username": r[0], "role": r[1], "created_at": r[2]} for r in rows]


# ── Helpers privados ───────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
