"""Active jobs pool cache — caches (job_uuid, embedding, last_seen_at) for matching.

Similar to matches_cache: in-memory, TTL 15 min. Reduces DB round-trips when
get_active_job_ids_ranked is called frequently (e.g. many match requests).

Also caches a pre-stacked numpy matrix of all embeddings so that
compute_ranked_from_pool can use a single vectorised matrix multiply instead
of a per-job Python loop.

Invalidate when: crawl completes, jobs deactivated, embeddings updated.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from mcf.lib.storage.base import Storage

logger = logging.getLogger(__name__)

ACTIVE_JOBS_POOL_TTL_SECONDS = 900  # 15 minutes

# (pool_data, embeddings_matrix, expires_at)
# pool_data:          list of (job_uuid, embedding, last_seen_at)
# embeddings_matrix:  pre-stacked float32 array, shape (n_jobs, dim)
_cache: tuple[list[tuple[str, list[float], datetime | None]], np.ndarray, float] | None = None


def get_cached() -> tuple[list[tuple[str, list[float], datetime | None]], np.ndarray] | tuple[None, None]:
    """Return (pool, matrix) if cache is valid, else (None, None)."""
    global _cache
    if _cache is None:
        return None, None
    pool, matrix, expires_at = _cache
    if time.monotonic() > expires_at:
        _cache = None
        return None, None
    return pool, matrix


def set_cached(pool: list[tuple[str, list[float], datetime | None]]) -> None:
    """Store pool in cache and pre-compute the stacked embedding matrix."""
    global _cache
    if pool:
        matrix = np.array([emb for _, emb, _ in pool], dtype=np.float32)
    else:
        matrix = np.empty((0, 0), dtype=np.float32)
    expires_at = time.monotonic() + ACTIVE_JOBS_POOL_TTL_SECONDS
    _cache = (pool, matrix, expires_at)
    logger.debug("active jobs pool cache set: %d jobs", len(pool))


def invalidate() -> None:
    """Clear the cache. Call when crawl completes or embeddings change."""
    global _cache
    if _cache is not None:
        _cache = None
        logger.debug("active jobs pool cache invalidated")


def compute_ranked_from_pool(
    pool: list[tuple[str, list[float], datetime | None]],
    query_embedding: list[float],
    limit: int | None = None,
    matrix: np.ndarray | None = None,
) -> list[tuple[str, float, datetime | None]]:
    """Compute (job_uuid, cosine_distance, last_seen_at) sorted by distance ASC.

    Uses a single vectorised matrix multiply when *matrix* is supplied (the
    pre-stacked array from the cache).  Falls back to building the matrix on
    the fly when not supplied, which is still faster than the previous per-job
    loop because numpy's array construction is C-level.

    Returns all jobs when limit is None (default).
    """
    if not pool:
        return []
    query_vec = np.array(query_embedding, dtype=np.float32)

    if matrix is None or matrix.ndim < 2 or matrix.shape[0] == 0:
        matrix = np.array([emb for _, emb, _ in pool], dtype=np.float32)

    # One BLAS dot-product call for all jobs at once.
    sims = matrix @ query_vec  # shape (n_jobs,)
    distances = 1.0 - sims

    scored = [
        (job_uuid, float(dist), last_seen_at)
        for (job_uuid, _, last_seen_at), dist in zip(pool, distances)
    ]
    scored.sort(key=lambda x: x[1])
    return scored[:limit] if limit is not None else scored


def get_pool_or_fetch(
    store: Storage,
) -> tuple[list[tuple[str, list[float], datetime | None]], np.ndarray | None]:
    """Return (pool, matrix) — either from cache or freshly fetched.

    The caller should pass *matrix* to compute_ranked_from_pool to avoid
    re-building it on every request.
    """
    pool, matrix = get_cached()
    if pool is not None:
        return pool, matrix
    pool = store.get_active_jobs_pool()
    set_cached(pool)
    pool, matrix = get_cached()
    return pool, matrix  # type: ignore[return-value]
