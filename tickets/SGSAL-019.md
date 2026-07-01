---
id: SGSAL-019
project: salary-matching
title: High-value listings page — surface above-market jobs
status: done
priority: medium
type: feature
labels: [frontend, backend, retention, salary-intelligence]
created: 2026-06-17
updated: 2026-07-01
---

## Summary

A curated page that surfaces active job listings paying above market rate for their peer group — updated daily with the crawl. Gives users a reason to return regularly without competing with MCF as a general job board.

## Context

- Surface: `/hot-jobs` or `/top-pay` — public-facing
- Retention mechanic: new high-value listings drop every day, creating a habit-forming "what dropped today?" use case
- Differentiator: only Lowball can do this because we have salary data on every MCF listing (FCF mandate) and embeddings to define peer groups

## Approach

### Scoring step (post-crawl batch, not per-request)

For each newly crawled job, compute an `above_market_pct` score comparing its salary against peers. Two options in order of preference:

**Option A — Coarse buckets (ship fast, 97% coverage)**
- Bucket by `categories_json` (industry) + `position_levels_json` (seniority)
- Compute median `salary_min` per bucket in a single SQL GROUP BY query
- Flag jobs where `salary_min > bucket_median * 1.20` (20% above median)
- No new infrastructure, runs as a post-crawl SQL step

**Option B — Semantic clusters (more accurate, requires backfill)**
- Use `role_cluster` (K-means on embeddings) as the peer group instead of industry buckets
- More precise — groups true role peers rather than broad industry verticals
- Blocked on backfilling `role_cluster` across all jobs (currently only 8.5% populated)
- Preferred long-term once backfill is done

Start with Option A to validate the feature, migrate to Option B once `role_cluster` is backfilled.

### Storage

- Add `above_market_pct FLOAT` column to `jobs` table
- Populated post-crawl for newly added jobs
- Null = not yet scored; negative = below market; positive = above market

### API

- New endpoint `GET /api/hot-jobs` — returns active jobs where `above_market_pct >= 20`, ordered by score desc, paginated
- Filter params: `category` (IT, Engineering, etc.), `position_level`, `limit`

### Frontend

- New page `/hot-jobs` — public-facing, no auth required
- Job cards showing: title, company, salary range, `above_market_pct` badge ("22% above market"), posting age
- Filter bar: role category, seniority level
- Listed in public nav alongside salary checker and dashboard

## Data findings (from DB investigation 2026-06-17)

- ~2,000–2,500 new jobs/day based on 63k active ÷ 28-day median tenure
- `categories_json` and `position_levels_json` have 97% coverage — viable for Option A
- `role_cluster` only 8.5% populated — Option B requires backfill first
- Job titles are too messy for regex bucketing (salary in title, all-caps, internal codes)
- `inferred_seniority` only ~33% of active jobs — not reliable enough as primary bucket key
- HNSW index not yet in place (see SGSAL-017) — Option B performance depends on this

## Acceptance Criteria

- [ ] `above_market_pct` column added to `jobs` table
- [ ] Post-crawl scoring step populates it for new jobs (Option A: bucket-based)
- [ ] `GET /api/hot-jobs` endpoint returns correctly filtered + ordered results
- [ ] `/hot-jobs` page displays job cards with above-market badge
- [ ] Filter by category and seniority works client-side
- [ ] Page linked from public nav

## Dependencies

- SGSAL-017 (HNSW index) — not a blocker for Option A, but needed before Option B
- `role_cluster` backfill — needed before Option B

## Notes

- Do not call the lowball route per job — that embeds raw text on every request. Use stored embeddings or SQL bucket median instead.
- The 30-day MCF expiry cycle means the active pool turns over roughly monthly — the page will feel meaningfully fresh week-over-week without any extra work.

## Implementation (2026-07-01)

Shipped with Option B (semantic clusters), not Option A — a fresh k=23 K-means
was fit on active-job embeddings for peer grouping instead of waiting on the
old `role_cluster` backfill.

**Important naming decision:** the existing `role_cluster` column (0–34,
`kmeans_role_v2.pkl`, used by the matching pipeline) is a *different*,
unrelated clustering system, still only ~6% backfilled at the time of this
ticket. Reusing it for hot-jobs would have silently mixed two incompatible
cluster schemes in one column. This feature uses new, separate schema
instead: `jobs.hot_jobs_cluster`, `hot_jobs_cluster_centroids`,
`hot_jobs_salary_profiles` (migration `017_add_hot_jobs.sql`).

**Data-quality guardrails added** (not in the original plan — found during
implementation): coarse k=23 clusters occasionally pair a high-comp role
(finance, leadership) with a peer-group median that doesn't reflect its true
pay band, producing 1000%+ "above market" blowouts.
- `hot_jobs_salary_profiles.viable` now also requires `salary_median >= 3500`
  (see `MIN_BASELINE_SALARY` in `scripts/seed_hot_jobs_salary_profiles.py`),
  removing Intern/near-zero-salary clusters as comparison baselines.
- `get_hot_jobs()` caps displayed/ranked `above_market_pct` at 150%
  (`HOT_JOBS_PCT_CAP` in `postgres_store.py`); the raw value stays in the DB.
- `scripts/hot_jobs_outlier_report.py` dumps jobs still exceeding the cap to
  `scripts/cluster_analysis_output/hot_jobs_outliers.csv` for future review —
  469 jobs as of the initial backfill, mostly high-comp finance/leadership
  roles the k=23 granularity can't peer-group accurately.
- Cluster labels (`hot_jobs_cluster_centroids.label`, from
  `cluster_profiles.csv` top title) are noisy for some clusters (e.g. a
  DevOps role landing in a cluster labelled "Warehouse Assistant") — the
  frontend does not display `cluster_label`; it shows `categories` +
  `inferred_seniority` instead, which come from MCF's own taxonomy / LLM
  extraction and are reliable.

**Ranking changed to recency-first (2026-07-01):** `get_hot_jobs()` now orders
by `posted_date DESC` (most recent qualifying listing first), with the capped
`above_market_pct` only as a same-day tiebreaker — was previously ordered by
score alone.

**Shipped as beta (2026-07-01, follow-up):** page title and nav link both show
a "BETA" indicator. Added a salary sanity filter to `get_hot_jobs()` —
excludes jobs where `salary_max > 2 * salary_min` (catches placeholder/junk
ranges like $9,999–$99,999 that MCF listings sometimes use; 72 active jobs
affected at time of fix).

**Frontend not visually verified in a real browser** — no browser tooling
available in this environment. Verified via: TypeScript compiles clean,
direct API curl returns correct/sane data, Next.js proxy route returns 200,
nav links present in raw HTML. Recommend a manual check of
`http://localhost:3000/hot-jobs` before considering this fully shipped.
