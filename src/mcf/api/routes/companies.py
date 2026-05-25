"""Companies route — returns distinct company names for autocomplete and company profiles."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mcf.api.deps import get_store
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


class TopCompany(BaseModel):
    name: str
    active_count: int


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


def _to_iso(val) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


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
def list_companies(store: Storage = Depends(get_store)) -> list[str]:
    """Return sorted list of distinct company names from active jobs."""
    return store.get_distinct_companies()


@router.get("/api/companies/popular")
def get_popular_companies(
    limit: int = 20,
    store: Storage = Depends(get_store),
) -> list[TopCompany]:
    """Return top companies by active job count."""
    return [TopCompany(**row) for row in store.get_top_companies(limit)]


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

    # salary percentiles
    salaries = [j["salary_min"] for j in jobs if j.get("salary_min") is not None]
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

    active_jobs_raw = sorted(
        [j for j in jobs if j.get("is_active")],
        key=lambda j: _to_iso(j.get("last_seen_at")),
        reverse=True,
    )
    closed_jobs_raw = sorted(
        [j for j in jobs if not j.get("is_active")],
        key=lambda j: _to_iso(j.get("last_seen_at")),
        reverse=True,
    )[:10]

    return CompanyProfileResponse(
        company_name=company_name,
        active_count=len(active_jobs_raw),
        total_count=len(jobs),
        salary_p25=p25,
        salary_p50=p50,
        salary_p75=p75,
        salary_sample_size=len(salaries),
        avg_min_experience=avg_min_experience,
        position_levels=dict(pl_counter),
        employment_types=dict(et_counter),
        top_skills=top_skills,
        active_jobs=[_to_company_job(j) for j in active_jobs_raw],
        recent_closed=[_to_company_job(j) for j in closed_jobs_raw],
    )
