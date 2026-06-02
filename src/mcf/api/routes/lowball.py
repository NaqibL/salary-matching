"""Lowball checker and salary search routes."""

from __future__ import annotations

import json as _json
from statistics import quantiles as _quantiles

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from mcf.api.auth import get_optional_user
from mcf.api.cache.job_pool import compute_ranked_from_pool, get_pool_or_fetch
from mcf.api.config import settings
from mcf.api.deps import get_embedder, get_store
from mcf.api.limiter import limiter
from mcf.lib.embeddings.base import EmbedderProtocol
from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description
from mcf.lib.storage.base import Storage

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LowballCheckRequest(BaseModel):
    title: str = Field(max_length=500)
    description: str = Field(max_length=20_000)
    salary: int | None = Field(default=None, ge=0, le=500_000)
    top_k: int = Field(default=20, ge=1, le=100)
    company_name: str | None = Field(default=None, max_length=200)


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
    company_similar_jobs: list[dict] | None = None


class SalarySearchRequest(BaseModel):
    title: str = Field(max_length=500)
    description: str = Field(max_length=20_000)
    salary_min: int | None = Field(default=None, ge=0, le=500_000)
    salary_max: int | None = Field(default=None, ge=0, le=500_000)
    top_k: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


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


def _build_similar_jobs(jobs: list[dict], uuid_to_score: dict[str, float], top_k: int) -> list[dict]:
    result = []
    for j in jobs:
        raw_desc = j.get("description") or ""
        llm_raw = j.get("llm_fields_json")
        llm = _json.loads(llm_raw) if isinstance(llm_raw, str) else (llm_raw or {})
        result.append({
            "job_uuid": j["job_uuid"],
            "title": j["title"],
            "company_name": j.get("company_name"),
            "location": j.get("location"),
            "job_url": j.get("job_url"),
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "is_active": j.get("is_active", True),
            "description": raw_desc or None,
            "similarity_score": round(uuid_to_score.get(j["job_uuid"], 0.0), 4),
            "min_years_experience": j.get("min_years_experience"),
            "inferred_seniority": llm.get("inferred_seniority"),
            "canonical_skills": llm.get("canonical_skills"),
        })
    result.sort(key=lambda x: x["similarity_score"], reverse=True)
    return result[:top_k]


def _effective_salary(job: dict) -> int | None:
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo is not None and hi is not None:
        return (lo + hi) // 2
    return lo


def _salary_percentiles(salaries: list[int]) -> tuple[int, int, int]:
    qs = _quantiles(salaries, n=4)  # [p25, p50, p75]
    return int(qs[0]), int(qs[1]), int(qs[2])


# ---------------------------------------------------------------------------
# Lowball checker
# ---------------------------------------------------------------------------


@router.post("/api/lowball/check")
@limiter.limit("10/minute")
def check_lowball(
    request: Request,
    body: LowballCheckRequest,
    _: str | None = Depends(get_optional_user),
    store: Storage = Depends(get_store),
    embedder: EmbedderProtocol = Depends(get_embedder),
):
    """Check if an offered salary is competitive for a described role."""
    description_text, _ = extract_high_signal_description(body.description, body.title)
    job_text = f"Job Title: {body.title}\nDescription: {description_text}"
    vector = embedder.embed_text(job_text)

    if settings.enable_active_jobs_pool_cache:
        pool, matrix = get_pool_or_fetch(store)
        ranked = compute_ranked_from_pool(pool, vector, limit=500, matrix=matrix)
    else:
        ranked = store.get_all_embedded_job_ids_ranked(vector, limit=500)

    # Company-specific results (computed before early returns so all branches can include it)
    company_similar_jobs = None
    if body.company_name:
        company_uuids = store.get_active_job_uuids_by_company(body.company_name)
        company_ranked = [(uuid, dist) for uuid, dist, _ in ranked if uuid in company_uuids][: body.top_k]
        if company_ranked:
            c_uuids = [uuid for uuid, _ in company_ranked]
            c_scores = {uuid: round(1.0 - dist, 4) for uuid, dist in company_ranked}
            c_jobs = store.get_jobs_with_salary_by_uuids(c_uuids)
            company_similar_jobs = _build_similar_jobs(c_jobs, c_scores, body.top_k)

    top_slice = ranked[: body.top_k * 5]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in top_slice}

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))
    # Salary benchmark pool uses compliant ranges only (EP rule: salary_max <= 2 * salary_min).
    # Display cards (similar_jobs) still use the full unfiltered fetch above.
    salary_jobs = store.get_jobs_with_salary_by_uuids(
        list(uuid_to_score.keys()), compliant_ranges_only=True
    )
    salary_jobs = [j for j in salary_jobs if j.get("salary_min") is not None]
    similar = _build_similar_jobs(jobs, uuid_to_score, body.top_k)

    # Compute market percentiles regardless of whether salary was provided
    if len(salary_jobs) < 5:
        return LowballResult(
            verdict="insufficient_data", offered_salary=body.salary,
            percentile=None, market_p25=None, market_p50=None, market_p75=None,
            salary_coverage=len(salary_jobs), total_matched=len(jobs),
            similar_jobs=similar, company_similar_jobs=company_similar_jobs,
        )

    salaries = sorted(s for j in salary_jobs if (s := _effective_salary(j)) is not None)
    p25, p50, p75 = _salary_percentiles(salaries)

    # No salary provided — return market data only
    if body.salary is None:
        return LowballResult(
            verdict="market_data", offered_salary=None,
            percentile=None, market_p25=p25, market_p50=p50, market_p75=p75,
            salary_coverage=len(salaries), total_matched=len(jobs),
            similar_jobs=similar, company_similar_jobs=company_similar_jobs,
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
        salary_coverage=len(salaries), total_matched=len(jobs),
        similar_jobs=similar, company_similar_jobs=company_similar_jobs,
    )


# ---------------------------------------------------------------------------
# Salary search
# ---------------------------------------------------------------------------


@router.post("/api/salary/search")
@limiter.limit("10/minute")
def salary_search(
    request: Request,
    body: SalarySearchRequest,
    _: str | None = Depends(get_optional_user),
    store: Storage = Depends(get_store),
    embedder: EmbedderProtocol = Depends(get_embedder),
):
    """Semantic job search filtered by salary range."""
    description_text, _ = extract_high_signal_description(body.description, body.title)
    job_text = f"Job Title: {body.title}\nDescription: {description_text}"
    vector = embedder.embed_text(job_text)

    if settings.enable_active_jobs_pool_cache:
        pool, matrix = get_pool_or_fetch(store)
        ranked_all = compute_ranked_from_pool(pool, vector, limit=500, matrix=matrix)
    else:
        ranked_all = store.get_all_embedded_job_ids_ranked(vector, limit=500)

    # Active-only gate for displayed results (users are browsing to apply)
    active_uuids = store.active_job_uuids()

    # Salary range filter (active-only) — only applied when the user specified a range
    salary_allowed = store.get_job_uuids_with_salary_filter(body.salary_min, body.salary_max)

    # Displayed jobs: active AND in salary range (if specified)
    display_gate = salary_allowed if salary_allowed is not None else active_uuids
    filtered = [(uuid, dist, last_seen) for uuid, dist, last_seen in ranked_all if uuid in display_gate]

    total = len(filtered)
    page_slice = filtered[body.offset : body.offset + body.top_k]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in page_slice}

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))

    # Percentile pool: top-500 from ALL embedded, regardless of active/salary range.
    # Compliant ranges only (EP rule: salary_max <= 2 * salary_min) to avoid skewed benchmarks.
    top_500_uuids = [uuid for uuid, _, _ in ranked_all[:500]]
    salary_pool = store.get_jobs_with_salary_by_uuids(top_500_uuids, compliant_ranges_only=True)
    salary_values = sorted(
        s for j in salary_pool
        if (s := _effective_salary(j)) is not None
    )

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
