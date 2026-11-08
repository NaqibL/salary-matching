"""Lowball checker and salary search routes."""

from __future__ import annotations

import logging

import json as _json
from statistics import quantiles as _quantiles

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from mcf.api.auth import get_optional_user
from mcf.api.cache.job_pool import compute_ranked_from_pool, get_pool_or_fetch
from mcf.api.cache.response import TTL_LOWBALL, cache_get, cache_set, make_body_cache_key
from mcf.api.config import settings
from mcf.api.deps import get_embedder, get_store
from mcf.api.limiter import limiter
from mcf.lib.embeddings.base import EmbedderProtocol
from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description
from mcf.lib.storage.base import Storage

logger = logging.getLogger(__name__)

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
    seniority: str | None = Field(default=None, max_length=50)


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
    total_listings: int | None = None
    # SGSAL-027: open postings among the 500 nearest; cards show open roles first
    open_matched: int | None = None


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


def _int_or(value, default: int) -> int:
    """int(value), or ``default`` only when value is None — a legitimate 0 passes through."""
    return int(value) if value is not None else default


def _dedup_by_job_uuid(rows: list[dict]) -> list[dict]:
    """Drop rows whose job_uuid was already seen (keep first occurrence).

    Several vector hits from one posting group resolve to the same representative
    row (before the backfill --apply, or with a hash's second self-canonical), so
    the benchmark pool must count each posting's salary once.
    """
    seen: set[str] = set()
    out = []
    for r in rows:
        if r["job_uuid"] in seen:
            continue
        seen.add(r["job_uuid"])
        out.append(r)
    return out


def _by_score(rows: list[dict], uuid_to_score: dict[str, float]) -> list[dict]:
    """Sort representative rows by their vector hit's score, best first."""
    return sorted(
        rows,
        key=lambda j: uuid_to_score.get(j.get("canonical_job_uuid") or j["job_uuid"], 0.0),
        reverse=True,
    )


_AGENCY_CACHE: dict[str, object] = {"keys": set(), "at": 0.0}
_AGENCY_TTL_SECONDS = 3600


def _agency_keys(store: Storage) -> set[str]:
    """lower(company_name) of registered employment agencies (SSIC 78), refreshed hourly."""
    import time as _time

    now = _time.time()
    if now - float(_AGENCY_CACHE["at"]) > _AGENCY_TTL_SECONDS:
        try:
            _AGENCY_CACHE["keys"] = store.get_agency_company_keys()
        except Exception:  # noqa: BLE001 — never fail a check over the label
            logger.exception("agency key refresh failed")
        _AGENCY_CACHE["at"] = now
    return _AGENCY_CACHE["keys"]  # type: ignore[return-value]


def _direct_employers(store: Storage, rows: list[dict], agency_keys: set[str]) -> dict[str, str]:
    """canonical_job_uuid -> a non-agency company that also posted the same ad text (SGSAL-028).

    Looks the posting group up by ``content_hash`` (exact, even when a hash has two
    self-canonicals). Occurrence names are canonical names, so ``agency_keys`` must contain
    both raw and canonical spellings (see ``get_agency_company_keys``) and the card's own
    company is excluded by raw *and* canonical name.
    """
    by_hash = {j["content_hash"]: j for j in rows if j.get("content_hash") and _int_or(j.get("distinct_companies"), 1) >= 2}
    if not by_hash:
        return {}
    try:
        groups = store.get_posting_group_companies(list(by_hash))
    except Exception:  # noqa: BLE001
        logger.exception("posting group company lookup failed")
        return {}
    out: dict[str, str] = {}
    for content_hash, names in groups.items():
        row = by_hash.get(content_hash)
        if row is None:
            continue
        own = {
            (row.get("company_name") or "").strip().lower(),
            (row.get("company_canonical") or "").strip().lower(),
        } - {""}
        for name in names:
            key = name.strip().lower()
            if key and key not in own and key not in agency_keys:
                out[row.get("canonical_job_uuid") or row["job_uuid"]] = name
                break
    return out


def _build_similar_jobs(
    jobs: list[dict],
    uuid_to_score: dict[str, float],
    top_k: int,
    *,
    agency_keys: set[str] | None = None,
    direct_by_canonical: dict[str, str] | None = None,
) -> list[dict]:
    agency_keys = agency_keys or set()
    direct_by_canonical = direct_by_canonical or {}
    result = []
    for j in jobs:
        raw_desc = j.get("description") or ""
        llm_raw = j.get("llm_fields_json")
        llm = _json.loads(llm_raw) if isinstance(llm_raw, str) else (llm_raw or {})
        score_key = j.get("canonical_job_uuid") or j["job_uuid"]
        result.append({
            "job_uuid": j["job_uuid"],
            "canonical_job_uuid": score_key,
            "title": j["title"],
            "company_name": j.get("company_name"),
            "location": j.get("location"),
            "job_url": j.get("job_url"),
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "is_active": j.get("is_active", True),
            # SGSAL-028: label facts (SSIC 78 registry; posting-group companies)
            "is_agency": bool(
                {(j.get("company_name") or "").strip().lower(), (j.get("company_canonical") or "").strip().lower()}
                & agency_keys
            ),
            "direct_employer": direct_by_canonical.get(score_key),
            "description": raw_desc or None,
            "similarity_score": round(uuid_to_score.get(score_key, 0.0), 4),
            "min_years_experience": j.get("min_years_experience"),
            "inferred_seniority": llm.get("inferred_seniority"),
            "canonical_skills": llm.get("canonical_skills"),
            "repost_count": _int_or(j.get("repost_count"), 1),
            "active_count": _int_or(j.get("active_count"), 1 if j.get("is_active", True) else 0),
            "first_posted": _iso(j.get("first_posted")),
            "last_posted": _iso(j.get("last_posted")),
            "reposts_365d": _int_or(j.get("reposts_365d"), 1),
            "distinct_companies": _int_or(j.get("distinct_companies"), 1),
            "min_salary_seen": j.get("min_salary_seen"),
            "max_salary_seen": j.get("max_salary_seen"),
        })
    # SGSAL-027: open roles first, then by score — callers pass open rows ahead of closed ones.
    result.sort(key=lambda x: (not (x["is_active"] or x["active_count"] > 0), -x["similarity_score"]))
    # Until duplicate vectors are deleted, two members of one posting group can
    # resolve to the same latest occurrence: keep the best-scoring entry only.
    seen: set[str] = set()
    deduped = []
    for r in result:
        if r["job_uuid"] in seen:
            continue
        seen.add(r["job_uuid"])
        deduped.append(r)
    return deduped[:top_k]


def _iso(d) -> str | None:
    return d.isoformat() if d is not None and hasattr(d, "isoformat") else d


def _effective_salary(job: dict) -> int | None:
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo is not None and hi is not None:
        return (lo + hi) // 2
    return lo


def _has_valid_salary(job: dict) -> bool:
    """Return False for jobs with placeholder or thousands-notation salary errors (salary_max < 100)."""
    hi = job.get("salary_max")
    return hi is None or hi >= 100


def _salary_percentiles(salaries: list[int]) -> tuple[int, int, int]:
    qs = _quantiles(salaries, n=4)  # [p25, p50, p75]
    return int(qs[0]), int(qs[1]), int(qs[2])


def lowball_cache_key(body: LowballCheckRequest) -> str:
    """Response-cache key for POST /api/lowball/check.

    Every body field that changes the result is included. title/description are
    whitespace+case normalized (they only feed the embedder); salary, top_k,
    company_name and seniority are exact because the handler uses them verbatim
    (company_name is an exact DB match, seniority is compared literally).
    """
    return make_body_cache_key(
        "lowball",
        title=body.title,
        description=body.description,
        salary=body.salary,
        top_k=body.top_k,
        company_name=body.company_name,
        seniority=body.seniority,
    )


def salary_search_cache_key(body: SalarySearchRequest) -> str:
    """Response-cache key for POST /api/salary/search (same rules as lowball_cache_key)."""
    return make_body_cache_key(
        "salary_search",
        title=body.title,
        description=body.description,
        salary_min=body.salary_min,
        salary_max=body.salary_max,
        top_k=body.top_k,
        offset=body.offset,
    )


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
    # Short-TTL response cache keyed on the request body (not per user). Repeated
    # checks of the same role skip the embed + pgvector scan entirely.
    if not settings.enable_response_cache:
        return _compute_lowball(body, store, embedder)
    key = lowball_cache_key(body)
    cached = cache_get(key)
    if cached is not None:
        return cached
    result = _compute_lowball(body, store, embedder)
    cache_set(key, TTL_LOWBALL, result)
    return result


def _compute_lowball(body: LowballCheckRequest, store: Storage, embedder: EmbedderProtocol) -> LowballResult:
    description_text, _ = extract_high_signal_description(body.description, body.title)
    job_text = f"Job Title: {body.title}\nDescription: {description_text}"
    if body.seniority == "Intern":
        job_text += "\nRole Type: Internship\nSeniority: Intern"
    elif body.seniority:
        job_text += f"\nSeniority: {body.seniority}"
    vector = embedder.embed_text(job_text)

    # Always query all jobs (active + historical) for accurate salary benchmarking.
    # Pool cache is active-only, so bypass it here.
    ranked = store.get_all_embedded_job_ids_ranked(vector, limit=500)

    agency_keys = _agency_keys(store)

    # Company-specific results: direct similarity search scoped to the company,
    # independent of the global top-500 so no Shopee-style jobs get missed.
    company_similar_jobs = None
    if body.company_name:
        company_ranked = store.get_company_jobs_ranked(vector, body.company_name, limit=body.top_k)
        if company_ranked:
            c_uuids = [uuid for uuid, _, _ in company_ranked]
            c_scores = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in company_ranked}
            c_jobs = store.get_jobs_with_salary_by_uuids(c_uuids, representative=True, company_name=body.company_name)
            c_jobs = _dedup_by_job_uuid(_by_score(c_jobs, c_scores))
            company_similar_jobs = _build_similar_jobs(
                c_jobs, c_scores, body.top_k,
                agency_keys=agency_keys, direct_by_canonical=_direct_employers(store, c_jobs, agency_keys),
            )

    top_slice = ranked[: body.top_k * 5]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in top_slice}
    # SGSAL-027: the cards draw from the full 500 nearest so open roles can come first;
    # the percentile pool below stays the closest top_k*5 (historical by design).
    uuid_to_score_all = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in ranked}

    jobs_all = store.get_jobs_with_salary_by_uuids(list(uuid_to_score_all.keys()), representative=True)
    # One row per posting (I3): best-scoring hit wins, before coverage/percentiles.
    jobs_all = _dedup_by_job_uuid(_by_score([j for j in jobs_all if _has_valid_salary(j)], uuid_to_score_all))
    jobs = [j for j in jobs_all if (j.get("canonical_job_uuid") or j["job_uuid"]) in uuid_to_score]
    # Salary benchmark pool uses compliant ranges only (EP rule: salary_max <= 2 * salary_min).
    salary_jobs = store.get_jobs_with_salary_by_uuids(
        list(uuid_to_score.keys()), compliant_ranges_only=True, representative=True
    )
    salary_jobs = _dedup_by_job_uuid(
        [j for j in salary_jobs if j.get("salary_min") is not None and _has_valid_salary(j)]
    )
    open_jobs = [j for j in jobs_all if j.get("is_active") or _int_or(j.get("active_count"), 0) > 0]
    closed_jobs = [j for j in jobs_all if not (j.get("is_active") or _int_or(j.get("active_count"), 0) > 0)]
    open_matched = len(open_jobs)
    card_rows = open_jobs[: body.top_k] + closed_jobs[: max(0, body.top_k - len(open_jobs[: body.top_k]))]
    similar = _build_similar_jobs(
        card_rows, uuid_to_score_all, body.top_k,
        agency_keys=agency_keys, direct_by_canonical=_direct_employers(store, card_rows, agency_keys),
    )
    total_listings = sum(_int_or(j.get("repost_count"), 1) for j in similar)

    # Compute market percentiles regardless of whether salary was provided
    if len(salary_jobs) < 5:
        return LowballResult(
            verdict="insufficient_data", offered_salary=body.salary,
            percentile=None, market_p25=None, market_p50=None, market_p75=None,
            salary_coverage=len(salary_jobs), total_matched=len(jobs),
            similar_jobs=similar, company_similar_jobs=company_similar_jobs,
            total_listings=total_listings,
            open_matched=open_matched,
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
            total_listings=total_listings,
            open_matched=open_matched,
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
        total_listings=total_listings,
        open_matched=open_matched,
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
    if not settings.enable_response_cache:
        return _compute_salary_search(body, store, embedder)
    key = salary_search_cache_key(body)
    cached = cache_get(key)
    if cached is not None:
        return cached
    result = _compute_salary_search(body, store, embedder)
    cache_set(key, TTL_LOWBALL, result)
    return result


def _compute_salary_search(
    body: SalarySearchRequest, store: Storage, embedder: EmbedderProtocol
) -> SalarySearchResult:
    description_text, _ = extract_high_signal_description(body.description, body.title)
    job_text = f"Job Title: {body.title}\nDescription: {description_text}"
    vector = embedder.embed_text(job_text)

    if settings.enable_active_jobs_pool_cache:
        pool, matrix = get_pool_or_fetch(store)
        ranked_all = compute_ranked_from_pool(pool, vector, limit=500, matrix=matrix)
    else:
        ranked_all = store.get_all_embedded_job_ids_ranked(vector, limit=500)

    # Active-only gate for displayed results (users are browsing to apply)
    active_uuids = store.active_canonical_uuids()

    # Salary range filter (active-only) — only applied when the user specified a range
    salary_allowed = store.get_job_uuids_with_salary_filter(body.salary_min, body.salary_max)

    # Displayed jobs: active AND in salary range (if specified)
    display_gate = salary_allowed if salary_allowed is not None else active_uuids
    filtered = [(uuid, dist, last_seen) for uuid, dist, last_seen in ranked_all if uuid in display_gate]

    total = len(filtered)
    page_slice = filtered[body.offset : body.offset + body.top_k]
    uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in page_slice}

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()), representative=True)
    jobs = _dedup_by_job_uuid(_by_score(jobs, uuid_to_score))

    # Percentile pool: top-500 from ALL embedded, regardless of active/salary range.
    # Compliant ranges only (EP rule: salary_max <= 2 * salary_min) to avoid skewed benchmarks.
    top_500_uuids = [uuid for uuid, _, _ in ranked_all[:500]]
    salary_pool = _dedup_by_job_uuid(
        store.get_jobs_with_salary_by_uuids(top_500_uuids, compliant_ranges_only=True, representative=True)
    )
    salary_values = sorted(
        s for j in salary_pool
        if _has_valid_salary(j) and (s := _effective_salary(j)) is not None
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
            similarity_score=uuid_to_score.get(j.get("canonical_job_uuid") or j["job_uuid"], 0.0),
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
