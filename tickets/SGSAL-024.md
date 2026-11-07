---
id: SGSAL-024
project: salary-matching
title: Content-addressed embeddings (one vector per posting text) + repost history per job
status: in-progress
priority: high
type: feature
labels: [storage, embeddings, data-quality, salary-checker, product, cost]
created: 2026-11-07
updated: 2026-11-08
depends_on: []
blocks: [SGSAL-025]
---

## Decision this ticket records

Luqman, 2026-11-07: **keep every job row and every expired posting forever.**
The historical view (expired jobs in the salary checker, dashboard trends) is a
core part of the product. Never prune `jobs`. Embeddings are a *derived*
artifact: they may be deduplicated, re-encoded or re-generated from
`jobs.description`, but the policy is "compress, don't forget". This supersedes
SGSAL-022 E6 (the 90-day deletion proposal is rejected).

## Problem

Measured 2026-11-07 (full history, 716k jobs since 2026-01-15):

| metric | value |
|---|---|
| jobs with an embedding | 616,208 |
| distinct `(company, description)` texts among them | 339,129 |
| vectors that are exact reposts of an already-embedded text | **277,079 (45%)** |
| `(company, normalised title)` repeats across all jobs | 343,562 (48%) |
| `job_embeddings` size (TOAST 2.5 GB + HNSW 1.9 GB) | 4.5 GB of a 7.1 GB DB |
| HNSW index vs Small-instance `shared_buffers` | 1.9 GB vs 512 MB — the index no longer fits in memory |
| new jobs per week | ≈ 21,000 |

MCF employers and agencies repost the same ad; the pipeline re-cleans it with
the LLM, re-embeds it, re-classifies it with Jev and stores another 3 KB vector
plus ~3 KB of HNSW graph every time. Nearly half of the index, the cleaner
spend, the embed time and the Jev calls go on text already processed.

Sampling (300 random duplicate-text groups, 26k random vectors) showed:

- Identical vector ⇒ identical posting in 939/952 groups; the 13 exceptions were
  the same ad with a trivial whitespace/character difference. Identical vectors
  are a safe "same posting" signal.
- Identical raw text ⇏ identical vector: the embedded text includes the title,
  LLM canonical skills, seniority and the *LLM-cleaned* description, and the
  cleaner is non-deterministic. Same-model reposts land at median cosine 0.9865
  from each other, so today the checker's top-500 is padded with near-copies
  ranked slightly apart. Deduplicating at ingest therefore *improves*
  consistency as well as saving space.
- ~1 in 4 duplicate-description groups has a different title between reposts.
  Those are legitimately different embeddings (title is in the text) and are
  left to SGSAL-023 (similarity-based near-dup handling).

## Design

Full design (backend + UI, decided 2026-11-07 with Luqman): 
`docs/superpowers/specs/2026-11-07-content-addressed-embeddings-repost-history-design.md`.
Decisions: one card per posting (latest occurrence) with a repost badge; exact
key (title + description, company excluded) for now; pointer columns on `jobs`
+ `posting_groups` materialised view refreshed at crawl end.

### 1. Content hash on every job

`jobs.content_hash TEXT` = sha256 (first 32 hex chars) of normalised **title +
description** — computed by one Python helper (`posting_key`), not in SQL.
Company is deliberately *excluded*: it is not part of the embedded text, so
agency reposts under different company names are byte-identical vectors, and
excluding it is what makes the "posted under N company names" signal possible.
`NULL` when `description` is empty (never dedup text-less rows; see the CAG
NULL-title incident in SGSAL-022). Partial index
`idx_jobs_content_hash ON jobs (content_hash) WHERE content_hash IS NOT NULL`.

### 2. One canonical job per hash owns the vector and the LLM fields

`jobs.canonical_job_uuid TEXT` — the job whose `job_embeddings` row / LLM
fields / Jev labels are shared by the group. Equal to its own `job_uuid` for
the canonical row. `job_embeddings` keeps its `job_uuid` PK (no change to the
five ANN queries' shape); it simply only contains canonical rows.

Backfill (resumable script, batches of 5k, `statement_timeout = 0`):

1. compute `content_hash` for all jobs;
2. per hash, canonical = earliest `first_seen_at` **that already has an
   embedding**, else earliest job;
3. for non-canonical jobs with `min_years_experience IS NULL` /
   `role_family IS NULL`, copy the canonical's LLM fields and Jev labels (fills
   part of the 1,012 empty-LLM gap and some of the 641k unlabelled expired
   jobs for free);
4. `DELETE FROM job_embeddings` for non-canonical jobs (≈ 230–280k rows);
5. the HNSW index does **not** shrink on delete — do not `REINDEX` here;
   SGSAL-025 step 1 builds the replacement halfvec index after this backfill
   and drops the old one, which reclaims the space in one pass. `VACUUM
   (ANALYZE) job_embeddings` afterwards reclaims TOAST.

### 3. Crawl: skip the expensive work for a repost

In `incremental_crawl.py` Phase 1 (after `upsert_new_job_detail`): compute the
hash; `store.find_canonical_for_hash(hash)` → if a canonical job with an
embedding exists, set `canonical_job_uuid`, copy `min_years_experience`,
`llm_fields_json`, `role_family/role_conf/tier_conf/predicted_tier/role_cluster`
from it, and **drop the job from `jobs_to_embed`** (no cleaner call, no embed,
no Jev call). Otherwise proceed as today and the new job becomes canonical.
`re-embed --only-unembedded` and `backfill_role_families.py` must select only
canonical jobs (`canonical_job_uuid = job_uuid OR canonical_job_uuid IS NULL`).

Expected: ≈ 35–40% fewer cleaner calls, embeds and Jev calls per crawl
(45% minus the changed-title reposts), and vector growth drops from ~21k to
~12–13k rows/week.

### 4. Repost history (product feature)

Postings are a *group* now, so keep the information the dedup would otherwise
hide — Luqman's request: "a reposted counter for a job description, and when it
was reposted … to indicate high turnover or a possible scam listing".

Materialised view `posting_groups` (refreshed at the end of each crawl, or by
`pg_cron` nightly — the extension is available on this Supabase instance):

| column | definition |
|---|---|
| `content_hash`, `canonical_job_uuid` | group key |
| `repost_count` | `count(*)` jobs in the group |
| `active_count` | `count(*) FILTER (WHERE is_active)` |
| `first_posted`, `last_posted` | `min/max(COALESCE(posted_date, first_seen_at::date))` |
| `reposts_90d`, `reposts_365d` | count of postings whose date is within the window |
| `distinct_companies` | `count(DISTINCT company_canonical/company_name)` — the same text under several company names is the agency pattern (70/869 sampled identical-vector groups) |
| `salary_history` | `jsonb_agg(json_build_object('date', …, 'min', salary_min, 'max', salary_max) ORDER BY date)` — reposts sometimes change the range; this is real information |
| `posting_dates` | `array_agg(date ORDER BY date)` for a sparkline |

API: `GET /api/jobs/{uuid}/reposts` (public, cached) plus `repost_count`,
`first_posted`, `last_posted`, `reposts_365d`, `distinct_companies` inlined on
similar-roles cards (`_build_similar_jobs`) and Hot Jobs cards.

UI (salary checker cards, `LowballContent.tsx`):

- badge **"Reposted N× since Mon YYYY"** when `repost_count ≥ 2`; tooltip with
  the posting-date sparkline and salary history.
- amber marker **"Frequently reposted"** when `reposts_365d ≥ 6` or
  `distinct_companies ≥ 3`. Copy must be neutral and factual ("posted 9 times
  in the last 12 months under 3 company names") — *not* the word "scam"; high
  repost rates also mean genuine high-volume or high-turnover hiring, and the
  site should not make a defamatory claim about a named company.
- dashboard: "Most reposted roles (12 months)" table, methodology note that
  counts are per posting group.

Thresholds are a first guess; tune after looking at the distribution of
`reposts_365d` once the view exists (history only starts 2026-01-15, so
"over the years" accrues from now).

### 5. Salary checker semantics (ties into SGSAL-023)

- ANN queries now return one hit per posting group (canonical uuid). Display
  the group's **most recent active** posting (else most recent), with the
  repost badge; `get_jobs_with_salary_by_uuids` gains a
  `representative=True` mode that resolves canonical → representative.
- Benchmark pool: one salary per group, taken from the most recent posting.
  Rationale: 20 identical reposts carry one data point, not twenty (SGSAL-023's
  over-weighting problem). The historical ranges stay visible in
  `salary_history`. State this in the dashboard methodology copy.

## Rollout

1. Migration `022_content_hash.sql` (columns + partial index, `IF NOT EXISTS`,
   also in `ensure_schema()`), Storage ABC methods: `find_canonical_for_hash`,
   `set_canonical`, `get_posting_group(s)`, `refresh_posting_groups`.
2. `scripts/backfill_content_hash.py` (resumable; prints group stats; `--dry-run`
   first, then `--apply` which also deletes non-canonical embeddings).
3. Crawl change + re-embed/Jev selection change; smoke test: a crawl over a
   known repost produces no new `job_embeddings` row and copies the fields.
4. `posting_groups` view + refresh hook at crawl end; API + cards + dashboard.
5. Then SGSAL-025 step 1 (halfvec index rebuild) to reclaim the index space.

## Acceptance

- `SELECT count(*) FROM job_embeddings e JOIN jobs j USING (job_uuid) WHERE
  j.canonical_job_uuid <> j.job_uuid` = 0.
- Every job with a non-NULL `content_hash` has `canonical_job_uuid` set and
  the canonical has an embedding (`tests/test_smoke.py`).
- Daily crawl log shows "N reposts linked, skipped cleaner/embed/Jev".
- Checker cards show the repost badge; `/api/jobs/{uuid}/reposts` returns the
  date and salary history; no company is labelled "scam" anywhere in copy.
- `job_embeddings` row count ≈ 340–400k; DB size reported in the ticket after
  the halfvec rebuild in SGSAL-025.

## Risks / notes

- Hash normalisation must be identical in Python (crawl) and SQL (backfill);
  put it in one helper and test both paths agree on a fixture.
- Reposts under a *different* title keep their own vector (correct, title is
  in the embedded text). SGSAL-023 handles near-dups.
- Deleting embeddings of non-canonical rows is lossless only if the canonical
  has an embedding of the current model; mixed-model vectors (104k
  `BAAI/bge-base`, 74k `v1`) are re-embedded in SGSAL-025 step 2, so prefer a
  `v2` row as canonical when the group has one.
- `delete_inactive_job_embeddings()` in `PostgresStore` has no callers and
  contradicts the policy above — remove it in this ticket.

## Backfill dry run (2026-11-08)

`scripts/backfill_posting_keys.py --dry-run` against Supabase. Additive only: wrote
`content_hash` / `canonical_job_uuid` on `jobs` and refreshed `posting_groups`. No vectors
deleted, no fields copied. `--apply` is pending the owner's go-ahead.

Baseline before the run (2026-11-08):

| metric | value |
|---|---|
| `job_embeddings` rows | 627,040 |
| `pg_total_relation_size('job_embeddings')` | 4521 MB |
| database size | 7087 MB |

Run output:

```
step 1: hashed 703,398 jobs in 1,271s
step 2: assigned 716,225 canonical pointers in 494s
        255,252 non-canonical jobs still hold a vector
step 5: posting_groups refreshed in 39s
stats: {'groups': 407109, 'members': 703398, 'max_repost_count': 949, 'p50_reposts_365d': 1.0, 'p95_reposts_365d': 4.0}
```

Total runtime about 33 min (01:21 to 01:54). `--apply` would delete 255,252 vectors
(627,040 -> ~371,788 rows). Then `VACUUM (ANALYZE) job_embeddings`.

## Implementation status (2026-11-08)

Code-complete on branch `sgsal-024-repost-history` (commits `1ec6d87..30fbe1e`). Not merged, not deployed, backfill `--apply` NOT run.

- `posting_key` (content hash of title + description, company excluded): done, `1ec6d87..30fbe1e`
- Migration 022 (columns, indexes, `posting_groups` view): done, applied to Supabase
- Storage methods (write / read / backfill helpers; `delete_inactive_job_embeddings` removed): done
- Crawl linking (`mcf.lib.pipeline.reposts`, skips cleaner/embed/Jev for reposts, view refresh at crawl end): done
- `scripts/backfill_posting_keys.py`: done, `--dry-run` run 2026-11-08
- API: checker one card per posting with repost facts, `/api/jobs/{uuid}/reposts`, most-reposted endpoints: done
- Frontend: types, API client, repost badge + history panel, dashboard most-reposted card: done

Selection rulings applied:
- `find_canonicals` requires the canonical to have an embedding.
- `assign_canonicals` ranks an embedded existing canonical first.
- Role-family selection is NOT restricted to canonicals, because reposts of never-labelled canonicals would otherwise stay unclassified.

### Remaining (owner)

**`--apply` must not run before this branch is deployed.** (Under master's old code an expired canonical renders as "Position closed" and the old daily embed re-embeds every active repost whose vector was deleted.)

1. Merge this branch to master and push; watch CI and the Railway deploy.
2. Re-run `uv run python scripts/backfill_posting_keys.py --dry-run` — hashes and assigns pointers for the NULL-pointer rows the old crawl added since 2026-11-08.
3. `uv run python scripts/backfill_posting_keys.py --apply --expect-max 260000` (aborts with exit 2, before any copy/delete, if more vectors would be deleted).
4. Score the hot-jobs backlog at once (reposts never inherit `above_market_pct`; it is computed from each row's own salary). Scores every active job still missing it — reposts included — in batches of 5,000:
   ```bash
   uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import os; from mcf.lib.storage.postgres_store import PostgresStore; s=PostgresStore(os.environ['DATABASE_URL']); u=s.get_active_job_uuids_missing_hot_jobs_score(limit=500000); [s.assign_hot_jobs_scores(u[i:i+5000]) for i in range(0, len(u), 5000)]; print(len(u), 'jobs scored')"
   ```
5. `VACUUM (ANALYZE) job_embeddings;`
6. Invariant queries:
   ```sql
   -- non-canonical vectors: ≈0; the remainder = members whose canonical has no vector (the delete keeps a group's only vector)
   select count(*) from job_embeddings e join jobs j using(job_uuid) where j.canonical_job_uuid <> j.job_uuid;
   -- hashed rows without pointer: must be 0
   select count(*) from jobs where content_hash is not null and canonical_job_uuid is null;
   -- active jobs whose vector owner has no vector: must be 0 (today's not-yet-embedded only, until the daily embed runs)
   select count(*) from jobs j where j.is_active
      and not exists (select 1 from job_embeddings e where e.job_uuid = coalesce(j.canonical_job_uuid, j.job_uuid));
   -- active repost rows without a hot-jobs cluster: 0 after step 4 (and trending to 0 after each crawl)
   select count(*) from jobs j where j.is_active and j.canonical_job_uuid <> j.job_uuid and j.hot_jobs_cluster is null;
   ```
7. After the next 02:00 UTC crawl: `gh run view <id> --log | grep -E "reposts linked|posting_groups"`.
8. Record post-apply `job_embeddings` row count + `pg_total_relation_size('job_embeddings')` in `tickets/SGSAL-025.md` and close this ticket.
