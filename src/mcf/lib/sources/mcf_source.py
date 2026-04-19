"""MyCareersFuture job source implementation."""

from __future__ import annotations

import re
from typing import Callable, Sequence

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    if not text:
        return ""
    text = text.replace("\u00a0", " ")
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()

from mcf.lib.external.client import MCFClient
from mcf.lib.crawler.crawler import Crawler, CrawlProgress
from mcf.lib.sources.base import NormalizedJob, clean_description


def _extract_mcf_skills(raw: dict) -> list[str]:
    """Extract skill names from MCF API job detail (key skills first)."""
    key_skills: list[str] = []
    other_skills: list[str] = []
    for s in raw.get("skills", []):
        if isinstance(s, dict):
            name = s.get("skill")
            if name:
                if s.get("isKeySkill"):
                    key_skills.append(str(name))
                else:
                    other_skills.append(str(name))
    return key_skills + other_skills


def _mcf_raw_to_normalized(raw: dict, external_id: str) -> NormalizedJob:
    """Convert MCF API job detail dict to NormalizedJob."""
    title = raw.get("title") or raw.get("jobTitle")
    company_name = None
    company = raw.get("company") or raw.get("postingCompany")
    if isinstance(company, dict):
        company_name = company.get("name") or company.get("companyName")

    location = None
    addr = raw.get("address") or raw.get("workLocation")
    if isinstance(addr, dict):
        location = addr.get("country") or addr.get("postalCode") or addr.get("streetAddress")

    job_url = None
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        job_url = metadata.get("jobDetailsUrl")
    if not job_url:
        job_url = raw.get("jobDetailsUrl")
    if not job_url:
        job_url = f"https://www.mycareersfuture.gov.sg/job/{external_id}"

    description = clean_description(_strip_html(raw.get("description") or raw.get("jobDescription") or "")) or None

    skills = _extract_mcf_skills(raw)

    categories = [
        c["category"]
        for c in raw.get("categories", [])
        if isinstance(c, dict) and c.get("category")
    ]
    employment_types = [
        e["employmentType"]
        for e in raw.get("employmentTypes", [])
        if isinstance(e, dict) and e.get("employmentType")
    ]
    position_levels = [
        p["position"]
        for p in raw.get("positionLevels", [])
        if isinstance(p, dict) and p.get("position")
    ]

    salary = raw.get("salary") or {}
    salary_min = salary.get("minimum") if isinstance(salary, dict) else None
    salary_max = salary.get("maximum") if isinstance(salary, dict) else None
    if salary_min is not None:
        salary_min = int(salary_min)
    if salary_max is not None:
        salary_max = int(salary_max)

    metadata_dict = raw.get("metadata") or {}
    posted_date = None
    if metadata_dict.get("newPostingDate"):
        posted_date = str(metadata_dict.get("newPostingDate", ""))[:10]
    expiry_date = None
    if metadata_dict.get("expiryDate"):
        expiry_date = str(metadata_dict.get("expiryDate", ""))[:10]

    return NormalizedJob(
        source_id="mcf",
        external_id=external_id,
        title=title,
        company_name=company_name,
        location=location,
        job_url=job_url,
        skills=skills,
        description=description,
        categories=categories,
        employment_types=employment_types,
        position_levels=position_levels,
        salary_min=salary_min,
        salary_max=salary_max,
        posted_date=posted_date or None,
        expiry_date=expiry_date or None,
    )


class MCFJobSource:
    """Job source for MyCareersFuture Singapore API."""

    def __init__(self, rate_limit: float = 4.0) -> None:
        self.rate_limit = rate_limit

    @property
    def source_id(self) -> str:
        return "mcf"

    def list_job_ids(
        self,
        *,
        categories: Sequence[str] | None = None,
        limit: int | None = None,
        on_progress: Callable[[CrawlProgress], None] | None = None,
    ) -> list[str]:
        """List job UUIDs from MCF."""
        crawler = Crawler(rate_limit=self.rate_limit)
        cats = list(categories) if categories else None
        return crawler.list_job_uuids_all_categories(
            categories=cats,
            limit=limit,
            on_progress=on_progress,
        )

    def get_job_detail(self, external_id: str) -> NormalizedJob:
        """Fetch job detail from MCF API and return as NormalizedJob."""
        with MCFClient(rate_limit=self.rate_limit) as client:
            detail = client.get_job_detail(external_id)
            raw = detail.model_dump(by_alias=True, mode="json")
            return _mcf_raw_to_normalized(raw, external_id)
