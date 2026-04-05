"""Matches cache for FastAPI — alternative when Next.js unstable_cache limits apply.

Use when:
- Deploying FastAPI on Railway/VPS (not Vercel)
- Bypassing Next.js proxy (frontend calls FastAPI directly)
- Need Redis-like durability (extend with Redis backend)

Cache: user_id + mode + params → result, TTL 15 min.
Invalidation: resume update, job rating, compute taste.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

MATCHES_CACHE_TTL_SECONDS = 900  # 15 minutes

# In-memory cache: (user_id, mode, params_hash) -> (result, expires_at)
_cache: dict[tuple[str, str, str], tuple[Any, float]] = {}
_cache_lock = threading.Lock()
_stats: dict[str, int] = {"hits": 0, "misses": 0}


def _params_hash(
    exclude_interacted: bool,
    exclude_rated_only: bool,
    top_k: int,
    offset: int,
    min_similarity: float,
    max_days_old: int | None,
    session_id: str | None,
) -> str:
    parts = [
        str(exclude_interacted),
        str(exclude_rated_only),
        str(top_k),
        str(offset),
        str(min_similarity),
        str(max_days_old) if max_days_old is not None else "",
        session_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def get_cached(
    user_id: str,
    mode: str,
    exclude_interacted: bool,
    exclude_rated_only: bool,
    top_k: int,
    offset: int,
    min_similarity: float,
    max_days_old: int | None,
    session_id: str | None,
) -> dict | None:
    """Return cached result if valid, else None."""
    key = (
        user_id,
        mode,
        _params_hash(
            exclude_interacted, exclude_rated_only, top_k, offset, min_similarity, max_days_old, session_id
        ),
    )
    now = time.monotonic()
    with _cache_lock:
        if key in _cache:
            result, expires_at = _cache[key]
            if expires_at > now:
                _stats["hits"] += 1
                return result
            del _cache[key]
        _stats["misses"] += 1
    return None


def set_cached(
    user_id: str,
    mode: str,
    exclude_interacted: bool,
    exclude_rated_only: bool,
    top_k: int,
    offset: int,
    min_similarity: float,
    max_days_old: int | None,
    session_id: str | None,
    result: dict,
) -> None:
    """Store result in cache."""
    key = (
        user_id,
        mode,
        _params_hash(
            exclude_interacted, exclude_rated_only, top_k, offset, min_similarity, max_days_old, session_id
        ),
    )
    expires_at = time.monotonic() + MATCHES_CACHE_TTL_SECONDS
    with _cache_lock:
        _cache[key] = (result, expires_at)
    logger.debug("matches cache set: user=%s mode=%s", user_id, mode)


def invalidate_user(user_id: str) -> None:
    """Remove all cached entries for this user. Call on resume update or job rating."""
    with _cache_lock:
        to_remove = [k for k in _cache if k[0] == user_id]
        for k in to_remove:
            del _cache[k]
    if to_remove:
        logger.debug("matches cache invalidated: user=%s entries=%d", user_id, len(to_remove))


def invalidate_all() -> int:
    """Remove all cached entries. Call when crawl completes."""
    with _cache_lock:
        count = len(_cache)
        _cache.clear()
    if count:
        logger.debug("matches cache invalidated: all users, entries=%d", count)
    return count


def cache_stats() -> dict:
    """Return hit/miss stats and key count."""
    with _cache_lock:
        keys_count = len(_cache)
    total = _stats["hits"] + _stats["misses"]
    return {
        "hits": _stats["hits"],
        "misses": _stats["misses"],
        "hit_rate": round(_stats["hits"] / total, 4) if total else 0,
        "keys_count": keys_count,
    }
