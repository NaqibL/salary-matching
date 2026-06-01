"""Active jobs pool cache — caches (job_uuid, last_seen_at) + embedding matrix for matching.

Similar to matches_cache: in-memory, TTL 15 min. Reduces DB round-trips when
get_active_job_ids_ranked is called frequently (e.g. many match requests).

Embeddings are stored only in the pre-stacked numpy matrix; the pool list keeps
only (uuid, last_seen_at) so embeddings are not duplicated in memory.

Invalidate when: crawl completes, jobs deactivated, embeddings updated.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from mcf.lib.storage.base import Storage

logger = logging.getLogger(__name__)

ACTIVE_JOBS_POOL_TTL_SECONDS = 900  # 15 minutes

# (pool_meta, embeddings_matrix, expires_at)
# pool_meta:          list of (job_uuid, last_seen_at)  — NO embeddings stored here
# embeddings_matrix:  pre-stacked float32 array, shape (n_jobs, dim)
_cache: tuple[list[tuple[str, datetime | None]], np.ndarray, float] | None = None
_fetch_lock = threading.Lock()  # prevents thundering herd on cache miss


def get_cached() -> tuple[list[tuple[str, datetime | None]], np.ndarray] | tuple[None, None]:
    """Return (pool_meta, matrix) if cache is valid, else (None, None)."""
    global _cache
    if _cache is None:
        return None, None
    pool, matrix, expires_at = _cache
    if time.monotonic() > expires_at:
        _cache = None
        return None, None
    return pool, matrix


def set_cached(full_pool: list[tuple[str, Any, datetime | None]]) -> None:
    """Build matrix from embeddings and cache (uuid, last_seen_at) metadata only.

    Embeddings are extracted to build the matrix then discarded from the pool
    list so they are not held twice in memory.
    """
    global _cache
    if full_pool:
        matrix = np.array([emb for _, emb, _ in full_pool], dtype=np.float32)
        pool_meta: list[tuple[str, datetime | None]] = [(uuid, ts) for uuid, _, ts in full_pool]
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
        pool_meta = []
    expires_at = time.monotonic() + ACTIVE_JOBS_POOL_TTL_SECONDS
    _cache = (pool_meta, matrix, expires_at)
    logger.debug("active jobs pool cache set: %d jobs", len(pool_meta))


def invalidate() -> None:
    """Clear the cache. Call when crawl completes or embeddings change."""
    global _cache
    if _cache is not None:
        _cache = None
        logger.debug("active jobs pool cache invalidated")


def compute_ranked_from_pool(
    pool: list[tuple[str, datetime | None]],
    query_embedding: list[float],
    limit: int | None = None,
    matrix: np.ndarray | None = None,
) -> list[tuple[str, float, datetime | None]]:
    """Compute (job_uuid, cosine_distance, last_seen_at) sorted by distance ASC.

    *matrix* must be supplied — the pre-stacked float32 array from the cache.
    Pool contains only (uuid, last_seen_at); embeddings live in the matrix.

    Returns all jobs when limit is None (default).
    """
    if not pool:
        return []
    if matrix is None or matrix.ndim < 2 or matrix.shape[0] == 0:
        raise ValueError("matrix is required for compute_ranked_from_pool")

    query_vec = np.array(query_embedding, dtype=np.float32)

    # One BLAS dot-product call for all jobs at once.
    sims = matrix @ query_vec  # shape (n_jobs,)
    distances = 1.0 - sims

    scored = [
        (job_uuid, float(dist), last_seen_at)
        for (job_uuid, last_seen_at), dist in zip(pool, distances)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:limit] if limit is not None else scored


def get_pool_or_fetch(
    store: Storage,
) -> tuple[list[tuple[str, datetime | None]], np.ndarray | None]:
    """Return (pool_meta, matrix) — either from cache or freshly fetched.

    The fetch lock ensures only one thread fetches from the DB on a cache miss.
    Without it, all 40 FastAPI worker threads race to fetch the full pool
    simultaneously, each holding ~3 GB, spiking process memory to 20+ GB.
    """
    pool, matrix = get_cached()
    if pool is not None:
        return pool, matrix
    with _fetch_lock:
        # Re-check inside the lock — another thread may have populated it.
        pool, matrix = get_cached()
        if pool is not None:
            return pool, matrix
        full_pool = store.get_active_jobs_pool()
        set_cached(full_pool)
        pool, matrix = get_cached()
    return pool, matrix  # type: ignore[return-value]
