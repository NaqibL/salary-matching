"""Incremental crawl pipeline."""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence


def _notify_crawl_complete() -> None:
    """Call Next.js webhook to invalidate caches (dashboard, matches, pool, job)."""
    import time

    webhook_url = os.getenv("CRAWL_WEBHOOK_URL") or os.getenv("NEXT_PUBLIC_VERCEL_URL")
    if not webhook_url:
        return
    if not webhook_url.startswith("http"):
        webhook_url = f"https://{webhook_url}"
    webhook_url = f"{webhook_url.rstrip('/')}/api/webhooks/crawl-complete"

    secret = os.getenv("CRON_SECRET") or os.getenv("REVALIDATE_SECRET")
    if not secret:
        return

    req = urllib.request.Request(
        webhook_url,
        method="POST",
        headers={"X-Crawl-Secret": secret, "Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status >= 400:
                    print(f"Warning: crawl webhook returned {resp.status}")
                return
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2**attempt)
    print(f"Warning: crawl webhook failed after 3 attempts: {last_err}")

from mcf.lib.embeddings.base import EmbedderProtocol
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache
from mcf.lib.embeddings.job_text import build_job_text_from_normalized
from mcf.lib.sources.base import NormalizedJob
from mcf.lib.sources.mcf_source import MCFJobSource
from mcf.lib.storage.base import RunStats, Storage

if TYPE_CHECKING:
    from mcf.lib.sources.base import JobSource


@dataclass(frozen=True)
class IncrementalCrawlResult:
    run: RunStats
    total_seen: int
    added: list[str]
    maintained: list[str]
    removed: list[str]


def run_incremental_crawl(
    *,
    store: Storage,
    source: JobSource | None = None,
    embedder: EmbedderProtocol | None = None,
    rate_limit: float = 4.0,
    categories: Sequence[str] | None = None,
    limit: int | None = None,
    on_progress=None,
    embed: bool = True,
) -> IncrementalCrawlResult:
    """Run an incremental crawl.

    - Lists job IDs from the source (cheap)
    - Diffs against DB to compute added/maintained/removed
    - Fetches job detail only for newly added jobs
    """
    job_source = source or MCFJobSource(rate_limit=rate_limit)

    try:
        run = store.begin_run(kind="incremental", categories=list(categories) if categories else None)

        seen = job_source.list_job_ids(
            categories=list(categories) if categories else None,
            limit=limit,
            on_progress=on_progress,
        )
        seen_set = set(seen)
        existing = store.existing_job_uuids()
        active = store.active_job_uuids()

        added = sorted(seen_set - existing)
        maintained = sorted(seen_set & existing)
        # Removals can be inferred whenever we have a complete view of a well-defined
        # slice of the job universe:
        #   - full crawl (no category filter, no limit): diff against all active jobs
        #   - category-scoped crawl (no limit): diff against active jobs in those categories
        # A limit-capped crawl never sees the full slice, so removals cannot be inferred.
        if limit is not None:
            removed = []
        elif categories is not None:
            # Category-scoped: only retire jobs whose category overlaps the crawled set
            active_in_scope = store.active_job_uuids_for_source_and_categories(
                job_source.source_id, list(categories)
            )
            removed = sorted(active_in_scope - seen_set)
        elif hasattr(store, "active_job_uuids_for_source"):
            active_for_source = store.active_job_uuids_for_source(job_source.source_id)
            removed = sorted(active_for_source - seen_set)
        else:
            removed = sorted(active - seen_set)

        store.record_statuses(run.run_id, added=added, maintained=maintained, removed=removed)
        store.touch_jobs(run_id=run.run_id, job_uuids=maintained)
        if removed:
            store.deactivate_jobs(run_id=run.run_id, job_uuids=removed)

        if added:
            if embed:
                _embeddings_cache = (
                    EmbeddingsCache(store=store)
                    if os.getenv("ENABLE_EMBEDDINGS_CACHE", "1") in ("1", "true", "yes")
                    else None
                )
                _embedder: EmbedderProtocol = (
                    embedder
                    if embedder is not None
                    else Embedder(EmbedderConfig(), embeddings_cache=_embeddings_cache)
                )
                cfg = getattr(_embedder, "config", None)
                batch_size = cfg.batch_size if cfg and hasattr(cfg, "batch_size") else 32

            # Phase 1: Fetch job details and upsert (no embeddings yet)
            jobs_to_embed: list[tuple[NormalizedJob, str]] = []  # (normalized, job_text)
            for external_id in added:
                normalized = job_source.get_job_detail(external_id)
                job_uuid = normalized.job_uuid
                job_text = build_job_text_from_normalized(normalized)

                store.upsert_new_job_detail(
                    run_id=run.run_id,
                    job_uuid=job_uuid,
                    title=normalized.title,
                    company_name=normalized.company_name,
                    location=normalized.location,
                    job_url=normalized.job_url,
                    skills=normalized.skills or None,
                    categories=normalized.categories or None,
                    employment_types=normalized.employment_types or None,
                    position_levels=normalized.position_levels or None,
                    salary_min=normalized.salary_min,
                    salary_max=normalized.salary_max,
                    posted_date=normalized.posted_date,
                    expiry_date=normalized.expiry_date,
                    description=normalized.description,
                )

                if job_text:
                    jobs_to_embed.append((normalized, job_text))

            if embed:
                # Phase 2: Batch embed and upsert (10–30x faster than one-by-one with GPU)
                embedded: list[tuple[str, list[float]]] = []  # (job_uuid, embedding)
                for i in range(0, len(jobs_to_embed), batch_size):
                    batch = jobs_to_embed[i : i + batch_size]
                    texts = [jt for _, jt in batch]
                    try:
                        embeddings = _embedder.embed_texts(texts)
                        for (normalized, _), emb in zip(batch, embeddings):
                            store.upsert_embedding(
                                job_uuid=normalized.job_uuid,
                                model_name=_embedder.model_name,
                                embedding=emb,
                            )
                            embedded.append((normalized.job_uuid, emb))
                    except Exception as e:
                        for normalized, _ in batch:
                            print(f"Warning: Failed to generate embedding for job {normalized.job_uuid}: {e}")

                # Phase 3: Classify all new jobs in one batch (role cluster + experience tier + multi-label)
                if embedded:
                    try:
                        import numpy as np
                        from mcf.matching.classifiers import classify_jobs, classify_jobs_multilabel

                        emb_matrix = np.array([e for _, e in embedded], dtype=np.float32)
                        classifications_raw = classify_jobs(emb_matrix)
                        classifications = [
                            (job_uuid, role_cluster, predicted_tier)
                            for (job_uuid, _), (role_cluster, predicted_tier)
                            in zip(embedded, classifications_raw)
                        ]
                        store.batch_upsert_job_classifications(classifications)

                        multi_labels = classify_jobs_multilabel(emb_matrix)
                        store.batch_upsert_multi_label_clusters(
                            [(job_uuid, clusters) for (job_uuid, _), clusters in zip(embedded, multi_labels)]
                        )
                    except Exception as e:
                        print(f"Warning: job classification failed, skipping: {e}")

        store.update_daily_stats(run.run_id)
        store.delete_inactive_job_embeddings()
        store.finish_run(
            run.run_id,
            total_seen=len(seen_set),
            added=len(added),
            maintained=len(maintained),
            removed=len(removed),
        )

        # Refresh dashboard materialized views (Postgres only; non-fatal)
        if hasattr(store, "refresh_dashboard_materialized_views"):
            try:
                store.refresh_dashboard_materialized_views()
            except Exception as _mv_err:
                print(f"Warning: failed to refresh dashboard materialized views: {_mv_err}")

        # Invalidate active jobs pool cache when same process runs API + crawl
        try:
            from mcf.api.cache.job_pool import invalidate

            invalidate()
        except ImportError:
            pass

        # Notify Next.js + FastAPI to invalidate caches (webhook)
        _notify_crawl_complete()

        # Update DB cache timestamp (Postgres only)
        if hasattr(store, "update_crawl_completed_timestamp"):
            try:
                store.update_crawl_completed_timestamp()
            except Exception:
                pass

        final_run = RunStats(
            run_id=run.run_id,
            started_at=run.started_at,
            finished_at=None,
            total_seen=len(seen_set),
            added=len(added),
            maintained=len(maintained),
            removed=len(removed),
        )
        return IncrementalCrawlResult(
            run=final_run,
            total_seen=len(seen_set),
            added=added,
            maintained=maintained,
            removed=removed,
        )
    finally:
        pass  # Store cleanup handled by caller

