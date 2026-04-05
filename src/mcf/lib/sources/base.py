"""Base job source interface and normalized job model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


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
    description_snippet: str | None
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
