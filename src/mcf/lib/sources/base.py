"""Base job source interface and normalized job model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence

# ---------------------------------------------------------------------------
# Description cleaning (applied at ingest time, before storage)
# ---------------------------------------------------------------------------

_UNICODE_BULLETS_RE = re.compile(r"[•◦▪▸►·]+")
_EM_DASH_RE = re.compile(r"[–—]+")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_EXCESS_SPACE_RE = re.compile(r" {2,}")

# Sentence-level boilerplate common in Singapore job postings.
# On first match, everything from that sentence onwards is discarded
# (boilerplate is always tail content).
_BOILERPLATE_RES = [
    re.compile(r"\bpdpa\b", re.IGNORECASE),
    re.compile(r"\bpersonal data protection\b", re.IGNORECASE),
    re.compile(r"by (submitting|applying|sending)\b.{0,60}(resume|cv|application|data)\b", re.IGNORECASE),
    re.compile(r"\bonly shortlisted candidates?\b", re.IGNORECASE),
    re.compile(r"\bwe regret (to inform|that only)\b", re.IGNORECASE),
    re.compile(r"\bequal opportunity employer\b", re.IGNORECASE),
    re.compile(r"\btreated in (strict )?confidence\b", re.IGNORECASE),
    re.compile(r"\bdo not hear from us within\b", re.IGNORECASE),
    re.compile(r"\ball applications? will be treated\b", re.IGNORECASE),
]


def clean_description(text: str) -> str:
    """Clean a plain-text job description for storage.

    Applied after HTML stripping. Normalises unicode punctuation, strips
    boilerplate tail content (PDPA notices, EEO statements, shortlist notices),
    and preserves paragraph/bullet structure using newline separators.

    Paragraph structure (newlines) is preserved so that the embedding pipeline
    can later split into meaningful blocks and score them by salience.  Callers
    that previously expected a single flat string will still work — they just
    see newlines instead of spaces between paragraphs.
    """
    if not text:
        return text

    # Normalise unicode noise to ASCII equivalents
    text = _UNICODE_BULLETS_RE.sub("-", text)
    text = _EM_DASH_RE.sub("-", text)
    text = _ZERO_WIDTH_RE.sub("", text)

    # Split into paragraph blocks (preserve structure), then within each block
    # check for boilerplate sentences.  On the first boilerplate hit, discard
    # that block and everything after it (boilerplate is always tail content).
    raw_blocks = re.split(r"\n{2,}", text)
    kept_blocks: list[str] = []
    done = False
    for raw_block in raw_blocks:
        if done:
            break
        # Check each sentence in this block for boilerplate triggers.
        sentences = re.split(r"(?<=[.!?])\s+|\n", raw_block)
        block_lines: list[str] = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            if any(p.search(s) for p in _BOILERPLATE_RES):
                done = True  # discard this sentence and everything after
                break
            block_lines.append(s)
        if block_lines:
            # Re-join sentences within the block with a single newline so that
            # bullet items and short lines remain on separate lines.
            block_text = "\n".join(block_lines)
            block_text = _EXCESS_SPACE_RE.sub(" ", block_text)
            kept_blocks.append(block_text.strip())

    return "\n\n".join(kept_blocks).strip()


@dataclass(frozen=True)
class NormalizedJob:
    """Normalized job representation for storage and embedding.

    All job sources map their API responses to this structure so the rest
    of the pipeline (embedding, matching, storage) is source-agnostic.
    """

    source_id: str
    external_id: str
    title: str | None
    company_name: str | None
    location: str | None
    job_url: str | None
    skills: list[str]
    description: str | None
    categories: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    position_levels: list[str] = field(default_factory=list)
    salary_min: int | None = None
    salary_max: int | None = None
    posted_date: str | None = None
    expiry_date: str | None = None
    min_years_experience: int | None = None

    @property
    def job_uuid(self) -> str:
        """Unique job identifier (source:external_id for cross-source uniqueness)."""
        return f"{self.source_id}:{self.external_id}" if self.source_id != "mcf" else self.external_id


class JobSource(Protocol):
    """Protocol for job data sources.

    Implement this to add a new job source (e.g. LinkedIn, Indeed).
    """

    @property
    def source_id(self) -> str:
        """Unique identifier for this source (e.g. 'mcf', 'linkedin')."""
        ...

    def list_job_ids(
        self,
        *,
        categories: Sequence[str] | None = None,
        limit: int | None = None,
        on_progress=None,
    ) -> list[str]:
        """List job IDs from this source.

        The returned IDs must be in ``job_uuid`` form — i.e. exactly what is
        (or will be) stored as ``job_uuid`` in the database.  This is required
        so the incremental pipeline can diff the result set against
        ``store.existing_job_uuids()`` without an extra translation step.

        For MCF the ``job_uuid`` equals the bare external UUID, so there is no
        difference.  For every other source the ``job_uuid`` is prefixed with
        ``"{source_id}:"`` (e.g. ``"cag:15219929_005056a3-..."``).  The source
        implementation is responsible for applying (and later stripping) this
        prefix in :meth:`get_job_detail`.
        """
        ...

    def get_job_detail(self, job_uuid: str) -> NormalizedJob:
        """Fetch job detail and return as NormalizedJob.

        Args:
            job_uuid: The ID exactly as returned by :meth:`list_job_ids`.
                For non-MCF sources this will be prefixed
                (e.g. ``"cag:15219929_..."``); implementations should strip
                the prefix before calling their upstream API.
        """
        ...
