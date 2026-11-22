"""Companies route — returns distinct company names for autocomplete and company profiles."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from mcf.api.cache.response import TTL_DASHBOARD, cache_response
from mcf.api.deps import get_store
from mcf.api.limiter import limiter
from mcf.lib.companies.pay import pay_kind
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
    min_years_experience: int | None
    job_url: str | None
    role_family: str
    # "standard" (full-time monthly) | "hourly" | "daily" | "part_time" | "internship" | None (no pay stated)
    pay_kind: str | None = None


class CompanyPayRow(BaseModel):
    """One job type at one company: open ads and what they advertise."""

    role_family: str
    open_count: int
    salary_p25: int | None
    salary_p50: int | None
    salary_p75: int | None
    salary_sample: int


class CompanyProfileResponse(BaseModel):
    """Everything on the profile is computed from the company's open ads in one request,
    so the counts on the page always agree with each other."""

    company_name: str
    active_count: int
    total_count: int
    first_seen: str | None = None
    # advertised full-time monthly pay across the open ads (None when none states one);
    # hourly/daily rates, part-time pay and internships are counted in nonstandard_pay_count
    salary_p25: int | None
    salary_p50: int | None
    salary_p75: int | None
    salary_sample_size: int
    nonstandard_pay_count: int = 0
    pay_by_family: list[CompanyPayRow] = []
    # newest first, capped at OPEN_JOBS_CAP; active_count is the full number
    active_jobs: list[CompanyJob]
    stats: "CompanyStatsRow | None" = None
    top_reposted: list["CompanyReposted"] = []


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
    # SGSAL-032 (False / 0 until the view is on migration 029)
    hires_for_clients: bool = False
    nonstandard_pay_count: int = 0
    described_ads: int = 0
    ea_licence_ads: int = 0
    client_ads: int = 0


class CompanyStatsSummary(BaseModel):
    companies: int
    openings: int
    median_salary: int | None


class CompanyStatsResponse(BaseModel):
    rows: list[CompanyStatsRow]
    total_matching: int
    summary: CompanyStatsSummary


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


OPEN_JOBS_CAP = 200

# Short names people type that appear nowhere in the registered name. Each maps to name
# fragments to search for as well. Kept small and factual; anything else matches on the text.
_SHORT_NAMES: dict[str, tuple[str, ...]] = {
    "nuh": ("national university hospital",),
    "nuhs": ("national university health",),
    "sgh": ("singapore general hospital",),
    "ttsh": ("tan tock seng",),
    "ktph": ("khoo teck puat",),
    "cgh": ("changi general hospital",),
    "skh": ("sengkang general hospital",),
    "kkh": ("kk women",),
    "ntfgh": ("ng teng fong",),
    "imh": ("institute of mental health",),
    "nhg": ("national healthcare group",),
    "singhealth": ("singapore health services",),
    "govtech": ("government technology agency",),
    "moe": ("ministry of education",),
    "moh": ("ministry of health",),
    "mom": ("ministry of manpower",),
    "mha": ("ministry of home affairs",),
    "mindef": ("ministry of defence",),
    "mas": ("monetary authority of singapore",),
    "cpf": ("central provident fund",),
    "hdb": ("housing & development board", "housing and development board"),
    "lta": ("land transport authority",),
    "iras": ("inland revenue authority",),
    "nea": ("national environment agency",),
    "imda": ("infocomm media development",),
    "csa": ("cyber security agency",),
    "edb": ("economic development board",),
    "dsta": ("defence science and technology agency",),
    "astar": ("a*star", "agency for science, technology and research"),
    "a-star": ("a*star", "agency for science, technology and research"),
    "nus": ("national university of singapore",),
    "ntu": ("nanyang technological university",),
    "smu": ("singapore management university",),
    "sutd": ("singapore university of technology and design",),
    "sit": ("singapore institute of technology",),
    "suss": ("singapore university of social sciences",),
    "pwc": ("pricewaterhousecoopers",),
    "ey": ("ernst & young",),
    "sia": ("singapore airlines",),
    "singtel": ("singapore telecommunications",),
    "uob": ("united overseas bank",),
    "ocbc": ("oversea-chinese banking",),
    "sbs": ("sbs transit",),
}


def short_name_expansions(q: str | None) -> tuple[str, ...]:
    """Full-name fragments for a typed short name ("NUH" -> National University Hospital)."""
    return _SHORT_NAMES.get((q or "").strip().lower(), ())


def _parse_json_list(raw) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _effective_salary(job: dict) -> int | None:
    """Same midpoint the company_stats view uses, so list and profile figures agree."""
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo is not None and hi is not None:
        return (lo + hi) // 2
    return lo


def _percentiles(salaries: list[int]) -> tuple[int | None, int | None, int | None]:
    if len(salaries) >= 4:
        return (
            int(np.percentile(salaries, 25)),
            int(np.percentile(salaries, 50)),
            int(np.percentile(salaries, 75)),
        )
    if salaries:
        mid = int(np.percentile(salaries, 50))
        return mid, mid, mid
    return None, None, None


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
            "hires_for_clients": bool(raw.get("hires_for_clients")),
        }
    )


def _job_pay_kind(job: dict) -> str | None:
    return pay_kind(job.get("salary_min"), job.get("salary_max"), _parse_json_list(job.get("employment_types_json")))


def _standard_salary(job: dict) -> int | None:
    """The ad's salary midpoint when it is full-time monthly pay, else None."""
    return _effective_salary(job) if _job_pay_kind(job) == "standard" else None


def _to_company_job(job: dict) -> CompanyJob:
    return CompanyJob(
        job_uuid=job["job_uuid"],
        title=job["title"],
        salary_min=job.get("salary_min"),
        salary_max=job.get("salary_max"),
        first_seen_at=_to_iso(job.get("first_seen_at")),
        last_seen_at=_to_iso(job.get("last_seen_at")),
        employment_types=_parse_json_list(job.get("employment_types_json")),
        min_years_experience=job.get("min_years_experience"),
        job_url=job.get("job_url"),
        role_family=job.get("role_family") or "other",
        pay_kind=_job_pay_kind(job),
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
        q_also=short_name_expansions(q),
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
@cache_response(
    ttl_seconds=TTL_DASHBOARD,
    key_prefix="companies:profile",
    key_builder=lambda **kw: str(kw.get("company_name")),
)
def get_company_profile(
    company_name: str,
    store: Storage = Depends(get_store),
) -> CompanyProfileResponse:
    """Company profile built from the company's open ads.

    Open-role count, pay figures, the per-job-type table and the ad list all come from
    the same rows, so they cannot disagree. ``stats`` (company_stats view) is used only
    for the registered industry and the agency flag.
    """
    try:
        counts = store.get_company_job_counts(company_name)
        if not counts["total"]:
            raise HTTPException(status_code=404, detail="Company not found")
        jobs = store.get_open_jobs_by_company(company_name)
    except HTTPException:
        raise
    except Exception:
        logger.exception("company profile query failed for %r", company_name)
        raise HTTPException(status_code=500, detail="Failed to fetch company jobs")

    # typical pay counts full-time monthly ads only, the same rule as company_stats (migration 029)
    salaries = [s for j in jobs if (s := _standard_salary(j)) is not None]
    p25, p50, p75 = _percentiles(salaries)
    nonstandard = sum(1 for j in jobs if _job_pay_kind(j) not in (None, "standard"))

    by_family: dict[str, list[dict]] = {}
    for j in jobs:
        by_family.setdefault(j.get("role_family") or "other", []).append(j)
    pay_by_family = []
    for family, rows in by_family.items():
        fam_salaries = [s for j in rows if (s := _standard_salary(j)) is not None]
        f25, f50, f75 = _percentiles(fam_salaries)
        pay_by_family.append(
            CompanyPayRow(
                role_family=family,
                open_count=len(rows),
                salary_p25=f25,
                salary_p50=f50,
                salary_p75=f75,
                salary_sample=len(fam_salaries),
            )
        )
    # most open ads first; the classifier's remainder ("other") always last
    pay_by_family.sort(key=lambda r: (r.role_family == "other", -r.open_count, r.role_family))

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
        for r in store.get_company_top_reposted(company_name, limit=10)
    ]

    return CompanyProfileResponse(
        company_name=company_name,
        active_count=len(jobs),
        total_count=counts["total"],
        first_seen=_to_iso(counts.get("first_seen")) or None,
        salary_p25=p25,
        salary_p50=p50,
        salary_p75=p75,
        salary_sample_size=len(salaries),
        nonstandard_pay_count=nonstandard,
        pay_by_family=pay_by_family,
        active_jobs=[_to_company_job(j) for j in jobs[:OPEN_JOBS_CAP]],
        stats=_stats_row(store.get_company_stats_one(company_name)),
        top_reposted=top_reposted,
    )
