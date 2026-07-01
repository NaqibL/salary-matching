"""Hot jobs route — active listings paying above their peer-group median salary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from mcf.api.cache.response import TTL_DASHBOARD, cache_response
from mcf.api.deps import get_store
from mcf.lib.storage.base import Storage

router = APIRouter()

MIN_ABOVE_MARKET_PCT = 20.0


class HotJob(BaseModel):
    job_uuid: str
    title: str | None
    company_name: str | None
    salary_min: int | None
    salary_max: int | None
    above_market_pct: float | None
    job_url: str | None
    cluster_label: str | None
    categories: list[str]
    position_levels: list[str]
    inferred_seniority: str | None
    canonical_skills: list[str] | None
    posted_date: str | None


class HotJobsResponse(BaseModel):
    jobs: list[HotJob]
    count: int


@router.get("/api/hot-jobs")
@cache_response(
    ttl_seconds=TTL_DASHBOARD // 6,  # 10 min
    key_prefix="hot-jobs:list",
    key_builder=lambda **kw: f"{kw.get('category')}:{kw.get('position_level')}:{kw.get('limit')}",
)
def get_hot_jobs(
    category: str | None = None,
    position_level: str | None = None,
    limit: int = Query(default=50, le=200),
    store: Storage = Depends(get_store),
) -> HotJobsResponse:
    """Active jobs paying >= 20% above their peer-group (cluster x seniority) median."""
    jobs = store.get_hot_jobs(
        min_pct=MIN_ABOVE_MARKET_PCT,
        category=category,
        position_level=position_level,
        limit=limit,
    )
    return HotJobsResponse(jobs=[HotJob(**j) for j in jobs], count=len(jobs))
