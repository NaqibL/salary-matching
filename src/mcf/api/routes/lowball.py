"""Lowball checker and salary search routes."""

from __future__ import annotations

from statistics import quantiles as _quantiles

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mcf.api.auth import get_optional_user
from mcf.api.config import settings
from mcf.api.deps import get_store
from mcf.lib.embeddings.base import EmbedderProtocol
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache
from mcf.lib.embeddings.job_text import structure_salary_query

router = APIRouter()


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
    structured_query: bool = True


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
# Lowball checker
# ---------------------------------------------------------------------------


@router.post("/api/lowball/check")
def check_lowball(body: LowballCheckRequest, _: str | None = Depends(get_optional_user)):
    """Check if an offered salary is competitive for a described role."""
    store = get_store()
    embeddings_cache_inst = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    embedder: EmbedderProtocol = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache_inst)
    vector = embedder.embed_text(body.job_description)

    ranked = store.get_all_embedded_job_ids_ranked(vector, limit=500)

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


@router.post("/api/salary/search")
def salary_search(body: SalarySearchRequest, _: str | None = Depends(get_optional_user)):
    """Semantic job search filtered by salary range."""
    store = get_store()
    embeddings_cache_inst = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    embedder: EmbedderProtocol = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache_inst)
    query_text = structure_salary_query(body.job_description) if body.structured_query else body.job_description
    vector = embedder.embed_text(query_text)

    # All embedded jobs (active + inactive) — for richer percentile calculation
    ranked_all = store.get_all_embedded_job_ids_ranked(vector)

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

    # Percentile pool: top-500 from ALL embedded, regardless of active/salary range
    top_500_uuids = [uuid for uuid, _, _ in ranked_all[:500]]
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
