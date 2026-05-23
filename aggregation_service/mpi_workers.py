"""
mpi_workers.py — funciones puras que se ejecutan en cada worker MPI.

Reglas de diseño:
  - Deben ser picklables (definidas a nivel de módulo, sin lambdas ni closures).
  - Reciben un fragmento (chunk) de la lista total de registros.
  - Retornan un resultado parcial que el coordinador luego reduce.
  - No tienen efectos secundarios ni estado compartido.

Cada función corresponde a un "map" en el paradigma map-reduce:
  count_chunk   → reduce: sum()
  sum_chunk     → reduce: sum()
  avg_chunk     → reduce: sum(sums) / sum(counts)
  distinct_chunk → reduce: union de sets
  join_chunk    → reduce: concatenar listas
"""
from __future__ import annotations


# ── COUNT ──────────────────────────────────────────────────────────

def count_chunk(chunk: list) -> int:
    """Cuenta los registros en este fragmento."""
    return len(chunk)


# ── SUM ────────────────────────────────────────────────────────────

def sum_chunk(chunk: list, field: str) -> float:
    """Suma los valores del campo `field` en este fragmento."""
    total = 0.0
    for row in chunk:
        val = row.get(field)
        if val is not None:
            try:
                total += float(val)
            except (TypeError, ValueError):
                pass
    return total


# ── AVG ────────────────────────────────────────────────────────────

def avg_chunk(chunk: list, field: str) -> tuple[float, int]:
    """
    Retorna (suma_parcial, conteo_parcial) para calcular el promedio global.
    El reduce es: sum(sumas) / sum(conteos).
    """
    total, count = 0.0, 0
    for row in chunk:
        val = row.get(field)
        if val is not None:
            try:
                total += float(val)
                count += 1
            except (TypeError, ValueError):
                pass
    return total, count


# ── DISTINCT ───────────────────────────────────────────────────────

def distinct_chunk(chunk: list, field: str) -> set:
    """Retorna el conjunto de valores únicos del campo en este fragmento."""
    return {row[field] for row in chunk if field in row and row[field] is not None}


# ── INNER JOIN ─────────────────────────────────────────────────────

def join_chunk(
    left_chunk:    list,
    right_records: list,
    left_key:      str,
    right_key:     str,
) -> list[dict]:
    """
    Hash join: construye un lookup de los registros de la tabla derecha
    y hace el join con el fragmento izquierdo.

    right_records se envía completo a cada worker (broadcast).
    Esto funciona bien cuando la tabla derecha cabe en memoria;
    para datasets muy grandes se debería usar un join distribuido.
    """
    # Construir índice de la tabla derecha
    right_index: dict[any, list] = {}
    for row in right_records:
        key = row.get(right_key)
        if key is not None:
            right_index.setdefault(key, []).append(row)

    result = []
    for left_row in left_chunk:
        lk = left_row.get(left_key)
        for right_row in right_index.get(lk, []):
            # Prefijamos las claves del lado derecho para evitar colisiones
            merged = dict(left_row)
            for k, v in right_row.items():
                if k in merged:
                    merged[f"r_{k}"] = v
                else:
                    merged[k] = v
            result.append(merged)

    return result
