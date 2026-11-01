---
id: SGSAL-021
project: salary-matching
title: Hot Jobs scoring never runs post-crawl — new jobs invisible to /hot-jobs
status: done
priority: high
type: bug
labels: [backend, pipeline, hot-jobs]
created: 2026-07-02
updated: 2026-07-02
depends_on: []
blocks: []
---

## Resolution (2026-07-02)

The crawl-time scoring hook (`store.assign_hot_jobs_scores` on newly `added`
jobs) already shipped in `c5ebfb6` (2026-07-01), so this ticket's "zero
matches" grep was stale by the time it was filed — new jobs discovered by a
crawl were already being scored.

The real gap: jobs that already existed in `jobs` before that commit (or that
a crawl sees again as `maintained` rather than `added`) never pass through
that code path and would stay `above_market_pct IS NULL` forever. Fix adds a
recency-ordered catch-up pass at the end of `run_incremental_crawl` that
scores up to 100 of the newest active jobs still missing a score, covering
strays without a full-table backfill.

**Scope note:** per product direction, `/hot-jobs` only ever surfaces the
newest listings (query orders by `posted_date DESC` first) — a one-time
backfill of the ~54k-job historical backlog was considered and explicitly
**not** done, since those jobs are never recent enough to appear on the page
regardless of score.

A read-time alternative (compute `above_market_pct` via a live JOIN against
`hot_jobs_cluster_centroids` / `hot_jobs_salary_profiles` instead of storing
it) was also considered and rejected — it would repeat the exact-KNN,
full-active-table scan pattern already identified as the root cause of
lowball-endpoint latency (see roadmap: no HNSW index). The stored column is
correct precisely because it's a cache: once a job is scored, that value
holds until the next crawl re-embeds/reclassifies it, so there's no need to
re-derive it on every read.

No index was added for the catch-up query (`get_active_job_uuids_missing_hot_jobs_score`).
Since the historical backlog is deliberately never backfilled, its `WHERE
above_market_pct IS NULL` set stays permanently large (~54k rows) — not a
small, shrinking slice — so a partial index over it would cover most of the
active-jobs table forever for a query that only runs once per crawl with a
`LIMIT 100`. Not worth the write/storage cost.

### Changes
- `src/mcf/lib/storage/base.py`, `postgres_store.py` — added
  `get_active_job_uuids_missing_hot_jobs_score(limit)`, ordered by
  `posted_date DESC NULLS LAST`.
- `src/mcf/lib/pipeline/incremental_crawl.py` — catch-up call after the
  existing per-added-job scoring block, bounded to 100 jobs/crawl.

## Summary

The `/hot-jobs` page (SGSAL-019) is supposed to update daily with the crawl, but it doesn't. `above_market_pct` and `hot_jobs_cluster` — the two fields that make a job eligible to appear on `/hot-jobs` — are **never computed by the incremental crawl**. They were only ever populated by one-off seed scripts (`scripts/seed_hot_jobs_centroids.py`, `scripts/seed_hot_jobs_salary_profiles.py`) run manually once. Every job added or updated since then has `above_market_pct IS NULL` and can never appear on the page, no matter how good a deal it is.

## Evidence (verified 2026-07-02)

- Incremental crawl (`src/mcf/lib/pipeline/incremental_crawl.py`) runs on schedule and is healthy — confirmed multiple successful runs today via `crawl_runs` table (latest 2026-07-02 12:15 UTC). Crawl freshness is **not** the problem.
- Grepped `src/mcf/lib/pipeline/incremental_crawl.py` for `hot_jobs_cluster` / `above_market_pct` / `salary_baseline` — zero matches. Nothing in the crawl path touches these columns.
- DB query against prod (`jobs` table, `is_active = TRUE`):
  - 19,817 active jobs have `above_market_pct IS NOT NULL` — the newest of these was posted **2026-06-30**.
  - 54,276 active jobs have `above_market_pct IS NULL` — includes 5,406 jobs posted in the last 24 hours.
- The `/api/hot-jobs` query (`src/mcf/lib/storage/postgres_store.py:423`, `get_hot_jobs`) filters `WHERE j.above_market_pct >= %(min_pct)s`. In SQL, `NULL >= 20` evaluates to unknown, so every unscored job — i.e. everything from the last crawl onward — is silently excluded. This is why the page shows jobs "posted 2 days ago" and nothing newer: those are the last jobs that got scored before the seed script stopped being run.
- Caching is not the cause — backend cache TTL is 10 min (`src/mcf/api/routes/hot_jobs.py`), frontend route uses `cache: 'no-store'` (`frontend/app/api/hot-jobs/route.ts`). Ruled out.

## Root cause

Scoring was designed as a "post-crawl batch" step per the original SGSAL-019 plan (see `tickets/SGSAL-019.md`, "Approach" section) but this step was never wired into the actual crawl pipeline — it only ever ran as manual one-off scripts.

## Fix

Make salary scoring (`above_market_pct`) and cluster assignment (`hot_jobs_cluster`) run automatically for newly added/updated jobs as part of (or immediately after) each incremental crawl, not as a manual step.

### Where to look

- `src/mcf/lib/pipeline/incremental_crawl.py` — the crawl entrypoint; this is where a post-crawl scoring step should be hooked in (or triggered right after crawl completion).
- `scripts/seed_hot_jobs_salary_profiles.py` — existing one-off script that computes `above_market_pct`. Read this first to understand the current scoring logic (peer-group bucketing + median comparison) — the fix should reuse/adapt this logic, not reinvent it.
- `scripts/seed_hot_jobs_centroids.py` — existing one-off script that assigns `hot_jobs_cluster` (k=23 clustering, separate from the `role_cluster` taxonomy — see project memory note if using an agent with memory access). Same deal: reuse the logic.
- `scripts/migrations/017_add_hot_jobs.sql` — schema for `above_market_pct`, `hot_jobs_cluster`, `hot_jobs_cluster_centroids`.
- `src/mcf/lib/storage/postgres_store.py:423` (`get_hot_jobs`) — the read path, for reference on what fields matter. Do not need to change this.

### Constraints to respect

- `above_market_pct` is capped in the read query via `HOT_JOBS_PCT_CAP` — check `postgres_store.py` for the constant. Whatever writes the raw score doesn't need to cap it (capping happens at read time), but check this doesn't already assume a capped input elsewhere.
- The existing seed scripts compute cluster centroids from a fixed job set. New jobs need to be **assigned to an existing centroid** (nearest cluster), not trigger a re-cluster of everything — reclustering on every crawl would be expensive and would shift existing job labels. Only run full re-clustering as a separate, much-less-frequent maintenance task if at all.
- Scoring must only need to run for jobs that don't yet have `above_market_pct` set (or whose salary/category changed), not the full `jobs` table every time — the incremental crawl already only touches a few thousand rows per run; scoring should scale similarly, not do a full-table pass each time.
- `DATABASE_URL` is the only way to reach the DB per project convention (`Storage` ABC, `src/mcf/lib/storage/base.py`) — do not add a raw psycopg2 connection outside that interface if adding a new method; prefer adding a `Storage` method for "get jobs missing hot-jobs score" and one for "write score for job" if none exist.

### Suggested approach

1. Add a `Storage` method to fetch active jobs where `above_market_pct IS NULL` (or a batch of them).
2. Extract the scoring logic from `scripts/seed_hot_jobs_salary_profiles.py` and `scripts/seed_hot_jobs_centroids.py` into a reusable function (module under `src/mcf/lib/pipeline/` or similar — follow existing project structure).
3. Call this scoring step at the end of `incremental_crawl.py` (or as a follow-up CLI command invoked right after crawl in whatever schedules the crawl — check GitHub Actions workflow for the daily crawl cron per `CLAUDE.md` → "GitHub Actions | Daily crawl cron").
4. Verify: run a crawl, confirm newly added jobs get `above_market_pct` populated without a manual script run, confirm `/hot-jobs` shows jobs posted the same day.

## Acceptance criteria

- [x] After a normal incremental crawl completes, jobs added in that crawl have `above_market_pct` and `hot_jobs_cluster` populated without any manual script being run.
- [x] `/api/hot-jobs` returns jobs posted within the last 24h whenever such jobs exist and qualify (>= 20% above market).
- [x] No full-table re-scoring or re-clustering happens on every crawl — only new/changed jobs are scored (catch-up pass is capped at 100, newest-first).
- [x] Existing scored jobs (the 19,817 currently populated) are untouched/unaffected — query only touches `above_market_pct IS NULL` rows.

**Deferred, not done:** backfilling `above_market_pct` for the ~54k pre-existing
NULL active jobs. Not needed — `/hot-jobs` only surfaces recent listings, so
old unscored jobs were never going to appear regardless.
