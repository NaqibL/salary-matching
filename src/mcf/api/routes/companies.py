"""Companies route — returns distinct company names for autocomplete and company profiles."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from mcf.api.cache.response import TTL_DASHBOARD, cache_response
from mcf.api.deps import get_store
from mcf.api.limiter import limiter
from mcf.lib.storage.base import Storage

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CompanyJob(BaseModel):
    job_uuid: str
    title: str | None
    salary_min: int | None
    salary_max: int | None
    first_seen_at: str | None
    last_seen_at: str | None
    employment_types: list[str]
    position_levels: list[str]
    min_years_experience: int | None
    inferred_seniority: str | None
    job_url: str | None


class CompanyProfileResponse(BaseModel):
    company_name: str
    active_count: int
    total_count: int
    salary_p25: int | None
    salary_p50: int | None
    salary_p75: int | None
    salary_sample_size: int
    avg_min_experience: float | None
    position_levels: dict[str, int]
    employment_types: dict[str, int]
    top_skills: list[list[Any]]
    active_jobs: list[CompanyJob]
    recent_closed: list[CompanyJob]
    stats: "CompanyStatsRow | None" = None
    top_reposted: list["CompanyReposted"] = []
    benchmarks: "CompanyBenchmarks | None" = None


class TopCompany(BaseModel):
    name: str
    active_count: int


class CompanyStatsRow(BaseModel):
    company_key: str
    company: str
    active_count: int
    distinct_postings: int
    reposted_count: int
    multi_company_count: int
    max_repost_count: int
    median_salary: int | None
    salary_sample: int
    role_family_counts: dict[str, int]
    family_count: int
    top_family: str | None
    category_counts: dict[str, int]
    total_seen: int
    first_seen: str | None
    last_seen: str | None
    # SGSAL-028: registered industry (SSIC) and the only source of the agency label
    ssic_code_2020: str | None = None
    ssic_description: str | None = None
    is_agency: bool = False
    top_family_share: float | None = None
    family_active_count: int | None = None
    family_median_salary: int | None = None
    family_salary_sample: int | None = None


class CompanyStatsSummary(BaseModel):
    companies: int
    openings: int
    median_salary: int | None


class CompanyStatsResponse(BaseModel):
    rows: list[CompanyStatsRow]
    total_matching: int
    summary: CompanyStatsSummary


class CompanyBenchmarks(BaseModel):
    median_repost_rate: float | None = None


class CompanyReposted(BaseModel):
    canonical_job_uuid: str
    title: str | None
    repost_count: int
    reposts_365d: int
    distinct_companies: int
    first_posted: str | None
    last_posted: str | None
    latest_salary_min: int | None
    latest_salary_max: int | None


CompanyProfileResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_json_list(raw) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _effective_salary(job: dict) -> int | None:
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo is not None and hi is not None:
        return (lo + hi) // 2
    return lo


def _to_iso(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _stats_row(raw: dict | None) -> CompanyStatsRow | None:
    if not raw:
        return None
    return CompanyStatsRow(
        **{
            **raw,
            "first_seen": _to_iso(raw.get("first_seen")) or None,
            "last_seen": _to_iso(raw.get("last_seen")) or None,
            "role_family_counts": raw.get("role_family_counts") or {},
            "category_counts": raw.get("category_counts") or {},
            "top_family_share": float(raw["top_family_share"]) if raw.get("top_family_share") is not None else None,
            "is_agency": bool(raw.get("is_agency")),
        }
    )


def _to_company_job(job: dict) -> CompanyJob:
    llm_raw = job.get("llm_fields_json")
    try:
        llm = json.loads(llm_raw) if isinstance(llm_raw, str) else (llm_raw or {})
    except (json.JSONDecodeError, TypeError):
        llm = {}
    return CompanyJob(
        job_uuid=job["job_uuid"],
        title=job["title"],
        salary_min=job.get("salary_min"),
        salary_max=job.get("salary_max"),
        first_seen_at=_to_iso(job.get("first_seen_at")),
        last_seen_at=_to_iso(job.get("last_seen_at")),
        employment_types=_parse_json_list(job.get("employment_types_json")),
        position_levels=_parse_json_list(job.get("position_levels_json")),
        min_years_experience=job.get("min_years_experience"),
        inferred_seniority=llm.get("inferred_seniority"),
        job_url=job.get("job_url"),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/companies")
@limiter.limit("60/minute")
@cache_response(ttl_seconds=TTL_DASHBOARD, key_prefix="companies:list", key_builder=lambda **_: "all")
def list_companies(request: Request, store: Storage = Depends(get_store)) -> list[str]:
    """Return sorted list of distinct company names from active jobs."""
    return store.get_distinct_companies()


@router.get("/api/companies/aliases")
@cache_response(ttl_seconds=TTL_DASHBOARD, key_prefix="companies:aliases", key_builder=lambda **_: "all")
def list_company_aliases(store: Storage = Depends(get_store)) -> dict[str, str]:
    """Return raw_name → canonical_name alias map for autocomplete matching."""
    return store.get_company_alias_map()


@router.get("/api/companies/popular")
def get_popular_companies(
    limit: int = Query(default=20, ge=1, le=100),
    store: Storage = Depends(get_store),
) -> list[TopCompany]:
    """Return top companies by active job count."""
    return [TopCompany(**row) for row in store.get_top_companies(limit)]


@router.get("/api/companies/stats")
@limiter.limit("60/minute")
@cache_response(
    ttl_seconds=TTL_DASHBOARD,
    key_prefix="companies:stats",
    key_builder=lambda **kw: "|".join(
        str(kw.get(k)) for k in ("family", "category", "q", "agency", "min_active", "sort", "limit")
    ),
)
def get_company_stats(
    request: Request,
    family: str | None = Query(default=None, max_length=64),
    category: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=80),
    agency: Literal["all", "direct", "agency"] = Query(default="all"),
    min_active: int = Query(default=10, ge=1, le=1000),
    sort: Literal["openings", "distinct", "repost_rate", "median_salary"] = Query(default="openings"),
    limit: int = Query(default=50, ge=1, le=200),
    store: Storage = Depends(get_store),
) -> CompanyStatsResponse:
    """Ranked companies from the company_stats view (SGSAL-026)."""
    out = store.get_company_stats(
        family=family or None,
        category=category or None,
        q=(q or "").strip() or None,
        agency=agency,
        min_active=min_active,
        sort=sort,
        limit=limit,
    )
    return CompanyStatsResponse(
        rows=[_stats_row(r) for r in out["rows"]],
        total_matching=out["total_matching"],
        summary=CompanyStatsSummary(**out["summary"]),
    )


@router.get("/api/companies/{company_name}/profile")
def get_company_profile(
    company_name: str,
    store: Storage = Depends(get_store),
) -> CompanyProfileResponse:
    """Return aggregated profile for a company (active + historical jobs)."""
    try:
        jobs = store.get_all_jobs_by_company(company_name)
    except Exception:
        logger.exception("get_all_jobs_by_company failed for %r", company_name)
        raise HTTPException(status_code=500, detail="Failed to fetch company jobs")
    if not jobs:
        raise HTTPException(status_code=404, detail="Company not found")

    # salary percentiles — use midpoint to match lowball checker behaviour
    salaries = [s for j in jobs if (s := _effective_salary(j)) is not None]
    if len(salaries) >= 4:
        p25 = int(np.percentile(salaries, 25))
        p50 = int(np.percentile(salaries, 50))
        p75 = int(np.percentile(salaries, 75))
    elif salaries:
        mid = int(np.percentile(salaries, 50))
        p25 = p50 = p75 = mid
    else:
        p25 = p50 = p75 = None

    # avg min experience
    exp_values = [j["min_years_experience"] for j in jobs if j.get("min_years_experience") is not None]
    avg_min_experience = round(sum(exp_values) / len(exp_values), 1) if exp_values else None

    # frequency counters
    pl_counter: Counter = Counter()
    et_counter: Counter = Counter()
    skill_counter: Counter = Counter()
    for j in jobs:
        for level in _parse_json_list(j.get("position_levels_json")):
            pl_counter[level] += 1
        for et in _parse_json_list(j.get("employment_types_json")):
            et_counter[et] += 1
        llm_raw = j.get("llm_fields_json")
        try:
            llm = json.loads(llm_raw) if isinstance(llm_raw, str) else (llm_raw or {})
        except (json.JSONDecodeError, TypeError):
            llm = {}
        for skill in llm.get("canonical_skills") or []:
            skill_counter[skill] += 1

    top_skills = [[skill, count] for skill, count in skill_counter.most_common(20)]

    active_jobs_all = sorted(
        [j for j in jobs if j.get("is_active")],
        key=lambda j: _to_iso(j.get("first_seen_at")),
        reverse=True,
    )
    closed_jobs_raw = sorted(
        [j for j in jobs if not j.get("is_active")],
        key=lambda j: _to_iso(j.get("last_seen_at")),
        reverse=True,
    )[:10]

    stats = _stats_row(store.get_company_stats_one(company_name))
    top_reposted = [
        CompanyReposted(
            canonical_job_uuid=r["canonical_job_uuid"],
            title=r.get("title"),
            repost_count=r["repost_count"],
            reposts_365d=r["reposts_365d"],
            distinct_companies=r["distinct_companies"],
            first_posted=_to_iso(r.get("first_posted")) or None,
            last_posted=_to_iso(r.get("last_posted")) or None,
            latest_salary_min=r.get("latest_salary_min"),
            latest_salary_max=r.get("latest_salary_max"),
        )
        for r in store.get_company_top_reposted(company_name, limit=5)
    ]

    return CompanyProfileResponse(
        company_name=company_name,
        stats=stats,
        top_reposted=top_reposted,
        benchmarks=CompanyBenchmarks(**store.get_company_benchmarks()),
        active_count=len(active_jobs_all),
        total_count=len(jobs),
        salary_p25=p25,
        salary_p50=p50,
        salary_p75=p75,
        salary_sample_size=len(salaries),
        avg_min_experience=avg_min_experience,
        position_levels=dict(pl_counter),
        employment_types=dict(et_counter),
        top_skills=top_skills,
        active_jobs=[_to_company_job(j) for j in active_jobs_all[:10]],
        recent_closed=[_to_company_job(j) for j in closed_jobs_raw],
    )
