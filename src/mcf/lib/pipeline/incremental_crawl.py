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
from mcf.lib.embeddings.job_description_extractor import LLMCleanResult
from mcf.lib.embeddings.job_text import build_job_text_from_normalized, build_texts_parallel
from mcf.lib.pipeline.reposts import link_reposts_for_batch
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
    reposts_linked: int = 0


def _classify_with_jev(store: Storage, jev, jobs_to_embed, embedded) -> None:
    """Run Jev over the jobs that were just embedded and persist role family + tier."""
    from mcf.lib.embeddings.jev_classifier import ROLE_FAMILY_ID, role_family_rows

    by_uuid = {n.job_uuid: n for n, _, _ in jobs_to_embed}
    targets = [by_uuid[u] for u, _ in embedded if u in by_uuid]
    if not targets:
        return
    store.upsert_role_families(role_family_rows())
    results = jev.classify_many(
        [(n.title, n.description, n.position_levels) for n in targets]
    )
    rows = [
        (n.job_uuid, r.role_key, ROLE_FAMILY_ID[r.role_key], r.tier, r.role_conf, r.tier_conf)
        for n, r in zip(targets, results)
        if r is not None
    ]
    store.batch_upsert_jev_classifications(rows)
    failed = len(targets) - len(rows)
    if failed:
        print(f"Warning: Jev left {failed}/{len(targets)} jobs unclassified")


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
        seen = job_source.list_job_ids(
            categories=list(categories) if categories else None,
            limit=limit,
            on_progress=on_progress,
        )
        seen_set = set(seen)

        run = store.begin_run(kind="incremental", categories=list(categories) if categories else None)
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

        repost_uuids: set[str] = set()
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
            fetched: list[NormalizedJob] = []
            company_rows: list[dict] = []
            for external_id in added:
                try:
                    normalized = job_source.get_job_detail(external_id)
                except Exception as e:
                    # A single malformed/erroring listing (e.g. MCF's own API returning a
                    # transient 4xx/5xx for one job) shouldn't abort the whole crawl run.
                    print(f"Warning: skipping {external_id}: {e}")
                    continue
                job_uuid = normalized.job_uuid
                fetched.append(normalized)

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
                # SGSAL-028: posting-company registry (SSIC drives the agency label). MCF only —
                # CAG carries no registry data; flushed once after Phase 1.
                if normalized.company_name and normalized.source_id == "mcf":
                    company_rows.append({
                        "name": normalized.company_name,
                        "uen": normalized.company_uen,
                        "ssic_code": normalized.company_ssic_code,
                        "ssic_code_2020": normalized.company_ssic_code_2020,
                        "ssic_description": normalized.company_ssic_description,
                        "employee_count": normalized.company_employee_count,
                        "source": "mcf",
                    })

            if company_rows:
                try:
                    n_companies = store.upsert_companies(company_rows)
                    print(f"Registry: {n_companies} companies upserted")
                except Exception as e:  # noqa: BLE001
                    print(f"Warning: company registry upsert failed, skipping: {e}")

            # Phase 1a: reposts (same title + description as a posting we already
            # hold) link to the existing canonical and skip the expensive steps.
            repost_uuids = link_reposts_for_batch(store, fetched)
            if repost_uuids:
                # Reposts skip embedding, so score them now against the canonical's
                # vector (above_market_pct uses each row's own salary; never copied).
                try:
                    store.assign_hot_jobs_scores(sorted(repost_uuids))
                except Exception as e:  # noqa: BLE001
                    print(f"Warning: hot-jobs scoring for reposts failed, skipping: {e}")
            fetched = [n for n in fetched if n.job_uuid not in repost_uuids]

            # Phase 1b: Build embedding text. The optional LLM cleaning call is
            # network-bound, so it runs on a thread pool (LLM_CLEAN_WORKERS).
            # Tuple: (normalized, job_text, llm_result)
            jobs_to_embed: list[tuple[NormalizedJob, str, LLMCleanResult | None]] = []
            for normalized, (job_text, llm_result) in zip(
                fetched, build_texts_parallel(fetched, build_job_text_from_normalized)
            ):
                if job_text:
                    jobs_to_embed.append((normalized, job_text, llm_result))

            if embed:
                # Phase 2: Batch embed and upsert (10–30x faster than one-by-one with GPU)
                embedded: list[tuple[str, list[float]]] = []  # (job_uuid, embedding)
                for i in range(0, len(jobs_to_embed), batch_size):
                    batch = jobs_to_embed[i : i + batch_size]
                    texts = [jt for _, jt, _ in batch]
                    try:
                        embeddings = _embedder.embed_texts(texts)
                        llm_rows: list[tuple[str, int | None, dict | None]] = []
                        for (normalized, _, llm_result), emb in zip(batch, embeddings):
                            store.upsert_embedding(
                                job_uuid=normalized.job_uuid,
                                model_name=_embedder.model_name,
                                embedding=emb,
                            )
                            if llm_result is not None:
                                llm_rows.append((
                                    normalized.job_uuid,
                                    llm_result.min_years_experience,
                                    {
                                        "min_years_experience": llm_result.min_years_experience,
                                        "canonical_skills": llm_result.canonical_skills,
                                        "inferred_seniority": llm_result.inferred_seniority,
                                    },
                                ))
                            embedded.append((normalized.job_uuid, emb))
                        if llm_rows:
                            store.update_llm_extracted_fields_batch(llm_rows)
                    except Exception as e:
                        for normalized, _, _ in batch:
                            print(f"Warning: Failed to generate embedding for job {normalized.job_uuid}: {e}")

                # Phase 3: Classify all new jobs (role family + seniority tier).
                # Jev role family + tier (SGSAL-022) when OPENROUTER_API_KEY is
                # set. Without a key the jobs stay unclassified and the daily
                # embed workflow's backfill_role_families.py step picks them up.
                if embedded:
                    jev = None
                    try:
                        from mcf.lib.embeddings.jev_classifier import make_jev_classifier_from_env
                        jev = make_jev_classifier_from_env()
                    except Exception as e:  # noqa: BLE001
                        print(f"Warning: Jev classifier unavailable: {e}")
                    if jev is not None:
                        try:
                            _classify_with_jev(store, jev, jobs_to_embed, embedded)
                        except Exception as e:  # noqa: BLE001
                            print(f"Warning: Jev classification failed, skipping: {e}")
                        finally:
                            jev.close()
                    else:
                        print("Role-family classification skipped (no OPENROUTER_API_KEY); "
                              "the daily embed step will classify these jobs.")

                    try:
                        store.assign_hot_jobs_scores([job_uuid for job_uuid, _ in embedded])
                    except Exception as e:
                        print(f"Warning: hot-jobs scoring failed, skipping: {e}")

        # Catch-up: score the newest active jobs that missed hot-jobs scoring
        # on a previous run (e.g. transient failure above, or a job crawled
        # as `maintained` rather than `added`). /hot-jobs only ever shows
        # recent listings, so this is recency-ordered and bounded — not a
        # full-table backfill of the historical backlog.
        try:
            stray_uuids = store.get_active_job_uuids_missing_hot_jobs_score(limit=100)
            if stray_uuids:
                store.assign_hot_jobs_scores(stray_uuids)
        except Exception as e:
            print(f"Warning: hot-jobs catch-up scoring failed, skipping: {e}")

        store.update_daily_stats(run.run_id)
        store.finish_run(
            run.run_id,
            total_seen=len(seen_set),
            added=len(added),
            maintained=len(maintained),
            removed=len(removed),
        )

        # Retention: only the current run's job_run_status rows are ever read
        # (update_daily_stats). Keep 90 days so the table stays ~600k rows
        # instead of growing ~4k rows/day forever (SGSAL-022 E5). Non-fatal.
        try:
            pruned = store.prune_job_run_status(keep_days=90)
            if pruned:
                print(f"Pruned {pruned:,} job_run_status rows older than 90 days")
        except Exception as e:  # noqa: BLE001
            print(f"Warning: job_run_status prune failed, skipping: {e}")

        # posting_groups feeds the repost badges / dashboard (SGSAL-024). Non-fatal.
        try:
            store.refresh_posting_groups()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: posting_groups refresh failed, skipping: {e}")

        # company_stats feeds /companies (SGSAL-026). Depends on posting_groups. Non-fatal.
        try:
            store.refresh_company_stats()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: company_stats refresh failed, skipping: {e}")

        # market_stats feeds the public dashboard (SGSAL-030). Depends on both views above. Non-fatal.
        try:
            store.refresh_market_stats()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: market_stats refresh failed, skipping: {e}")

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
            reposts_linked=len(repost_uuids),
        )
    finally:
        pass  # Store cleanup handled by caller

