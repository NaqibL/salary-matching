"""Structured text builder for job embeddings."""

from __future__ import annotations

import re
from typing import Callable

from mcf.lib.embeddings.job_description_extractor import LLMCleanResult, extract_high_signal_description
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


def build_job_text_from_normalized(
    normalized: NormalizedJob,
    token_counter: Callable[[str], int] | None = None,
) -> tuple[str, LLMCleanResult | None]:
    """Build embedding text from a NormalizedJob (source-agnostic).

    Returns (embedding_text, llm_result) where llm_result is non-None only
    when the LLM cleaning pass ran.  Callers should persist llm_result via
    ``store.update_llm_extracted_fields`` so extracted fields are available
    for filtering and future re-embeds.

    Args:
        normalized: The normalized job object.
        token_counter: Optional callable mapping text → token count.
    """
    llm_result: LLMCleanResult | None = None
    description_text: str | None = None

    if normalized.description:
        description_text, diags = extract_high_signal_description(
            description=normalized.description,
            title=normalized.title,
            token_counter=token_counter,
        )
        llm_result = diags.get("llm_result")

    # Use inferred_seniority from LLM as fallback when the scraper provided no position_levels
    effective_position_levels = normalized.position_levels
    if not effective_position_levels and llm_result and llm_result.inferred_seniority:
        effective_position_levels = [llm_result.inferred_seniority]

    # Use canonical_skills from LLM if available, else fall back to scraped skills
    effective_skills = (
        llm_result.canonical_skills
        if llm_result and llm_result.canonical_skills
        else normalized.skills
    )

    parts: list[str] = []
    if normalized.title:
        parts.append(f"Job Title: {normalized.title}")
    if effective_skills:
        parts.append(f"Required Skills: {', '.join(effective_skills)}")
    seniority = _format_seniority(effective_position_levels, None)
    if seniority:
        parts.append(seniority)
    role_types = _extract_role_types(normalized.title, normalized.description)
    if role_types:
        parts.append(f"Role Type: {', '.join(role_types)}")
    if description_text:
        parts.append(f"Description: {description_text}")
    return "\n".join(parts), llm_result


def build_job_text_from_dict(
    job: dict,
    token_counter: Callable[[str], int] | None = None,
) -> tuple[str, LLMCleanResult | None]:
    """Build embedding text from a job dict (as returned by Storage.get_all_active_jobs).

    Used by the re-embed CLI command where NormalizedJob objects are not available.
    Expected keys: title, skills (list[str]), position_levels (list[str]),
                   min_years_experience (int | None), description (str | None).

    Returns (embedding_text, llm_result).  Callers should persist llm_result
    via ``store.update_llm_extracted_fields`` when it is non-None.

    Args:
        job: Job dict from storage.
        token_counter: Optional callable mapping text → token count.
    """
    llm_result: LLMCleanResult | None = None
    description_text: str | None = None

    if job.get("description"):
        description_text, diags = extract_high_signal_description(
            description=job["description"],
            title=job.get("title"),
            token_counter=token_counter,
        )
        llm_result = diags.get("llm_result")

    # Use inferred_seniority from LLM as fallback when the scraper provided no position_levels.
    # For the dict path, min_years_experience is already persisted from a previous LLM pass.
    scraped_levels = job.get("position_levels") or []
    effective_position_levels = scraped_levels
    if not effective_position_levels and llm_result and llm_result.inferred_seniority:
        effective_position_levels = [llm_result.inferred_seniority]

    # Prefer LLM canonical skills over raw scraped skills
    effective_skills = (
        llm_result.canonical_skills
        if llm_result and llm_result.canonical_skills
        else (job.get("skills") or [])
    )

    parts: list[str] = []
    if job.get("title"):
        parts.append(f"Job Title: {job['title']}")
    if effective_skills:
        parts.append(f"Required Skills: {', '.join(effective_skills)}")
    seniority = _format_seniority(
        effective_position_levels,
        job.get("min_years_experience"),
    )
    if seniority:
        parts.append(seniority)
    role_types = _extract_role_types(job.get("title"), job.get("description"))
    if role_types:
        parts.append(f"Role Type: {', '.join(role_types)}")
    if description_text:
        parts.append(f"Description: {description_text}")
    return "\n".join(parts), llm_result
