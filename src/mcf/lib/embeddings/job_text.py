"""Structured text builder for job embeddings."""

from __future__ import annotations

import re

from mcf.lib.sources.base import NormalizedJob

# ---------------------------------------------------------------------------
# Role type detection
# ---------------------------------------------------------------------------
# Patterns are checked against title first (strongest signal), then description.
# Order matters: more specific patterns should come before general ones.

_ROLE_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bintern(ship)?\b", re.IGNORECASE), "Internship"),
    (re.compile(r"\bmanagement\s+trainee\b", re.IGNORECASE), "Management Trainee"),
    (re.compile(r"\bgraduate\s+(trainee|programme|program)\b", re.IGNORECASE), "Graduate Trainee"),
    (re.compile(r"\bfresh\s+graduate\b", re.IGNORECASE), "Fresh Graduate"),
    (re.compile(r"\bapprentice(ship)?\b", re.IGNORECASE), "Apprenticeship"),
    (re.compile(r"\bpart[- ]time\b", re.IGNORECASE), "Part-time"),
    (re.compile(r"\btemporary\b|\btemp\s+(staff|position|role|job)\b", re.IGNORECASE), "Temporary"),
    (re.compile(r"\bcontract(ual)?\s+(position|role|staff|basis|job)\b", re.IGNORECASE), "Contract"),
]


def _extract_role_types(title: str | None, description: str | None) -> list[str]:
    """Detect role type signals from title and description.

    Title hits are always included (highest confidence). Description hits fill
    in what the title missed. Returns deduplicated labels in pattern order.
    """
    found: list[str] = []
    seen: set[str] = set()
    for pattern, label in _ROLE_TYPE_PATTERNS:
        if label in seen:
            continue
        if (title and pattern.search(title)) or (description and pattern.search(description)):
            found.append(label)
            seen.add(label)
    return found


# ---------------------------------------------------------------------------
# Salary query structuring
# ---------------------------------------------------------------------------

# Delimiters that signal the job title portion of a query has ended.
_TITLE_END_RE = re.compile(
    r"\s+with\b|\s+using\b|\s+having\b|\s+\d+\+?\s*years?|\s+and\s+\d|,|;",
    re.IGNORECASE,
)


def _extract_query_title(text: str) -> str | None:
    """Extract a likely job title from the opening of a free-text query.

    Takes everything before the first clear title-ending delimiter and rejects
    candidates that are too long (likely a full sentence, not a title).
    """
    m = _TITLE_END_RE.search(text)
    candidate = text[: m.start()].strip() if m else text.strip()
    words = candidate.split()
    if 1 <= len(words) <= 8:
        return candidate.title()
    return None


def structure_salary_query(text: str) -> str:
    """Reformat a free-text salary search query into structured job-embedding format.

    Mirrors the format used for job documents so the query vector lands in the
    same neighbourhood as the documents it should match.

    Only structures what can be extracted with high confidence:
    - Job title (first phrase, up to 8 words)
    - Role type (reuses _extract_role_types — specific multi-word patterns)

    Seniority and years-of-experience are intentionally NOT extracted — keyword
    heuristics for those are noisy and a wrong inference would skew the embedding.
    Those signals are already encoded naturally in the Description text.

    The full original query is always included as Description so no content is lost.
    """
    parts: list[str] = []

    title = _extract_query_title(text)
    if title:
        parts.append(f"Job Title: {title}")

    role_types = _extract_role_types(text, text)
    if role_types:
        parts.append(f"Role Type: {', '.join(role_types)}")

    parts.append(f"Description: {text}")
    return "\n".join(parts)

# MCF position levels in seniority order (lowest → highest).
# Used to detect ranges when a job spans multiple levels.
_LEVEL_ORDER = [
    "fresh/entry level",
    "non-executive",
    "junior executive",
    "executive",
    "senior executive",
    "manager",
    "senior manager",
    "director",
    "c-suite/vp",
]


def _format_seniority(
    position_levels: list[str],
    min_years_experience: int | None,
) -> str | None:
    """Format position level(s) and experience into a natural-language seniority line.

    Single level:   "Seniority: Senior Executive, 5+ years experience"
    Range (span):   "Seniority: Junior Executive to Senior Executive, 3+ years experience"
    Experience only: "Experience: 3+ years"

    Returns None when both inputs are empty/None.
    """
    levels = [l.strip() for l in (position_levels or []) if l and l.strip()]
    years = min_years_experience if (min_years_experience is not None and min_years_experience >= 0) else None

    level_text: str | None = None
    if levels:
        # Map each level to its hierarchy index for range detection.
        indexed = sorted(
            {((_LEVEL_ORDER.index(l.lower()) if l.lower() in _LEVEL_ORDER else -1), l) for l in levels},
            key=lambda x: x[0],
        )
        known = [(i, l) for i, l in indexed if i >= 0]
        unknown = [l for i, l in indexed if i < 0]

        parts: list[str] = []
        if known:
            low_label = known[0][1]
            high_label = known[-1][1]
            if low_label.lower() == high_label.lower():
                parts.append(low_label)
            else:
                parts.append(f"{low_label} to {high_label}")
        if unknown:
            parts.extend(unknown)

        level_text = ", ".join(parts)

    exp_text = f"{years}+ years experience" if years is not None else None

    if level_text and exp_text:
        return f"Seniority: {level_text}, {exp_text}"
    if level_text:
        return f"Seniority: {level_text}"
    if exp_text:
        return f"Experience: {exp_text}"
    return None


def build_job_text_from_normalized(normalized: NormalizedJob) -> str:
    """Build embedding text from a NormalizedJob (source-agnostic)."""
    parts: list[str] = []
    if normalized.title:
        parts.append(f"Job Title: {normalized.title}")
    if normalized.skills:
        parts.append(f"Required Skills: {', '.join(normalized.skills)}")
    seniority = _format_seniority(normalized.position_levels, normalized.min_years_experience)
    if seniority:
        parts.append(seniority)
    role_types = _extract_role_types(normalized.title, normalized.description)
    if role_types:
        parts.append(f"Role Type: {', '.join(role_types)}")
    if normalized.description:
        snippet = " ".join(normalized.description.split()[:300])
        parts.append(f"Description: {snippet}")
    return "\n".join(parts)


def build_job_text_from_dict(job: dict) -> str:
    """Build embedding text from a job dict (as returned by Storage.get_all_active_jobs).

    Used by the re-embed CLI command where NormalizedJob objects are not available.
    Expected keys: title, skills (list[str]), position_levels (list[str]),
                   min_years_experience (int | None), description (str | None).
    """
    parts: list[str] = []
    if job.get("title"):
        parts.append(f"Job Title: {job['title']}")
    if job.get("skills"):
        parts.append(f"Required Skills: {', '.join(job['skills'])}")
    seniority = _format_seniority(
        job.get("position_levels") or [],
        job.get("min_years_experience"),
    )
    if seniority:
        parts.append(seniority)
    role_types = _extract_role_types(job.get("title"), job.get("description"))
    if role_types:
        parts.append(f"Role Type: {', '.join(role_types)}")
    if job.get("description"):
        snippet = " ".join(job["description"].split()[:300])
        parts.append(f"Description: {snippet}")
    return "\n".join(parts)
