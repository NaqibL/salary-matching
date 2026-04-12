"""Job and Discover API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from mcf.api.auth import get_current_user
from mcf.api.cache.response import TTL_JOB_DETAIL, cache_response, invalidate_matches_for_user
from mcf.api.cache.matches import invalidate_user
from mcf.api.config import settings
from mcf.api.deps import get_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------


@router.get("/api/jobs/taxonomy")
def get_job_taxonomy():
    """Return role cluster taxonomy: list of {id, name} sorted by id."""
    import mcf.matching.classifiers as _cls
    _cls._load()
    return {
        "clusters": [
            {"id": k, "name": v}
            for k, v in sorted((_cls._taxonomy or {}).items())
        ]
    }


@router.get("/api/jobs/interested")
def get_interested_jobs(user_id: str = Depends(get_current_user)):
    """Return jobs the user has marked as interested, ordered by most recent first."""
    store = get_store()
    jobs = store.get_interested_jobs(user_id=user_id)
    return {"jobs": jobs}


@router.post("/api/jobs/{job_uuid}/interact")
def mark_interaction(
    job_uuid: str,
    interaction_type: str = Query(
        ...,
        description="Interaction type: viewed, dismissed, interested, not_interested",
    ),
    user_id: str = Depends(get_current_user),
):
    """Record a user interaction with a job (interested / not_interested / …)."""
    store = get_store()
    valid_types = {"viewed", "dismissed", "applied", "saved", "interested", "not_interested"}
    if interaction_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid interaction type. Must be one of: {', '.join(sorted(valid_types))}",
        )
    job = store.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    store.record_interaction(user_id=user_id, job_uuid=job_uuid, interaction_type=interaction_type)
    if settings.enable_matches_cache:
        invalidate_user(user_id)
    if settings.enable_response_cache:
        invalidate_matches_for_user(user_id)
    return {"status": "ok", "job_uuid": job_uuid, "interaction_type": interaction_type}


@router.get("/api/jobs/{job_uuid}")
@cache_response(TTL_JOB_DETAIL, "job", key_builder=lambda job_uuid, **_: job_uuid)
def get_job_detail(
    job_uuid: str,
    user_id: str = Depends(get_current_user),
):
    """Return full job details by UUID. Used for prefetching and job detail page."""
    store = get_store()
    job = store.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------------------------------------------------------------------------
# Discover endpoints
# ---------------------------------------------------------------------------


@router.get("/api/discover/stats")
def get_discover_stats(user_id: str = Depends(get_current_user)):
    """Return counts of interested, not_interested, and unrated jobs."""
    store = get_store()
    return store.get_discover_stats(user_id=user_id)
