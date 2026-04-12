"""Admin API routes — cache management and diagnostics."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from mcf.api.auth import get_current_user
from mcf.api.cache.job_pool import invalidate as invalidate_active_jobs_pool
from mcf.api.cache.matches import cache_stats as matches_cache_stats, invalidate_all
from mcf.api.cache.response import (
    cache_invalidate,
    cache_list_keys,
    cache_stats as response_cache_stats,
    invalidate_matches_for_user,
)
from mcf.api.config import settings
from mcf.api.deps import get_store

router = APIRouter()


def _verify_admin_or_secret(
    authorization: str | None = Header(default=None),
    x_crawl_secret: str | None = Header(default=None, alias="X-Crawl-Secret"),
) -> str:
    """Allow access if X-Crawl-Secret matches OR JWT user is admin."""
    expected_secret = os.getenv("CRON_SECRET") or os.getenv("REVALIDATE_SECRET")
    if expected_secret and x_crawl_secret == expected_secret:
        return "crawl"
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = get_current_user(authorization=authorization)
        except HTTPException:
            raise
        store = get_store()
        if store and settings.admin_user_ids_set and user_id in settings.admin_user_ids_set:
            return user_id
        if store:
            user = store.get_user_by_id(user_id)
            if user and user.get("role") == "admin":
                return user_id
    raise HTTPException(status_code=403, detail="Admin access required")


@router.post("/api/admin/invalidate-pool")
def admin_invalidate_pool(_: str = Depends(_verify_admin_or_secret)):
    """Invalidate the active jobs pool cache. Call after crawl completes.

    Auth: X-Crawl-Secret header or JWT with admin role / ADMIN_USER_IDS.
    """
    if settings.enable_active_jobs_pool_cache:
        invalidate_active_jobs_pool()
    return {"status": "ok"}


@router.post("/api/admin/invalidate-cache")
def admin_invalidate_cache(
    _: str = Depends(_verify_admin_or_secret),
    prefix: str | None = Query(default=None, description="Invalidate all keys with this prefix"),
    key: str | None = Query(default=None, description="Invalidate exact key"),
    user_id: str | None = Query(default=None, description="Invalidate all matches for user"),
):
    """Manually invalidate response cache entries.

    Auth: X-Crawl-Secret header or JWT with admin role / ADMIN_USER_IDS.
    """
    removed = 0
    if user_id:
        removed = invalidate_matches_for_user(user_id)
    elif key:
        removed = cache_invalidate(key=key)
    elif prefix:
        removed = cache_invalidate(prefix=prefix)
        if prefix == "matches:" and settings.enable_matches_cache:
            removed += invalidate_all()
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide one of: prefix, key, or user_id",
        )
    return {"status": "ok", "removed": removed}


@router.get("/api/admin/cache-stats")
def admin_cache_stats(_: str = Depends(_verify_admin_or_secret)):
    """Cache hit rates and key counts. Auth: X-Crawl-Secret or admin JWT."""
    return {
        "response_cache": response_cache_stats(),
        "matches_cache": matches_cache_stats(),
    }


@router.get("/api/admin/cache-keys")
def admin_cache_keys(
    _: str = Depends(_verify_admin_or_secret),
    prefix: str = Query(default="", description="Filter by prefix"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List cache keys (for debugging). Auth: X-Crawl-Secret or admin JWT."""
    return {"keys": cache_list_keys(prefix=prefix, limit=limit)}


@router.delete("/api/admin/cache")
def admin_clear_cache(
    _: str = Depends(_verify_admin_or_secret),
    key: str | None = Query(default=None),
    prefix: str | None = Query(default=None),
):
    """Clear specific key or prefix. Auth: X-Crawl-Secret or admin JWT."""
    if key:
        removed = cache_invalidate(key=key)
    elif prefix:
        removed = cache_invalidate(prefix=prefix)
        if prefix == "matches:" and settings.enable_matches_cache:
            removed += invalidate_all()
    else:
        raise HTTPException(400, "Provide key or prefix")
    return {"removed": removed}


@router.get("/api/admin/cache-timestamp")
def admin_cache_timestamp(_: str = Depends(_verify_admin_or_secret)):
    """Last crawl/cache update timestamp from DB. Auth: X-Crawl-Secret or admin JWT."""
    from mcf.api import deps as _deps
    store = _deps._store
    if not store or not hasattr(store, "get_cache_metadata"):
        return {"last_updated": None}
    try:
        row = store.get_cache_metadata("crawl_completed_at")
        return {"last_updated": str(row["updated_at"]) if row else None}
    except Exception:
        return {"last_updated": None}
