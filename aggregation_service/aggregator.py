"""
aggregator.py — gestiona el pool de workers y coordina scatter/gather.

Estrategia:
  1. El coordinador (proceso principal) divide los registros en N chunks.
  2. Cada worker recibe su chunk y computa el resultado parcial.
  3. El coordinador recibe todos los parciales y los reduce al resultado final.

Pool:
  - Intenta usar mpi4py.futures.MPIPoolExecutor (MPI real).
  - Si MPI no está disponible (ej. entorno de desarrollo sin mpirun),
    cae silenciosamente a concurrent.futures.ProcessPoolExecutor
    con la misma interfaz.

El CMD del Dockerfile usa `python -m mpi4py.futures main.py` para que
mpi4py levante los worker processes automáticamente al inicio.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import Executor, ProcessPoolExecutor

import mpi_workers

log = logging.getLogger(__name__)

MPI_WORKERS = int(os.getenv("MPI_WORKERS", "4"))

_pool: Executor | None = None


# ── Lifecycle ──────────────────────────────────────────────────────

def init_pool() -> None:
    global _pool
    try:
        from mpi4py.futures import MPIPoolExecutor
        _pool = MPIPoolExecutor(max_workers=MPI_WORKERS)
        log.info(f"✅ MPI pool — {MPI_WORKERS} workers (mpi4py.futures)")
    except Exception as exc:
        log.warning(f"MPI no disponible ({exc}). Usando ProcessPoolExecutor.")
        _pool = ProcessPoolExecutor(max_workers=MPI_WORKERS)
        log.info(f"✅ Process pool — {MPI_WORKERS} workers (multiprocessing)")


def shutdown_pool() -> None:
    if _pool:
        _pool.shutdown(wait=True)
        log.info("Pool de workers apagado")


# ── Particionador ──────────────────────────────────────────────────

def _split(records: list, n: int) -> list[list]:
    """Divide `records` en hasta `n` fragmentos de tamaño similar."""
    if not records:
        return [[]]
    n = min(n, len(records))
    size = max(1, (len(records) + n - 1) // n)
    return [records[i : i + size] for i in range(0, len(records), size)]


# ── Operaciones ────────────────────────────────────────────────────

def count(records: list) -> float:
    """COUNT(*) distribuido."""
    if not records:
        return 0.0
    chunks  = _split(records, MPI_WORKERS)
    futures = [_pool.submit(mpi_workers.count_chunk, chunk) for chunk in chunks]
    return float(sum(f.result() for f in futures))


def aggregate_sum(records: list, field: str) -> float:
    """SUM(field) distribuido."""
    if not records:
        return 0.0
    chunks  = _split(records, MPI_WORKERS)
    futures = [_pool.submit(mpi_workers.sum_chunk, chunk, field) for chunk in chunks]
    return float(sum(f.result() for f in futures))


def avg(records: list, field: str) -> float:
    """AVG(field) distribuido. Cada worker devuelve (sum, count)."""
    if not records:
        return 0.0
    chunks  = _split(records, MPI_WORKERS)
    futures = [_pool.submit(mpi_workers.avg_chunk, chunk, field) for chunk in chunks]
    partial = [f.result() for f in futures]

    total_sum   = sum(s for s, _ in partial)
    total_count = sum(c for _, c in partial)
    return float(total_sum / total_count) if total_count > 0 else 0.0


def distinct(records: list, field: str) -> list[dict]:
    """DISTINCT field distribuido. Reduce = unión de sets."""
    if not records:
        return []
    chunks  = _split(records, MPI_WORKERS)
    futures = [_pool.submit(mpi_workers.distinct_chunk, chunk, field) for chunk in chunks]

    unique: set = set()
    for f in futures:
        unique.update(f.result())

    return [{field: v} for v in sorted(unique, key=str)]


def inner_join(
    left_records:  list,
    right_records: list,
    left_key:      str,
    right_key:     str,
) -> list[dict]:
    """
    INNER JOIN distribuido.
    Los registros de la tabla izquierda se particionan entre workers.
    La tabla derecha se envía completa a cada worker (broadcast).
    """
    if not left_records or not right_records:
        return []

    chunks  = _split(left_records, MPI_WORKERS)
    futures = [
        _pool.submit(mpi_workers.join_chunk, chunk, right_records, left_key, right_key)
        for chunk in chunks
    ]

    result: list[dict] = []
    for f in futures:
        result.extend(f.result())
    return result
