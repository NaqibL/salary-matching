"""Dashboard API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from mcf.api.auth import get_current_user, get_optional_user
from mcf.api.cache.response import TTL_DASHBOARD, cache_response
from mcf.api.deps import get_store

router = APIRouter()


@router.get("/api/dashboard/summary")
@cache_response(TTL_DASHBOARD, "dashboard:summary")
def get_dashboard_summary(user_id: str = Depends(get_current_user)):
    """Return dashboard summary: total jobs, active, by source (MCF only), jobs with embeddings."""
    store = get_store()
    return store.get_dashboard_summary()


@router.get("/api/dashboard/summary-public")
@cache_response(TTL_DASHBOARD, "dashboard:summary-public")
def get_dashboard_summary_public():
    """Public endpoint for summary stats (no auth). Used on login screen."""
    store = get_store()
    return store.get_dashboard_summary()


@router.get("/api/dashboard/jobs-over-time-posted-and-removed")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-over-time")
def get_dashboard_jobs_over_time_posted_and_removed(
    limit_days: int = Query(default=90, ge=1, le=365),
    user_id: str = Depends(get_current_user),
):
    """Return daily added and removed job counts from job_daily_stats."""
    store = get_store()
    return store.get_jobs_over_time_posted_and_removed(limit_days=limit_days)


@router.get("/api/dashboard/jobs-over-time-posted-and-removed-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-over-time-public")
def get_dashboard_jobs_over_time_posted_and_removed_public(
    limit_days: int = Query(default=90, ge=1, le=365),
):
    """Public endpoint for added/removed counts (no auth). Used by Next.js cached routes."""
    store = get_store()
    return store.get_jobs_over_time_posted_and_removed(limit_days=limit_days)


@router.get("/api/dashboard/active-jobs-over-time")
@cache_response(TTL_DASHBOARD, "dashboard:active-jobs-over-time")
def get_dashboard_active_jobs_over_time(
    limit_days: int = Query(default=90, ge=1, le=365),
    user_id: str = Depends(get_current_user),
):
    """Return total active jobs per day from job_daily_stats."""
    store = get_store()
    return store.get_active_jobs_over_time(limit_days=limit_days)


@router.get("/api/dashboard/active-jobs-over-time-public")
@cache_response(TTL_DASHBOARD, "dashboard:active-jobs-over-time-public")
def get_dashboard_active_jobs_over_time_public(
    limit_days: int = Query(default=30, ge=1, le=365),
):
    """Public endpoint for active jobs over time (no auth). Used on login screen."""
    store = get_store()
    return store.get_active_jobs_over_time(limit_days=limit_days)


@router.get("/api/dashboard/jobs-by-category")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-category")
def get_dashboard_jobs_by_category(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=30, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by MCF category (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_category(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/jobs-by-category-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-category-public")
def get_dashboard_jobs_by_category_public(
    limit_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=8, ge=1, le=50),
):
    """Public endpoint for jobs by category (no auth). Used on login screen."""
    store = get_store()
    return store.get_jobs_by_category(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/category-trends")
@cache_response(TTL_DASHBOARD, "dashboard:category-trends")
def get_dashboard_category_trends(
    category: str = Query(..., min_length=1),
    limit_days: int = Query(default=90, ge=1, le=365),
    _: str | None = Depends(get_optional_user),
):
    """Return trend data for a specific category from job_daily_stats."""
    store = get_store()
    return store.get_category_trends(category=category, limit_days=limit_days)


@router.get("/api/dashboard/category-stats")
@cache_response(TTL_DASHBOARD, "dashboard:category-stats")
def get_dashboard_category_stats(
    category: str = Query(..., min_length=1),
    _: str | None = Depends(get_optional_user),
):
    """Return employment type, position level, salary breakdown for a category."""
    store = get_store()
    return store.get_category_stats(category=category)


@router.get("/api/dashboard/jobs-by-employment-type")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-employment-type")
def get_dashboard_jobs_by_employment_type(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by employment type (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_employment_type(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/jobs-by-position-level")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-position-level")
def get_dashboard_jobs_by_position_level(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
    _: str | None = Depends(get_optional_user),
):
    """Return job counts by position level (from job_daily_stats)."""
    store = get_store()
    return store.get_jobs_by_position_level(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/salary-distribution")
@cache_response(TTL_DASHBOARD, "dashboard:salary-distribution")
def get_dashboard_salary_distribution(_: str | None = Depends(get_optional_user)):
    """Return salary distribution buckets (from jobs.salary_min)."""
    store = get_store()
    return store.get_salary_distribution()


@router.get("/api/dashboard/jobs-by-employment-type-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-employment-type-public")
def get_dashboard_jobs_by_employment_type_public(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public endpoint for jobs by employment type (no auth)."""
    store = get_store()
    return store.get_jobs_by_employment_type(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/jobs-by-position-level-public")
@cache_response(TTL_DASHBOARD, "dashboard:jobs-by-position-level-public")
def get_dashboard_jobs_by_position_level_public(
    limit_days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public endpoint for jobs by position level (no auth)."""
    store = get_store()
    return store.get_jobs_by_position_level(limit_days=limit_days, limit=limit)


@router.get("/api/dashboard/salary-distribution-public")
@cache_response(TTL_DASHBOARD, "dashboard:salary-distribution-public")
def get_dashboard_salary_distribution_public():
    """Public endpoint for salary distribution (no auth)."""
    store = get_store()
    return store.get_salary_distribution()


@router.get("/api/dashboard/charts-static")
@cache_response(TTL_DASHBOARD, "dashboard:charts-static")
def get_dashboard_charts_static(_: str | None = Depends(get_optional_user)):
    """Return all time-range-independent chart data in a single response."""
    store = get_store()
    return store.get_charts_static()


@router.get("/api/dashboard/charts-static-public")
@cache_response(TTL_DASHBOARD, "dashboard:charts-static-public")
def get_dashboard_charts_static_public():
    """Public endpoint for all static chart data (no auth). Used by Next.js cached route."""
    store = get_store()
    return store.get_charts_static()
