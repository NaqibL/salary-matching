"""Storage abstraction interface for job crawler."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class RunStats:
    """Statistics for a crawl run."""

    run_id: str
    started_at: datetime
    finished_at: datetime | None
    total_seen: int
    added: int
    maintained: int
    removed: int


class Storage(ABC):
    """Abstract storage interface.

    PostgresStore implements this interface. All DB access in routes goes through
    here — never import PostgresStore directly.
    """

    # === Crawl runs ===

    @abstractmethod
    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats: ...

    @abstractmethod
    def finish_run(
        self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int
    ) -> None: ...

    @abstractmethod
    def get_recent_runs(self, limit: int = 10) -> list[dict]: ...

    # === Job lifecycle ===

    @abstractmethod
    def existing_job_uuids(self) -> set[str]: ...

    @abstractmethod
    def active_job_uuids(self) -> set[str]: ...

    @abstractmethod
    def active_job_uuids_for_source(self, job_source: str) -> set[str]: ...

    @abstractmethod
    def active_job_uuids_for_source_and_categories(
        self, job_source: str, categories: list[str]
    ) -> set[str]: ...

    @abstractmethod
    def record_statuses(
        self,
        run_id: str,
        *,
        added: Iterable[str],
        maintained: Iterable[str],
        removed: Iterable[str],
    ) -> None: ...

    @abstractmethod
    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None: ...

    @abstractmethod
    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None: ...

    @abstractmethod
    def upsert_new_job_detail(
        self,
        *,
        run_id: str,
        job_uuid: str,
        title: str | None,
        company_name: str | None,
        location: str | None,
        job_url: str | None,
        skills: list[str] | None = None,
        raw_json: dict | None = None,
        categories: list[str] | None = None,
        employment_types: list[str] | None = None,
        position_levels: list[str] | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        posted_date: str | None = None,
        expiry_date: str | None = None,
        description: str | None = None,
    ) -> None: ...

    @abstractmethod
    def update_daily_stats(self, run_id: str) -> None:
        """Recompute job_daily_stats for today from the current active job roster."""
        ...

    def backfill_job_daily_stats(self, limit_days: int = 365) -> dict:
        """One-time backfill of job_daily_stats from jobs table for historical dates.

        Computes active_count, added_count, removed_count per (stat_date, category, employment_type, position_level)
        for each date in the range. Returns {rows_inserted, date_start, date_end}.
        """
        raise NotImplementedError

    def get_job_uuids_needing_description_backfill(self, limit: int | None = None) -> list[str]:
        """Return active MCF job UUIDs where description is NULL (need description backfill)."""
        raise NotImplementedError

    def update_job_description(self, job_uuid: str, description: str) -> None:
        """Set the description field for a single job row."""
        raise NotImplementedError

    def update_llm_extracted_fields(
        self,
        job_uuid: str,
        *,
        min_years_experience: int | None,
        llm_fields_json: dict | None,
    ) -> None:
        """Persist LLM-extracted fields for a job. Called by the embedder after the LLM pass."""
        raise NotImplementedError

    def update_llm_extracted_fields_batch(
        self,
        rows: list[tuple[str, int | None, dict | None]],
    ) -> None:
        """Persist LLM-extracted fields for many jobs in one round trip.

        ``rows`` are ``(job_uuid, min_years_experience, llm_fields_json)``.
        Default implementation loops over :meth:`update_llm_extracted_fields`;
        stores should override with a single statement.
        """
        for job_uuid, min_years, fields in rows:
            self.update_llm_extracted_fields(
                job_uuid, min_years_experience=min_years, llm_fields_json=fields
            )

    def get_job_uuids_needing_rich_backfill(self, limit: int | None = None) -> list[str]:
        """Return MCF job UUIDs where categories_json is NULL or empty (need backfill).
        Used by backfill-rich-fields to populate rich metadata from the MCF API."""
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_uuid: str) -> dict | None: ...

    @abstractmethod
    def get_active_job_count(self) -> int: ...

    def get_hot_jobs(
        self,
        min_pct: float = 20.0,
        category: str | None = None,
        position_level: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Active jobs paying >= min_pct above their peer-group (hot_jobs_cluster
        x seniority) median salary, ordered by above_market_pct desc."""
        raise NotImplementedError

    # === Job classifications (Jev role families, SGSAL-022) ===

    def upsert_role_families(self, rows: list[tuple[int, str, str, str]]) -> None:
        """Seed/refresh the role_families lookup: (id, key, display_name, description)."""
        raise NotImplementedError

    def get_role_families(self) -> list[dict]:
        """Return [{id, key, display_name, description}] sorted by id."""
        raise NotImplementedError

    def batch_upsert_jev_classifications(
        self, rows: list[tuple[str, str, int, str, float, float]]
    ) -> None:
        """Persist Jev output for a batch of jobs.

        rows: (job_uuid, role_family_key, role_family_id, predicted_tier, role_conf, tier_conf).
        Also writes role_family_id into role_cluster and clears the stale
        KMeans multi-label role_clusters_json so the matches filters stay consistent.
        """
        raise NotImplementedError

    def get_active_jobs_missing_role_family(self, limit: int) -> list[dict]:
        """Active jobs with role_family IS NULL: job_uuid, title, description, position_levels."""
        raise NotImplementedError

    def count_active_jobs_missing_role_family(self) -> int:
        raise NotImplementedError

    # --- Retention ---

    def prune_job_run_status(self, keep_days: int = 90) -> int:
        """Delete job_run_status rows of crawl runs started more than keep_days ago.

        Only the current run's rows are ever read (daily stats), so this is pure
        housekeeping. Returns the number of rows deleted.
        """
        raise NotImplementedError

    def describe_columns(self, relation: str) -> set[str]:
        """Column names of a table/view. Used by tests and /schema-diff."""
        raise NotImplementedError

    def assign_hot_jobs_scores(self, job_uuids: list[str]) -> None:
        """Assign hot_jobs_cluster (nearest centroid) and above_market_pct for a
        batch of jobs, entirely server-side against hot_jobs_cluster_centroids /
        hot_jobs_salary_profiles.

        Separate from role_cluster/predicted_tier (the matching taxonomy) —
        this is the k=23 peer-group clustering used only by the hot-jobs page.
        """
        raise NotImplementedError

    def get_active_job_uuids_missing_hot_jobs_score(self, limit: int) -> list[str]:
        """Return active job UUIDs with an embedding but no above_market_pct yet,
        newest posted first. /hot-jobs only ever surfaces recent listings, so
        this is a recency-ordered catch-up, not a full backlog drain — jobs
        that fall outside the newest slice are irrelevant to the page and are
        deliberately left unscored.
        """
        raise NotImplementedError

    # === Job embeddings ===

    @abstractmethod
    def upsert_embedding(
        self, *, job_uuid: str, model_name: str, embedding: Sequence[float]
    ) -> None: ...

    def upsert_embeddings_batch(
        self,
        *,
        model_name: str,
        rows: list[tuple[str, Sequence[float]]],
    ) -> None:
        """Upsert multiple embeddings in one round-trip. rows = [(job_uuid, embedding), ...]"""
        for job_uuid, embedding in rows:
            self.upsert_embedding(job_uuid=job_uuid, model_name=model_name, embedding=embedding)

    @abstractmethod
    def get_active_job_embeddings(
        self,
        query_embedding: Sequence[float] | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, str, list[float], dict]]: ...

    @abstractmethod
    def get_all_active_jobs(self) -> list[dict]: ...

    def get_active_jobs_without_embeddings(self) -> list[dict]:
        """Return active jobs that have no row in job_embeddings. Default: filter get_all_active_jobs."""
        raise NotImplementedError

    def get_active_jobs_embedded_since(self, days: int, *, missing_llm_only: bool = False) -> list[dict]:
        """Return active jobs whose embedding was written within the last `days` days.

        With ``missing_llm_only`` only jobs whose LLM-extracted fields are empty
        (no canonical skills and no inferred seniority) are returned — used to
        repair a window where the cleaner failed but the embed still ran.
        """
        raise NotImplementedError

    @abstractmethod
    def get_job_embeddings_for_uuids(
        self, uuids: list[str]
    ) -> list[tuple[str, list[float]]]: ...

    @abstractmethod
    def get_embedding_model_name(self) -> str | None: ...

    def get_active_jobs_pool(
        self,
    ) -> list[tuple[str, Any, datetime | None]]:
        """Return (job_uuid, embedding, last_seen_at) for every vector that some active
        job owns or points at (SGSAL-024: reposts share their canonical's vector, so
        the owner itself may be inactive). job_uuid is the vector owner; last_seen_at
        is the latest among the active members.
        Used by active_jobs_pool_cache for in-memory similarity computation."""
        raise NotImplementedError

    @abstractmethod
    def get_active_job_ids_ranked(
        self,
        query_embedding: Sequence[float],
        limit: int = 5000,
    ) -> list[tuple[str, float, datetime | None]]:
        """Return (job_uuid, cosine_distance, last_seen_at) sorted by distance ASC.

        Active gate (SGSAL-024): a vector is included when some active job owns it
        or points at it; job_uuid is the vector owner and last_seen_at the latest
        among its active members."""
        ...

    def get_all_embedded_job_ids_ranked(
        self,
        query_embedding: Sequence[float],
        limit: int = 5000,
    ) -> list[tuple[str, float, datetime | None]]:
        """Return (job_uuid, cosine_distance, last_seen_at) sorted ASC for ALL jobs
        with embeddings — active AND inactive. Used for salary percentile pools only."""
        raise NotImplementedError

    @abstractmethod
    def get_jobs_by_uuids(self, uuids: list[str]) -> list[dict]:
        """Return full job dicts for each uuid; output order matches input order."""
        ...

    def get_job_uuids_for_filter(
        self,
        role_clusters: list[int] | None = None,
        predicted_tiers: list[str] | None = None,
    ) -> set[str] | None:
        """Return set of active job UUIDs matching the given role/tier filters.
        Returns None if no filters are specified (caller should skip filtering)."""
        raise NotImplementedError

    def get_job_uuids_with_salary_filter(
        self,
        salary_min: int | None = None,
        salary_max: int | None = None,
    ) -> set[str] | None:
        """Return UUIDs of active jobs whose salary_min is within [salary_min, salary_max].
        Returns None if no salary bounds are specified (caller skips filtering).
        Only jobs with non-null salary_min are included when any bound is given."""
        raise NotImplementedError

    @abstractmethod
    def create_match_session(
        self,
        *,
        user_id: str,
        mode: str,
        ranked_ids: list[str],
        ttl_seconds: int = 7200,
    ) -> str:
        """Store ranked_ids, return new session_id."""
        ...

    @abstractmethod
    def get_match_session(self, session_id: str, user_id: str) -> dict | None:
        """Return {session_id, ranked_ids, total} or None if not found/expired."""
        ...

    # === Users ===

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> dict | None: ...

    @abstractmethod
    def upsert_user(self, *, user_id: str, email: str, role: str = "candidate") -> None: ...

    # === Profiles ===

    @abstractmethod
    def create_profile(
        self,
        *,
        profile_id: str,
        user_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
    ) -> None: ...

    @abstractmethod
    def get_profile_by_user_id(self, user_id: str) -> dict | None: ...

    @abstractmethod
    def get_profile_by_profile_id(self, profile_id: str) -> dict | None: ...

    @abstractmethod
    def update_profile(
        self,
        *,
        profile_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
        resume_storage_path: str | None = None,
    ) -> None: ...

    # === Candidate embeddings ===

    @abstractmethod
    def upsert_candidate_embedding(
        self, *, profile_id: str, model_name: str, embedding: Sequence[float]
    ) -> None: ...

    @abstractmethod
    def get_candidate_embedding(self, profile_id: str) -> list[float] | None: ...

    @abstractmethod
    def upsert_taste_embedding(
        self, *, profile_id: str, model_name: str, embedding: Sequence[float]
    ) -> None: ...

    @abstractmethod
    def get_taste_embedding(self, profile_id: str) -> list[float] | None: ...

    # === Interactions ===

    @abstractmethod
    def record_interaction(
        self, *, user_id: str, job_uuid: str, interaction_type: str
    ) -> None: ...

    @abstractmethod
    def get_interacted_jobs(self, user_id: str) -> set[str]: ...

    @abstractmethod
    def get_interested_job_uuids(self, user_id: str) -> list[str]: ...

    @abstractmethod
    def get_not_interested_job_uuids(self, user_id: str) -> list[str]: ...

    def get_interested_jobs(self, user_id: str) -> list[dict]:
        """Return interested jobs with job details, ordered by interacted_at desc (most recent first).
        Each dict has job fields plus similarity_score=1 for Match display."""
        raise NotImplementedError

    # === Discover ===

    @abstractmethod
    def get_discover_stats(self, user_id: str) -> dict: ...

    # === Dashboard ===

    @abstractmethod
    def get_dashboard_summary(self) -> dict: ...

    def get_jobs_over_time_posted_and_removed(self, limit_days: int = 90) -> list[dict]:
        """Added and removed counts per day from job_daily_stats (primary source only).
        Returns list of {date, added_count, removed_count}. Empty if job_daily_stats has no data."""
        raise NotImplementedError

    def get_active_jobs_over_time(self, limit_days: int = 90) -> list[dict]:
        """Total active jobs per day from job_daily_stats (primary source only).
        Returns list of {date, active_count}. Empty if job_daily_stats has no data."""
        raise NotImplementedError

    @abstractmethod
    def get_jobs_by_category(self, limit_days: int = 90, limit: int = 30) -> list[dict]: ...

    def get_category_trends(self, category: str, limit_days: int = 90) -> list[dict]:
        """Trend data for a category from job_daily_stats. Returns [{date, active_count, added_count, removed_count}]."""
        raise NotImplementedError

    @abstractmethod
    def get_jobs_by_employment_type(self, limit_days: int = 90, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def get_jobs_by_position_level(self, limit_days: int = 90, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def get_salary_distribution(self) -> list[dict]: ...

    # --- LLM-field analytics (jobs.llm_fields_json / jobs.role_family) ---

    @abstractmethod
    def get_seniority_breakdown(self) -> list[dict]:
        """Active jobs grouped by LLM-inferred seniority.

        Returns [{seniority, jobs, median_salary}] ordered Intern -> Director.
        Only rows with ``inferred_seniority`` present are counted; median_salary
        is percentile_cont(0.5) of (salary_min+salary_max)/2 over valid ranges,
        or None when no job in the group discloses a usable salary.
        """
        ...

    @abstractmethod
    def get_top_skills(self, limit: int = 25, role_family: str | None = None) -> list[dict]:
        """Most-mentioned ``canonical_skills`` across active jobs, case-folded.

        Returns [{skill, jobs, median_salary}] sorted by jobs desc. ``role_family``
        (a role_families.key) restricts to that family when given.
        """
        ...

    @abstractmethod
    def get_skills_trend(self, skills: list[str], weeks: int = 12) -> list[dict]:
        """Weekly count of jobs (posted in the last ``weeks`` weeks, active or not)
        mentioning each skill (case-insensitive). Returns [{week, skill, jobs}]
        with a row for every (week, skill) pair, zero-filled, ordered by week then skill.
        """
        ...

    @abstractmethod
    def get_role_family_breakdown(self) -> list[dict]:
        """Active jobs grouped by Jev role_family (NULLs excluded).

        Returns [{role_family, display_name, jobs, median_salary}] sorted by jobs desc.
        """
        ...

    def get_charts_static(self, cat_limit: int = 30, et_limit: int = 20, pl_limit: int = 20) -> dict:
        """Bundle the four time-range-independent chart datasets into a single call."""
        return {
            "jobs_by_category": self.get_jobs_by_category(limit=cat_limit),
            "jobs_by_employment_type": self.get_jobs_by_employment_type(limit=et_limit),
            "jobs_by_position_level": self.get_jobs_by_position_level(limit=pl_limit),
            "salary_distribution": self.get_salary_distribution(),
        }

    @abstractmethod
    def get_jobs_with_salary_by_uuids(
        self,
        job_uuids: list[str],
        *,
        compliant_ranges_only: bool = False,
        representative: bool = False,
        company_name: str | None = None,
    ) -> list[dict]:
        """Return job rows (title, company_name, location, job_url, salary_min/max,
        last_seen_at, is_active, description, min_years_experience, llm_fields_json).

        Args:
            job_uuids: UUIDs to fetch. With ``representative=True`` these are
                *canonical* UUIDs (what the similarity queries return).
            compliant_ranges_only: drop rows where salary_max > 2 * salary_min
                (benchmark pools only, never display cards). NULL bounds are kept.
            representative: return the group's **latest occurrence** (active
                preferred) instead of the canonical row, plus the group facts
                ``canonical_job_uuid, repost_count, active_count, first_posted,
                last_posted, reposts_365d, distinct_companies, min_salary_seen,
                max_salary_seen``. UUIDs without a group return themselves with
                ``repost_count = 1``.
            company_name: with ``representative=True``, pick the latest occurrence
                among members at this company (company tab of the checker).
        """

    # === Posting groups / reposts (SGSAL-024) ===

    @abstractmethod
    def set_content_hashes(self, rows: list[tuple[str, str | None]]) -> None:
        """Write (job_uuid, content_hash) pairs. content_hash comes from
        ``mcf.lib.pipeline.posting_key.posting_key`` and is None for text-less jobs."""

    @abstractmethod
    def find_canonicals(self, hashes: list[str]) -> dict[str, str]:
        """Map content_hash -> canonical job_uuid for hashes whose canonical row
        (``canonical_job_uuid = job_uuid``) already has an embedding. Unknown hashes are absent."""

    @abstractmethod
    def link_reposts(self, pairs: list[tuple[str, str]]) -> int:
        """Set ``canonical_job_uuid`` for each (job_uuid, canonical_job_uuid) pair and
        copy LLM fields + Jev labels from the canonical where the job's are NULL.
        Self-pairs are allowed (they only set the pointer). Returns rows updated."""

    @abstractmethod
    def refresh_posting_groups(self) -> None:
        """REFRESH MATERIALIZED VIEW CONCURRENTLY posting_groups. Call at crawl end."""

    @abstractmethod
    def get_posting_history(self, job_uuid: str) -> dict | None:
        """The posting group (incl. ``occurrences`` list) that ``job_uuid`` belongs to, or None."""

    @abstractmethod
    def get_most_reposted(self, days: int = 365, limit: int = 20) -> list[dict]:
        """Posting groups ordered by reposts in the window (``days`` is 90 or 365)."""

    @abstractmethod
    def active_canonical_uuids(self) -> set[str]:
        """``COALESCE(canonical_job_uuid, job_uuid)`` of every active job (checker gates)."""

    # --- SGSAL-024 backfill helpers (scripts/backfill_posting_keys.py) ---

    @abstractmethod
    def iter_jobs_needing_hash(self, after_uuid: str, limit: int) -> list[tuple[str, str | None, str]]:
        """(job_uuid, title, description) for jobs with a non-blank description and no
        content_hash yet, job_uuid > after_uuid, ordered by job_uuid."""

    @abstractmethod
    def assign_canonicals(self) -> int:
        """Set canonical_job_uuid where NULL: per hash prefer an existing canonical that has an embedding, then a
        v2-embedded row, then any embedded row, then the earliest seen. Text-less rows
        point at themselves. Returns rows updated."""

    @abstractmethod
    def copy_fields_from_canonicals(self) -> int:
        """For non-canonical members, fill NULL LLM fields / Jev labels from the canonical."""

    @abstractmethod
    def noncanonical_embedded_uuids(self) -> list[str]:
        """job_uuids that have an embedding but are not their group's canonical, and whose canonical already holds an embedding."""

    @abstractmethod
    def delete_embeddings_by_uuids(self, uuids: list[str]) -> int:
        """Delete job_embeddings rows for the given uuids (batched by caller). Returns rows deleted."""

    @abstractmethod
    def posting_group_stats(self) -> dict:
        """{groups, members, max_repost_count, p50_reposts_365d, p95_reposts_365d} from posting_groups."""

    @abstractmethod
    def get_distinct_companies(self) -> list[str]:
        """Return sorted list of distinct company_name values from active jobs."""
        ...

    @abstractmethod
    def get_active_job_uuids_by_company(self, company_name: str, active_only: bool = True) -> set[str]:
        """Return UUIDs of jobs from the given company. Defaults to active jobs only."""
        ...

    @abstractmethod
    def get_company_jobs_ranked(
        self,
        query_embedding: Sequence[float],
        company_name: str,
        limit: int = 20,
    ) -> list[tuple[str, float, Any]]:
        """Return (job_uuid, cosine_distance, last_seen_at) for all embedded jobs from the given company, ranked by similarity. Includes active and historical."""
        ...

    @abstractmethod
    def get_company_alias_map(self) -> dict[str, str]:
        """Return mapping of raw_name → canonical_name for all non-self aliases."""
        ...

    @abstractmethod
    def get_all_jobs_by_company(self, company_name: str) -> list[dict]:
        """Return all jobs (active and inactive) for the given company."""
        ...

    @abstractmethod
    def get_top_companies(self, limit: int = 20) -> list[dict]:
        """Return top companies by active job count as [{name, active_count}]."""
        ...

    def reset_profile_ratings(self, user_id: str) -> dict:
        """Reset job interactions and taste profile for a user (for testing).
        Returns counts of deleted rows. Override in store implementations."""
        raise NotImplementedError

    # === Match recording ===

    @abstractmethod
    def record_match(
        self,
        *,
        match_id: str,
        profile_id: str,
        job_uuid: str,
        similarity_score: float,
        match_type: str,
    ) -> None: ...

    # === Cache metadata ===

    def get_cache_metadata(self, key: str) -> dict | None:
        """Return {key, value_json, updated_at} or None. Postgres only."""
        raise NotImplementedError

    def set_cache_metadata(self, key: str, value_json: dict) -> None:
        """Upsert cache_metadata row. Postgres only."""
        raise NotImplementedError

    def update_crawl_completed_timestamp(self) -> None:
        """Update crawl_completed_at in cache_metadata. Postgres only."""
        try:
            from datetime import datetime, timezone

            self.set_cache_metadata("crawl_completed_at", {"ts": datetime.now(timezone.utc).isoformat()})
        except NotImplementedError:
            pass

    # === Lifecycle ===

    @abstractmethod
    def close(self) -> None: ...
