"""Job and Discover API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from mcf.api.auth import get_current_user, get_optional_user
from mcf.api.cache.response import TTL_JOB_DETAIL, cache_response, invalidate_matches_for_user
from mcf.api.cache.matches import invalidate_user
from mcf.api.config import settings
from mcf.api.deps import get_store

router = APIRouter()


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------


@router.get("/api/jobs/taxonomy")
def get_job_taxonomy(_: str | None = Depends(get_optional_user)):
    """Return role taxonomy: list of {id, name, key} sorted by id.

    Served from the Jev ``role_families`` table; ids match ``jobs.role_cluster``
    (SGSAL-022). Empty until ``ensure_schema``/the backfill has seeded the table.
    """
    try:
        families = get_store().get_role_families()
    except Exception:  # table missing / not migrated yet
        families = []
    return {
        "clusters": [
            {"id": f["id"], "name": f["display_name"], "key": f["key"]}
            for f in families
        ]
    }


@router.get("/api/jobs/{job_uuid}/reposts")
def get_job_reposts(job_uuid: str, _: str | None = Depends(get_optional_user)):
    """Public: the posting group a job belongs to — repost count, dates, per-occurrence
    salary/company history (SGSAL-024). Cached 1 h per job."""
    from mcf.api.cache.response import cache_get, cache_set, make_cache_key

    key = make_cache_key("jobs:reposts", job_uuid=job_uuid)
    if settings.enable_response_cache:
        cached = cache_get(key)
        if cached is not None:
            return cached
    store = get_store()
    group = store.get_posting_history(job_uuid)
    if group is None:
        job = store.get_job(job_uuid)  # title, company_name, is_active, first_seen_at (no salary)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        salary_rows = store.get_jobs_with_salary_by_uuids([job_uuid])
        if salary_rows:
            job = {**job, "salary_min": salary_rows[0].get("salary_min"), "salary_max": salary_rows[0].get("salary_max")}
        group = _single_occurrence_group(job)
    out = {
        "canonical_job_uuid": group.get("canonical_job_uuid"),
        "title": group.get("title"),
        "repost_count": int(group.get("repost_count") or 1),
        "active_count": int(group.get("active_count") or 0),
        "first_posted": _d(group.get("first_posted")),
        "last_posted": _d(group.get("last_posted")),
        "reposts_90d": int(group.get("reposts_90d") or 0),
        "reposts_365d": int(group.get("reposts_365d") or 0),
        "distinct_companies": int(group.get("distinct_companies") or 1),
        "latest_salary_min": group.get("latest_salary_min"),
        "latest_salary_max": group.get("latest_salary_max"),
        "min_salary_seen": group.get("min_salary_seen"),
        "max_salary_seen": group.get("max_salary_seen"),
        "occurrences": group.get("occurrences") or [],
    }
    if settings.enable_response_cache:
        cache_set(key, TTL_JOB_DETAIL, out)
    return out


def _d(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _single_occurrence_group(job: dict) -> dict:
    # get_job() has no posted_date; first_seen_at is the crawl date, which is the
    # same fallback the posting_groups view uses.
    date = job["first_seen_at"].date() if job.get("first_seen_at") else None
    return {
        "canonical_job_uuid": job["job_uuid"], "title": job.get("title"), "repost_count": 1,
        "active_count": 1 if job.get("is_active") else 0, "first_posted": date, "last_posted": date,
        "reposts_90d": 0, "reposts_365d": 0, "distinct_companies": 1,
        "latest_salary_min": job.get("salary_min"), "latest_salary_max": job.get("salary_max"),
        "min_salary_seen": job.get("salary_min"), "max_salary_seen": job.get("salary_max"),
        "occurrences": [{
            "job_uuid": job["job_uuid"], "date": _d(date), "company": job.get("company_name"),
            "salary_min": job.get("salary_min"), "salary_max": job.get("salary_max"),
            "is_active": bool(job.get("is_active")),
        }],
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
    user_id: str | None = Depends(get_optional_user),
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
