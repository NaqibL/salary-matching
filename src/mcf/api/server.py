"""FastAPI server."""

from __future__ import annotations

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, UploadFile, File, Header
from pydantic import BaseModel
from statistics import quantiles as _quantiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from mcf.api.auth import get_current_user, get_optional_user
from mcf.api.config import settings
from mcf.api.active_jobs_pool_cache import invalidate as invalidate_active_jobs_pool
from mcf.api.matches_cache import get_cached, invalidate_user, invalidate_all, set_cached, cache_stats as matches_cache_stats
from mcf.api.response_cache import (
    TTL_DASHBOARD,
    TTL_JOB_DETAIL,
    TTL_MATCHES,
    cache_invalidate,
    cache_response,
    cache_stats as response_cache_stats,
    cache_list_keys,
    invalidate_matches_for_user,
)
from mcf.api.services.matching_service import MatchingService
from mcf.lib.embeddings.base import EmbedderProtocol
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache
from mcf.lib.embeddings.resume import extract_resume_text, preprocess_resume_text
from mcf.lib.storage.base import Storage


def _make_store() -> Storage:
    """Return a DuckDBStore or PostgresStore depending on DATABASE_URL."""
    if settings.database_url:
        from mcf.lib.storage.postgres_store import PostgresStore

        return PostgresStore(settings.database_url)

    from mcf.lib.storage.duckdb_store import DuckDBStore

    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DuckDBStore(str(db_path))


# Global store — initialised in lifespan
_store: Storage | None = None


def _verify_admin_or_secret(
    authorization: str | None = Header(default=None),
    x_crawl_secret: str | None = Header(default=None, alias="X-Crawl-Secret"),
) -> str:
    """Allow access if X-Crawl-Secret matches OR JWT user is admin."""
    expected_secret = os.getenv("CRON_SECRET") or os.getenv("REVALIDATE_SECRET")
    if expected_secret and x_crawl_secret == expected_secret:
        return "crawl"
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        from mcf.api.auth import get_current_user
        try:
            user_id = get_current_user(authorization=authorization)
        except HTTPException:
            raise
        store = _store
        if store and settings.admin_user_ids_set and user_id in settings.admin_user_ids_set:
            return user_id
        if store:
            user = store.get_user_by_id(user_id)
            if user and user.get("role") == "admin":
                return user_id
    raise HTTPException(status_code=403, detail="Admin access required")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store
    _store = _make_store()
    # Pre-warm the active jobs pool so the first match request isn't cold.
    if settings.enable_active_jobs_pool_cache:
        try:
            from mcf.api.active_jobs_pool_cache import get_pool_or_fetch as _warm_pool
            _warm_pool(_store)
            logger.info("Active jobs pool warmed on startup")
        except Exception:
            logger.warning("Failed to warm active jobs pool on startup", exc_info=True)
    yield
    if _store:
        _store.close()


app = FastAPI(title="Job Matcher API", version="0.1.0", lifespan=lifespan)


def _add_cors_if_missing(response, request: Request) -> None:
    """Add CORS headers to response when missing (e.g. on 500 errors)."""
    origin = request.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        return
    existing = {h.lower() for h in response.headers}
    if "access-control-allow-origin" not in existing:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"


class CORSEnforcementMiddleware(BaseHTTPMiddleware):
    """Ensure CORS headers on all responses when request has Origin.

    FastAPI's CORSMiddleware can omit headers on 500 and other error paths. This
    safety net ensures the browser doesn't block with 'missing Allow Origin'.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            import traceback
            from starlette.responses import JSONResponse

            if not isinstance(exc, HTTPException):
                logging.error("Unhandled exception on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
            status = exc.status_code if isinstance(exc, HTTPException) else 500
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            response = JSONResponse(status_code=status, content={"detail": detail})
        _add_cors_if_missing(response, request)
        return response


# CORSEnforcement runs first (outermost); CORSMiddleware handles preflight and normal CORS
app.add_middleware(CORSEnforcementMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def get_store() -> Storage:
    if _store is None:
        raise RuntimeError("Store not initialised")
    return _store


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LowballCheckRequest(BaseModel):
    job_description: str
    salary: int | None = None  # single optional salary value (SGD/month)
    top_k: int = 20


class LowballResult(BaseModel):
    verdict: str  # "lowballed"|"below_median"|"at_median"|"above_median"|"insufficient_data"|"market_data"
    offered_salary: int | None  # None when no salary was provided
    percentile: float | None
    market_p25: int | None
    market_p50: int | None
    market_p75: int | None
    salary_coverage: int
    total_matched: int
    similar_jobs: list[dict]


class SalarySearchRequest(BaseModel):
    job_description: str
    salary_min: int | None = None
    salary_max: int | None = None
    top_k: int = 25
    offset: int = 0


class SalarySearchJob(BaseModel):
    job_uuid: str
    title: str
    company_name: str | None
    location: str | None
    job_url: str | None
    salary_min: int | None
    salary_max: int | None
    similarity_score: float
    last_seen_at: str | None


class SalarySearchResult(BaseModel):
    jobs: list[SalarySearchJob]
    total: int
    market_p25: int | None
    market_p50: int | None
    market_p75: int | None
    salary_coverage: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_similar_jobs(jobs: list[dict], uuid_to_score: dict[str, float]) -> list[dict]:
    return [
        {
            "job_uuid": j["job_uuid"],
            "title": j["title"],
            "company_name": j["company_name"],
            "job_url": j.get("job_url"),
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "similarity_score": round(uuid_to_score.get(j["job_uuid"], 0.0), 4),
        }
        for j in jobs
    ]


def _salary_percentiles(salaries: list[int]) -> tuple[int, int, int]:
    qs = _quantiles(salaries, n=4)  # [p25, p50, p75]
    return int(qs[0]), int(qs[1]), int(qs[2])


# ---------------------------------------------------------------------------
# Job endpoints
# ---------------------------------------------------------------------------


@app.get("/api/jobs/taxonomy")
def get_job_taxonomy():
    """Return role cluster taxonomy: list of {id, name} sorted by id."""
    import mcf.lib.classifiers as _cls
    _cls._load()
    return {
        "clusters": [
            {"id": k, "name": v}
            for k, v in sorted((_cls._taxonomy or {}).items())
        ]
    }


@app.get("/api/jobs/interested")
def get_interested_jobs(user_id: str = Depends(get_current_user)):
    """Return jobs the user has marked as interested, ordered by most recent first."""
    store = get_store()
    jobs = store.get_interested_jobs(user_id=user_id)
    return {"jobs": jobs}


@app.post("/api/jobs/{job_uuid}/interact")
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


@app.get("/api/jobs/{job_uuid}")
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


@app.get("/api/discover/stats")
def get_discover_stats(user_id: str = Depends(get_current_user)):
    """Return counts of interested, not_interested, and unrated jobs."""
    store = get_store()
    return store.get_discover_stats(user_id=user_id)


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@app.get("/api/dashboard/summary")
@cache_response(TTL_DASHBOARD, "dashboard:summary")
def get_dashboard_summary(user_id: str = Depends(get_current_user)):
    """Return dashboard summary: total jobs, active, by source (MCF only), jobs with embeddings."""
    store = get_store()
    return store.get_dashboard_summary()


@app.get("/api/dashboard/summary-public")
@cache_response(TTL_DASHBOARD, "dashboard:summary-public")
def get_dashboard_summary_public():
    """Public endpoint for summary stats (no auth). Used on login screen."""
    store = get_store()
    return store.get_dashboard_summary()


@app.get("/api/dashboard/jobs-over-time-posted-and-removed")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-over-time")
def get_dashboard_jobs_over_time_posted_and_removed(
    limit_days: int = Query(default=90, ge=1, le=365),
    user_id: str = Depends(get_current_user),
):
    """Return daily added and removed job counts from job_daily_stats."""
    store = get_store()
    return store.get_jobs_over_time_posted_and_removed(limit_days=limit_days)


@app.get("/api/dashboard/jobs-over-time-posted-and-removed-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-over-time-public")
def get_dashboard_jobs_over_time_posted_and_removed_public(
    limit_days: int = Query(default=90, ge=1, le=365),
):
    """Public endpoint for added/removed counts (no auth). Used by Next.js cached routes."""
    store = get_store()
    return store.get_jobs_over_time_posted_and_removed(limit_days=limit_days)


@app.get("/api/dashboard/active-jobs-over-time")
@cache_response(TTL_DASHBOARD, "dashboard:active-jobs-over-time")
def get_dashboard_active_jobs_over_time(
    limit_days: int = Query(default=90, ge=1, le=365),
    user_id: str = Depends(get_current_user),
):
    """Return total active jobs per day from job_daily_stats."""
    store = get_store()
    return store.get_active_jobs_over_time(limit_days=limit_days)


@app.get("/api/dashboard/active-jobs-over-time-public")
@cache_response(TTL_DASHBOARD, "dashboard:active-jobs-over-time-public")
def get_dashboard_active_jobs_over_time_public(
    limit_days: int = Query(default=30, ge=1, le=365),
):
    """Public endpoint for active jobs over time (no auth). Used on login screen."""
    store = get_store()
    return store.get_active_jobs_over_time(limit_days=limit_days)


@app.get("/api/dashboard/jobs-by-category")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-category")
def get_dashboard_jobs_by_category(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=30, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by MCF category (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_category(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/jobs-by-category-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-category-public")
def get_dashboard_jobs_by_category_public(
    limit_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=8, ge=1, le=50),
):
    """Public endpoint for jobs by category (no auth). Used on login screen."""
    store = get_store()
    return store.get_jobs_by_category(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/category-trends")
@cache_response(TTL_DASHBOARD, "dashboard:category-trends")
def get_dashboard_category_trends(
    category: str = Query(..., min_length=1),
    limit_days: int = Query(default=90, ge=1, le=365),
    _: str | None = Depends(get_optional_user),
):
    """Return trend data for a specific category from job_daily_stats."""
    store = get_store()
    return store.get_category_trends(category=category, limit_days=limit_days)


@app.get("/api/dashboard/category-stats")
@cache_response(TTL_DASHBOARD, "dashboard:category-stats")
def get_dashboard_category_stats(
    category: str = Query(..., min_length=1),
    _: str | None = Depends(get_optional_user),
):
    """Return employment type, position level, salary breakdown for a category."""
    store = get_store()
    return store.get_category_stats(category=category)


@app.get("/api/dashboard/jobs-by-employment-type")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-employment-type")
def get_dashboard_jobs_by_employment_type(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by employment type (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_employment_type(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/jobs-by-position-level")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-position-level")
def get_dashboard_jobs_by_position_level(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by position level (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_position_level(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/salary-distribution")
@cache_response(TTL_DASHBOARD, "dashboard:salary-distribution")
def get_dashboard_salary_distribution(_: str | None = Depends(get_optional_user)):
    """Return salary distribution buckets (from jobs.salary_min)."""
    store = get_store()
    return store.get_salary_distribution()


@app.get("/api/dashboard/jobs-by-employment-type-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-employment-type-public")
def get_dashboard_jobs_by_employment_type_public(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public endpoint for jobs by employment type (no auth)."""
    store = get_store()
    return store.get_jobs_by_employment_type(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/jobs-by-position-level-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-position-level-public")
def get_dashboard_jobs_by_position_level_public(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public endpoint for jobs by position level (no auth)."""
    store = get_store()
    return store.get_jobs_by_position_level(limit_days=limit_days, limit=limit)


@app.get("/api/dashboard/salary-distribution-public")
@cache_response(TTL_DASHBOARD, "dashboard:salary-distribution-public")
def get_dashboard_salary_distribution_public():
    """Public endpoint for salary distribution (no auth)."""
    store = get_store()
    return store.get_salary_distribution()


@app.get("/api/dashboard/charts-static")
@cache_response(TTL_DASHBOARD, "dashboard:charts-static")
def get_dashboard_charts_static(_: str | None = Depends(get_optional_user)):
    """Return all time-range-independent chart data in a single response."""
    store = get_store()
    return store.get_charts_static()


@app.get("/api/dashboard/charts-static-public")
@cache_response(TTL_DASHBOARD, "dashboard:charts-static-public")
def get_dashboard_charts_static_public():
    """Public endpoint for all static chart data (no auth). Used by Next.js cached route."""
    store = get_store()
    return store.get_charts_static()


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------


@app.get("/api/profile")
def get_profile(user_id: str = Depends(get_current_user)):
    """Get current user profile and resume status."""
    store = get_store()
    profile = store.get_profile_by_user_id(user_id)
    resume_path = Path(settings.resume_path)
    resume_exists = resume_path.exists()
    return {
        "user_id": user_id,
        "profile": profile,
        "resume_path": str(resume_path),
        "resume_exists": resume_exists,
    }


@app.post("/api/profile/process-resume")
async def process_resume(user_id: str = Depends(get_current_user)):
    """Process resume from local file or Supabase Storage.

    Tries local file first (dev). If not found and profile has resume_storage_path,
    fetches from Supabase Storage and processes that. Fixes Re-process in production.
    """
    store = get_store()
    resume_path = Path(settings.resume_path)

    if resume_path.exists():
        try:
            resume_text = extract_resume_text(resume_path)
            return _process_resume_text(store, user_id, resume_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")

    # Local file missing — try Supabase Storage
    profile = store.get_profile_by_user_id(user_id)
    if not profile or not profile.get("resume_storage_path"):
        raise HTTPException(
            status_code=404,
            detail="No resume found. Upload a resume first, or ensure the file exists at the configured path.",
        )

    storage_path = profile["resume_storage_path"]
    if not settings.storage_enabled:
        raise HTTPException(
            status_code=503,
            detail="Resume is in cloud storage but Supabase Storage is not configured.",
        )

    try:
        data = await _download_from_supabase(storage_path)
        resume_text = extract_resume_text(data)
        return _process_resume_text(store, user_id, resume_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume from storage: {e}")


@app.post("/api/profile/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """Upload a resume file, extract its text, and update the profile + embedding.

    Accepts PDF or DOCX.  If Supabase Storage is configured the raw file is
    also stored there so it can be re-processed later.
    """
    allowed = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Upload a PDF or DOCX.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Optionally push to Supabase Storage
    storage_path: str | None = None
    if settings.storage_enabled:
        storage_path = await _upload_to_supabase(data, user_id, file.filename or "resume.pdf")

    try:
        resume_text = extract_resume_text(data)
        store = get_store()
        result = _process_resume_text(store, user_id, resume_text, storage_path=storage_path)
        result["storage_path"] = storage_path
        return result
    except Exception as e:
        logging.exception("upload_resume failed")
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")


def _process_resume_text(
    store: Storage, user_id: str, resume_text: str, storage_path: str | None = None
) -> dict:
    """Create/update profile + embedding from resume text. Returns response dict."""
    profile = store.get_profile_by_user_id(user_id)
    if profile:
        profile_id = profile["profile_id"]
        store.update_profile(
            profile_id=profile_id,
            raw_resume_text=resume_text,
            resume_storage_path=storage_path,
        )
    else:
        profile_id = secrets.token_urlsafe(16)
        store.create_profile(
            profile_id=profile_id,
            user_id=user_id,
            raw_resume_text=resume_text,
        )
        if storage_path:
            store.update_profile(profile_id=profile_id, resume_storage_path=storage_path)

    embeddings_cache = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    embedder: EmbedderProtocol = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache)
    preprocessed = preprocess_resume_text(resume_text)
    try:
        embedding = embedder.embed_resume(preprocessed)
    except Exception as e:
        logging.exception("embed_resume failed: %s", e)
        raise
    store.upsert_candidate_embedding(
        profile_id=profile_id,
        model_name=embedder.model_name,
        embedding=embedding,
    )
    if settings.enable_matches_cache:
        invalidate_user(user_id)
    if settings.enable_response_cache:
        invalidate_matches_for_user(user_id)
    return {"status": "ok", "profile_id": profile_id, "message": "Resume processed successfully"}


async def _download_from_supabase(storage_path: str) -> bytes:
    """Download file bytes from Supabase Storage. storage_path is e.g. resumes/{user_id}/resume.pdf."""
    url = f"{settings.supabase_url}/storage/v1/object/{storage_path}"
    headers = {"Authorization": f"Bearer {settings.supabase_service_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch resume from storage: {resp.status_code} {resp.text[:200]}",
            )
    return resp.content


async def _upload_to_supabase(data: bytes, user_id: str, filename: str) -> str:
    """Upload file bytes to Supabase Storage and return the storage path."""
    ext = Path(filename).suffix or ".pdf"
    path = f"resumes/{user_id}/resume{ext}"
    url = f"{settings.supabase_url}/storage/v1/object/resumes/{user_id}/resume{ext}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/octet-stream",
        "x-upsert": "true",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.put(url, content=data, headers=headers, timeout=30.0)
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Supabase Storage upload failed: {resp.status_code} {resp.text}",
            )
    return path


# ---------------------------------------------------------------------------
# Matching endpoints
# ---------------------------------------------------------------------------


@app.post("/api/profile/reset-ratings")
def reset_ratings(user_id: str = Depends(get_current_user)):
    """Reset job interactions and taste profile for the current user (for testing)."""
    store = get_store()
    result = store.reset_profile_ratings(user_id)
    return result


@app.post("/api/profile/compute-taste")
def compute_taste(user_id: str = Depends(get_current_user)):
    """Build / refresh the taste-profile embedding from Interested/Not Interested ratings."""
    store = get_store()
    profile = store.get_profile_by_user_id(user_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail="No profile found. Please process your resume first."
        )
    result = MatchingService(store).compute_and_store_taste(
        profile_id=profile["profile_id"], user_id=user_id
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("reason", "Failed to compute taste profile")
        )
    if settings.enable_matches_cache:
        invalidate_user(user_id)
    if settings.enable_response_cache:
        invalidate_matches_for_user(user_id)
    return result


@app.get("/api/matches")
@cache_response(TTL_MATCHES, "matches")
def get_matches(
    exclude_interacted: bool = True,
    exclude_rated_only: bool = False,
    top_k: int = 25,
    offset: int = 0,
    min_similarity: float = 0.0,
    max_days_old: int | None = None,
    mode: str = "resume",
    session_id: str | None = None,
    role_cluster: list[int] = Query(default=[]),
    predicted_tier: list[str] = Query(default=[]),
    user_id: str = Depends(get_current_user),
):
    """Get job matches for the current user.

    *mode* is ``resume`` (default) or ``taste``.
    *exclude_rated_only*: when True, only exclude interested/not_interested (for Discover).
    When False, exclude all interactions (viewed, dismissed, etc.).
    """
    if settings.enable_matches_cache:
        cached = get_cached(
            user_id=user_id,
            mode=mode,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            top_k=top_k,
            offset=offset,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
        )
        if cached is not None:
            return cached

    store = get_store()
    if mode not in ("resume", "taste"):
        raise HTTPException(status_code=400, detail="mode must be 'resume' or 'taste'")
    if not 0.0 <= min_similarity <= 1.0:
        raise HTTPException(status_code=400, detail="min_similarity must be between 0.0 and 1.0")
    if max_days_old is not None and max_days_old <= 0:
        max_days_old = None  # Treat invalid/zero as no filter
    if offset < 0:
        offset = 0

    profile = store.get_profile_by_user_id(user_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail="No profile found. Please process your resume first."
        )

    profile_id = profile["profile_id"]
    svc = MatchingService(store)

    candidate_tier: str | None = None
    if mode == "taste":
        taste_emb = store.get_taste_embedding(profile_id)
        if not taste_emb:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No taste profile found. Go to Resume, rate some jobs, "
                    "then click Update Taste Profile."
                ),
            )
        matches, total, new_session_id = svc.match_taste_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            offset=offset,
            exclude_rated=exclude_interacted,
            user_id=user_id,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            role_clusters=role_cluster or None,
            predicted_tiers=predicted_tier or None,
        )
    else:
        # exclude_rated_only: only interested/not_interested (Discover). Else all interactions.
        matches, total, new_session_id, candidate_tier = svc.match_candidate_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            offset=offset,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            user_id=user_id,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            role_clusters=role_cluster or None,
            predicted_tiers=predicted_tier or None,
        )

    has_more = offset + len(matches) < total
    result = {
        "matches": matches,
        "total": total,
        "has_more": has_more,
        "mode": mode,
        "session_id": new_session_id,
        "candidate_tier": candidate_tier,
    }
    if settings.enable_matches_cache:
        set_cached(
            user_id=user_id,
            mode=mode,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            top_k=top_k,
            offset=offset,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            result=result,
        )
    return result


# ---------------------------------------------------------------------------
# Admin (cache invalidation, stats)
# ---------------------------------------------------------------------------


@app.post("/api/admin/invalidate-pool")
def admin_invalidate_pool(_: str = Depends(_verify_admin_or_secret)):
    """Invalidate the active jobs pool cache. Call after crawl completes.

    Auth: X-Crawl-Secret header or JWT with admin role / ADMIN_USER_IDS.
    """
    if settings.enable_active_jobs_pool_cache:
        invalidate_active_jobs_pool()
    return {"status": "ok"}


@app.post("/api/admin/invalidate-cache")
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


@app.get("/api/admin/cache-stats")
def admin_cache_stats(_: str = Depends(_verify_admin_or_secret)):
    """Cache hit rates and key counts. Auth: X-Crawl-Secret or admin JWT."""
    return {
        "response_cache": response_cache_stats(),
        "matches_cache": matches_cache_stats(),
    }


@app.get("/api/admin/cache-keys")
def admin_cache_keys(
    _: str = Depends(_verify_admin_or_secret),
    prefix: str = Query(default="", description="Filter by prefix"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """List cache keys (for debugging). Auth: X-Crawl-Secret or admin JWT."""
    return {"keys": cache_list_keys(prefix=prefix, limit=limit)}


@app.delete("/api/admin/cache")
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


@app.get("/api/admin/cache-timestamp")
def admin_cache_timestamp(_: str = Depends(_verify_admin_or_secret)):
    """Last crawl/cache update timestamp from DB. Auth: X-Crawl-Secret or admin JWT."""
    store = _store
    if not store or not hasattr(store, "get_cache_metadata"):
        return {"last_updated": None}
    try:
        row = store.get_cache_metadata("crawl_completed_at")
        return {"last_updated": str(row["updated_at"]) if row else None}
    except Exception:
        return {"last_updated": None}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/cors-check")
def cors_check(request: Request):
    """Debug: returns request origin and whether it's in ALLOWED_ORIGINS.

    Use this to verify CORS is configured correctly when upload fails with
    'CORS missing Allow Origin'. Call from the browser console:
    fetch('https://your-api.railway.app/api/cors-check').then(r=>r.json()).then(console.log)
    """
    origin = request.headers.get("origin", "(none)")
    allowed = settings.cors_origins
    return {
        "request_origin": origin,
        "allowed_origins": allowed,
        "origin_allowed": origin in allowed,
    }


# ---------------------------------------------------------------------------
# Lowball checker
# ---------------------------------------------------------------------------


@app.post("/api/lowball/check")
def check_lowball(body: LowballCheckRequest, _: str | None = Depends(get_optional_user)):
    """Check if an offered salary is competitive for a described role."""
    store = get_store()
    embeddings_cache_inst = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    embedder: EmbedderProtocol = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache_inst)
    vector = embedder.embed_text(body.job_description)

    if settings.enable_active_jobs_pool_cache:
        from mcf.api.active_jobs_pool_cache import get_pool_or_fetch, compute_ranked_from_pool
        pool = get_pool_or_fetch(store)
        ranked = compute_ranked_from_pool(pool, vector, limit=500)
    else:
        ranked = store.get_active_job_ids_ranked(vector, limit=500)

    top_slice = ranked[: body.top_k * 5]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in top_slice}

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))
    salary_jobs = [j for j in jobs if j.get("salary_min") is not None]
    similar = _build_similar_jobs(jobs[:body.top_k], uuid_to_score)

    # Compute market percentiles regardless of whether salary was provided
    if len(salary_jobs) < 5:
        return LowballResult(
            verdict="insufficient_data", offered_salary=body.salary,
            percentile=None, market_p25=None, market_p50=None, market_p75=None,
            salary_coverage=len(salary_jobs), total_matched=len(jobs),
            similar_jobs=similar,
        )

    salaries = sorted(j["salary_min"] for j in salary_jobs)
    p25, p50, p75 = _salary_percentiles(salaries)

    # No salary provided — return market data only
    if body.salary is None:
        return LowballResult(
            verdict="market_data", offered_salary=None,
            percentile=None, market_p25=p25, market_p50=p50, market_p75=p75,
            salary_coverage=len(salary_jobs), total_matched=len(jobs),
            similar_jobs=similar,
        )

    # Salary provided — compute verdict and percentile
    offered = body.salary
    percentile = round(sum(1 for s in salaries if s <= offered) / len(salaries) * 100, 1)

    if offered < p25:
        verdict = "lowballed"
    elif offered < p50:
        verdict = "below_median"
    elif offered < p75:
        verdict = "at_median"
    else:
        verdict = "above_median"

    return LowballResult(
        verdict=verdict, offered_salary=offered, percentile=percentile,
        market_p25=p25, market_p50=p50, market_p75=p75,
        salary_coverage=len(salary_jobs), total_matched=len(jobs),
        similar_jobs=similar,
    )


# ---------------------------------------------------------------------------
# Salary search
# ---------------------------------------------------------------------------


@app.post("/api/salary/search")
def salary_search(body: SalarySearchRequest, _: str | None = Depends(get_optional_user)):
    """Semantic job search filtered by salary range."""
    store = get_store()
    embeddings_cache_inst = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    embedder: EmbedderProtocol = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache_inst)
    vector = embedder.embed_text(body.job_description)

    if settings.enable_active_jobs_pool_cache:
        from mcf.api.active_jobs_pool_cache import get_pool_or_fetch, compute_ranked_from_pool
        pool, matrix = get_pool_or_fetch(store)
        ranked = compute_ranked_from_pool(pool, vector, matrix=matrix)
    else:
        ranked = store.get_active_job_ids_ranked(vector, limit=50_000)

    # Apply salary filter as an allowlist
    salary_allowed = store.get_job_uuids_with_salary_filter(body.salary_min, body.salary_max)
    if salary_allowed is not None:
        filtered = [(uuid, dist, last_seen) for uuid, dist, last_seen in ranked if uuid in salary_allowed]
    else:
        filtered = list(ranked)

    total = len(filtered)
    page_slice = filtered[body.offset : body.offset + body.top_k]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in page_slice}

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))

    # Compute market percentiles from top-500 semantically similar salary-bearing jobs
    top_500_uuids = [uuid for uuid, _, _ in filtered[:500]]
    salary_pool = store.get_jobs_with_salary_by_uuids(top_500_uuids)
    salary_values = sorted(j["salary_min"] for j in salary_pool if j.get("salary_min") is not None)

    p25 = p50 = p75 = None
    if len(salary_values) >= 5:
        p25, p50, p75 = _salary_percentiles(salary_values)

    result_jobs = [
        SalarySearchJob(
            job_uuid=j["job_uuid"],
            title=j.get("title") or "",
            company_name=j.get("company_name"),
            location=j.get("location"),
            job_url=j.get("job_url"),
            salary_min=j.get("salary_min"),
            salary_max=j.get("salary_max"),
            similarity_score=uuid_to_score.get(j["job_uuid"], 0.0),
            last_seen_at=str(j["last_seen_at"]) if j.get("last_seen_at") else None,
        )
        for j in jobs
    ]

    return SalarySearchResult(
        jobs=result_jobs,
        total=total,
        market_p25=p25,
        market_p50=p50,
        market_p75=p75,
        salary_coverage=len(salary_values),
    )
