"""Structured text builder for job embeddings."""

from __future__ import annotations

from mcf.lib.sources.base import NormalizedJob

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
    if normalized.description_snippet:
        parts.append(f"Description: {normalized.description_snippet}")
    return "\n".join(parts)


def build_job_text_from_dict(job: dict) -> str:
    """Build embedding text from a job dict (as returned by Storage.get_all_active_jobs).

    Used by the re-embed CLI command where NormalizedJob objects are not available.
    Expected keys: title, skills (list[str]), position_levels (list[str]),
                   min_years_experience (int | None).
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
    return "\n".join(parts)
