"""Response cache for FastAPI — TTL-based caching with key generation.

Supports:
- Dashboard endpoints: 1 hour TTL
- Match results: 15 minutes per user
- Job details: 24 hours

Cache key includes user_id (when auth) and query params. Manual invalidation
via POST /api/admin/invalidate-cache.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import threading
import time
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar

from mcf.api.config import settings

logger = logging.getLogger(__name__)

# TTL constants (seconds)
TTL_DASHBOARD = 3600  # 1 hour
TTL_MATCHES = 900  # 15 minutes
TTL_JOB_DETAIL = 86400  # 24 hours

# In-memory: key -> (value, expires_at)
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = threading.Lock()
_stats: dict[str, int] = {"hits": 0, "misses": 0}

P = ParamSpec("P")
R = TypeVar("R")


def make_cache_key(prefix: str, *, user_id: str | None = None, **params: Any) -> str:
    """Build cache key from prefix, optional user_id, and sorted params.

    Keys are deterministic: same inputs produce same key.
    """
    parts = [prefix]
    if user_id is not None:
        parts.append(f"u:{user_id}")
    if params:
        sorted_items = sorted((k, v) for k, v in params.items() if v is not None)
        param_str = "|".join(f"{k}={v}" for k, v in sorted_items)
        parts.append(hashlib.sha256(param_str.encode()).hexdigest()[:16])
    return ":".join(parts)


def cache_get(key: str) -> Any | None:
    """Return cached value if valid, else None."""
    with _cache_lock:
        if key not in _cache:
            _stats["misses"] += 1
            return None
        value, expires_at = _cache[key]
        if time.monotonic() > expires_at:
            del _cache[key]
            _stats["misses"] += 1
            return None
        _stats["hits"] += 1
    return value


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


def cache_list_keys(prefix: str = "", limit: int = 100) -> list[str]:
    """List cache keys (for admin)."""
    with _cache_lock:
        keys = [k for k in _cache if k.startswith(prefix)]
    return sorted(keys)[:limit]


def cache_set(key: str, ttl_seconds: int, value: Any) -> None:
    """Store value in cache with TTL."""
    expires_at = time.monotonic() + ttl_seconds
    with _cache_lock:
        _cache[key] = (value, expires_at)
    logger.debug("response_cache set: %s (ttl=%ds)", key[:60], ttl_seconds)


def invalidate_matches_for_user(user_id: str) -> int:
    """Invalidate all match cache entries for a user. Call when resume/rating changes."""
    return cache_invalidate(prefix=f"matches:u:{user_id}:")


def cache_invalidate(prefix: str | None = None, key: str | None = None) -> int:
    """Invalidate cache entries.

    - If key: remove that exact key.
    - If prefix: remove all keys starting with prefix.
    - Returns number of entries removed.
    """
    with _cache_lock:
        if key is not None:
            if key in _cache:
                del _cache[key]
                return 1
            return 0

        if prefix is not None:
            to_remove = [k for k in _cache if k.startswith(prefix)]
            for k in to_remove:
                del _cache[k]
            return len(to_remove)

    return 0


def cache_response(
    ttl_seconds: int,
    key_prefix: str,
    key_builder: Callable[..., str] | None = None,
):
    """Decorator to cache route responses with TTL.

    key_builder receives the route's kwargs and returns the key suffix.
    If None, uses make_cache_key(prefix, **kwargs) with user_id and other params.
    """

    def decorator(f: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(f)
        params = list(sig.parameters.keys())

        def _build_key(**kwargs: Any) -> str:
            if key_builder:
                return key_prefix + ":" + key_builder(**kwargs)
            user_id = kwargs.get("user_id")
            rest = {k: v for k, v in kwargs.items() if k != "user_id" and k in params}
            return make_cache_key(key_prefix, user_id=user_id, **rest)

        @wraps(f)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not settings.enable_response_cache:
                return f(*args, **kwargs)
            key = _build_key(**kwargs)
            cached = cache_get(key)
            if cached is not None:
                return cached
            result = f(*args, **kwargs)
            cache_set(key, ttl_seconds, result)
            return result

        @wraps(f)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not settings.enable_response_cache:
                return await f(*args, **kwargs)
            key = _build_key(**kwargs)
            cached = cache_get(key)
            if cached is not None:
                return cached
            result = await f(*args, **kwargs)
            cache_set(key, ttl_seconds, result)
            return result

        if inspect.iscoroutinefunction(f):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
