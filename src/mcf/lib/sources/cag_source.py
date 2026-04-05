"""Careers@Gov (Singapore) job source implementation.

Uses the Algolia search index to list job IDs and fetch full job details.
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from typing import Sequence

import httpx

from mcf.lib.sources.base import NormalizedJob

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------

_ALGOLIA_APP_ID = os.environ.get("CAG_ALGOLIA_APP_ID", "3OW7D8B4IZ")
_ALGOLIA_INDEX = "job_index"
_ALGOLIA_SEARCH_URL = (
    f"https://{_ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/{_ALGOLIA_INDEX}/query"
)
_ALGOLIA_OBJECT_URL = (
    f"https://{_ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/{_ALGOLIA_INDEX}/"
)
_ALGOLIA_HEADERS = {
    "x-algolia-application-id": _ALGOLIA_APP_ID,
    "x-algolia-api-key": os.environ.get("CAG_ALGOLIA_API_KEY", "32fa71d8b0bc06be1e6395bf8c430107"),
    "Referer": "https://jobs.careers.gov.sg/",
    "Content-Type": "application/json",
}

_SOURCE_ID = "cag"
_PREFIX = f"{_SOURCE_ID}:"

# Keywords for partitioning: Algolia search returns max 1000 per query.
# Multiple keyword searches + dedupe yields ~99%+ of jobs (index has no facets).
_LIST_KEYWORDS = [
    "",
    "engineer",
    "manager",
    "officer",
    "director",
    "analyst",
    "executive",
    "assistant",
    "specialist",
    "administrator",
    "consultant",
    "coordinator",
    "developer",
    "designer",
    "technician",
    "inspector",
    "supervisor",
    "lead",
    "head",
    "principal",
    "senior",
    "junior",
    "research",
    "policy",
    "legal",
    "finance",
    "human",
    "communications",
    "operations",
    "project",
    "programme",
    "data",
    "digital",
    "cyber",
    "security",
    "health",
    "education",
    "social",
    "environment",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    if not html:
        return ""
    text = html.replace("\u00a0", " ")
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _parse_object_id(object_id: str) -> tuple[str, str | None]:
    """Split an Algolia objectID into (raw_job_id, posting_uuid_or_None).

    Handles all formats returned by the Algolia index:
    - ``"{JobId}_{PostingUuid}"``     e.g. ``"15219929_005056a3-d347-..."``
    - ``"{JobId}/{PostingUuid}"``     e.g. ``"HRP:12243518/005056a3-d347-..."``
    - ``"{SYSTEM}:{id}"``             e.g. ``"GREENHOUSE:4764906101"``
      (no posting UUID — ATS systems like Greenhouse, Workday, etc.)
    """
    if "_" in object_id:
        sep = object_id.index("_")
        return object_id[:sep], object_id[sep + 1:]
    elif "/" in object_id:
        sep = object_id.index("/")
        return object_id[:sep], object_id[sep + 1:]
    else:
        # ATS systems like GREENHOUSE, WORKDAY, etc. — only have a bare job ID
        return object_id, None


def _numeric_job_id(raw_job_id: str) -> str:
    """Extract the numeric portion from a raw job ID.

    ``"HRP:12243518"`` → ``"12243518"``
    ``"15219929"``     → ``"15219929"``
    """
    return raw_job_id.split(":")[-1]


def _build_description(raw: dict) -> str | None:
    """Build a text description from available Algolia fields."""
    candidates = (
        "description",
        "job_description",
        "Jobdesc",
        "responsibilities",
        "requirements",
        "Jobreq",
        "Jobres",
    )
    parts = []
    for key in candidates:
        val = raw.get(key) or ""
        stripped = _strip_html(str(val)) if val else ""
        if stripped:
            parts.append(stripped)
    combined = " ".join(parts)
    words = combined.split()
    return " ".join(words[:150]) if words else None


# ---------------------------------------------------------------------------
# CareersGovJobSource
# ---------------------------------------------------------------------------


class CareersGovJobSource:
    """Job source for the Careers@Gov (Singapore) portal.

    Both listing and detail fetching use the public Algolia search index so
    no separate OData endpoint is required.

    The ``job_uuid`` for every CAG job is prefixed with ``"cag:"``
    (e.g. ``"cag:15219929_005056a3-d347-1fe1-80df-725f7689c286"`` or
    ``"cag:HRP:12243518/005056a3-d347-1fe1-85dc-4a2e60cc828a"``) so that
    it does not collide with MCF UUIDs in the database.
    """

    def __init__(self, rate_limit: float = 5.0) -> None:
        """Create a new CareersGovJobSource.

        Args:
            rate_limit: Maximum Algolia requests per second for detail fetching.
        """
        self.rate_limit = rate_limit
        self._min_interval = 1.0 / rate_limit if rate_limit > 0 else 0.0
        self._last_request_time: float = 0.0

    @property
    def source_id(self) -> str:
        return _SOURCE_ID

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _wait(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # list_job_ids
    # ------------------------------------------------------------------

    def list_job_ids(
        self,
        *,
        categories: Sequence[str] | None = None,  # ignored for CAG
        limit: int | None = None,
        on_progress=None,
    ) -> list[str]:
        """List Careers@Gov job IDs via Algolia keyword partitioning.

        Algolia search returns max 1000 hits per query. We run multiple
        searches with different job-title keywords and deduplicate to
        retrieve ~99%+ of the index.

        Returns IDs in prefixed ``job_uuid`` form: ``"cag:{objectID}"``.

        The ``categories`` parameter is accepted for protocol compatibility but
        ignored — Careers@Gov does not use the same category taxonomy as MCF.
        """
        seen: set[str] = set()
        job_uuids: list[str] = []

        with httpx.Client(headers=_ALGOLIA_HEADERS, timeout=30.0) as client:
            for i, keyword in enumerate(_LIST_KEYWORDS):
                payload = {
                    "query": keyword,
                    "hitsPerPage": 1000,
                    "page": 0,
                    "attributesToRetrieve": ["objectID"],
                }
                response = client.post(_ALGOLIA_SEARCH_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                for hit in data.get("hits", []):
                    object_id = hit.get("objectID")
                    if not object_id or object_id in seen:
                        continue
                    seen.add(object_id)
                    job_uuids.append(f"{_PREFIX}{object_id}")

                    if limit and len(job_uuids) >= limit:
                        break

                if on_progress:
                    try:
                        on_progress(len(job_uuids))
                    except Exception:
                        pass

                if limit and len(job_uuids) >= limit:
                    break

        return job_uuids

    # ------------------------------------------------------------------
    # get_job_detail
    # ------------------------------------------------------------------

    def get_job_detail(self, job_uuid: str) -> NormalizedJob:
        """Fetch full job detail from Algolia by objectID.

        Args:
            job_uuid: Prefixed ID in the form ``"cag:{objectID}"``
                (as returned by :meth:`list_job_ids`).

        Returns:
            A :class:`NormalizedJob` populated from the Algolia response.
        """
        object_id = job_uuid.removeprefix(_PREFIX)

        raw_job_id, posting_uuid = _parse_object_id(object_id)
        numeric_id = _numeric_job_id(raw_job_id)

        # HRP jobs have a posting UUID; other ATS systems (Greenhouse, etc.) do not.
        # URL for HRP is known; for others we'll try to get it from Algolia data.
        job_url: str | None = None
        if posting_uuid:
            job_url = f"https://www.jobs.gov.sg/career/hrp/{numeric_id}/{posting_uuid}"

        # Fetch all attributes for this object from Algolia
        encoded_id = urllib.parse.quote(object_id, safe="")
        algolia_url = f"{_ALGOLIA_OBJECT_URL}{encoded_id}"

        self._wait()
        with httpx.Client(headers=_ALGOLIA_HEADERS, timeout=30.0) as client:
            response = client.get(algolia_url)
            response.raise_for_status()
            raw = response.json()

        # For non-HRP jobs fall back to any URL field in the Algolia response
        if not job_url:
            job_url = (
                raw.get("job_url")
                or raw.get("url")
                or raw.get("apply_url")
                or raw.get("application_url")
                or None
            )

        title = raw.get("job_title") or raw.get("Jobtitle") or None
        company_name = (
            raw.get("agency_name")
            or raw.get("Agncy")
            or raw.get("agencytitle")
            or None
        )
        location_raw = raw.get("location") or raw.get("LocationTxt") or ""
        location = _strip_html(str(location_raw)) or "Singapore"

        # Skills — Algolia may return a list or a comma-separated string
        raw_skills = raw.get("skills") or raw.get("job_skills") or []
        if isinstance(raw_skills, str):
            skills: list[str] = [s.strip() for s in raw_skills.split(",") if s.strip()]
        elif isinstance(raw_skills, list):
            skills = [str(s).strip() for s in raw_skills if s]
        else:
            skills = []

        description_snippet = _build_description(raw)

        return NormalizedJob(
            source_id=_SOURCE_ID,
            external_id=object_id,
            title=title,
            company_name=company_name,
            location=location,
            job_url=job_url,
            skills=skills,
            description_snippet=description_snippet,
        )
