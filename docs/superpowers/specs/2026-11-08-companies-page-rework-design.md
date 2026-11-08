# Companies page rework — explore by job type, see reposting per company

**Date:** 2026-11-08 · **Ticket:** SGSAL-026 (new) · **Depends on:** SGSAL-024 (posting groups, live)

## Problem

`/companies` is a name search plus a "Most hiring" grid of 30 names. Every one of those 30 is a
staffing agency, and the page says nothing about what a company hires for, what it pays, or how
much of its hiring is the same ad reposted. `/company/[name]` has salary, position levels and
employment types but nothing from SGSAL-024, and it aggregates every job row per company in
Python on each request (thousands of rows for an agency).

What the data now supports, all already in the database (figures from 2026-11-08, active jobs):

| Signal | Source | Coverage |
|---|---|---|
| Job type | `jobs.role_family` (24 families) | 100% |
| Industry | MCF `categories_json` (~30 labels) | 100% |
| Reposting | `posting_groups` (repost_count, distinct_companies, first/last posted) | 99% hashed |
| Salary, seniority, skills | existing columns | as today |

The repost signal is sharp at the company level: the share of a company's active postings that
belong to a reposted group runs from 15% (Randstad, HRnet) to 94–97% (Anradus, RMR, Recruit
Expert, RN Care). Some agencies have ~10% fewer distinct posting texts than live listings (the same
ad up twice at once). 5,753 posting groups span 2+ company names. Agencies post across ~all 24
families; direct employers sit in 2–3.

Size: 14,715 companies with an active job; 251 with 30+ openings; 1,009 with 10+.

## Goals

1. **Explore first.** Pick a role family and/or industry and see which companies are hiring for it,
   ranked, with openings, repost rate, median salary and a role-mix bar per row.
2. **Repost facts on the profile.** Repost rate, distinct postings vs live listings, the company's
   most-reposted postings, and whether its ads also appear under other company names.
3. **Job-type visuals.** Role-family mix per company (mini bar in the table, full chart on the
   profile) and industry mix on the profile.
4. **Backend-light.** Every page read is an indexed lookup or a scan of a ~15k-row table. No
   per-request aggregation over `jobs`. One materialised view refreshed at crawl end, the same
   pattern as `posting_groups`.

Non-goals: company deduplication beyond today's `company_canonical` coalesce (SGSAL-011 scope);
changing the existing profile endpoint's job lists; any change to the checker.

## Decisions (made 2026-11-08, delegated by Luqman)

- **Explore-first**, profile page gets the repost + role-family additions from the same table.
- **Agencies stay in the ranking.** Each row shows its repost rate and family spread as facts. A
  three-way toggle — All / Direct employers / Staffing agencies — uses `likely_agency` (below).
  Copy names the fact ("posts across 18 role families"), never the judgement ("spammer").
- **Floor:** aggregates and the ranking default to companies with ≥ 10 active openings
  (`min_active`, user-adjustable to 3 or 1). Search by name has no floor.
- **One view, `company_stats`,** refreshed right after `posting_groups` at crawl end.

## Data: `company_stats` materialised view (migration 024)

One row per company key `lower(COALESCE(company_canonical, company_name))`. Excluded aliases
(`company_aliases.is_excluded`) are filtered out. Active jobs feed every metric except the
history columns.

| Column | Definition |
|---|---|
| `company_key`, `company` | key; display name = most common `COALESCE(company_canonical, company_name)` |
| `active_count` | active jobs |
| `distinct_postings` | `count(distinct content_hash)` over active jobs (NULL hash counts as its own) |
| `reposted_count` | active jobs whose posting group has `repost_count >= 2` |
| `multi_company_count` | active jobs whose group has `distinct_companies >= 2` |
| `max_repost_count` | max `repost_count` across the company's active groups |
| `median_salary`, `salary_sample` | `percentile_cont(0.5)` of `(salary_min+salary_max)/2`, or `salary_min` when max is NULL; active jobs with a salary |
| `role_family_counts` | `jsonb` `{family_key: n}` over active jobs (`role_family` NULL → `other`) |
| `family_count` | number of distinct families with ≥ 1 active job |
| `top_family` | family with the most active jobs |
| `category_counts` | `jsonb` `{category: n}` over active jobs, `categories_json` elements |
| `total_seen` | all jobs ever (active + inactive) |
| `first_seen`, `last_seen` | `min(first_seen_at)`, `max(last_seen_at)` over all jobs |
| `likely_agency` | `family_count >= 10 OR company ~* '(recruit|manpower|staffing|employment|human resource|\\bHR\\b|talent|consultancy|outsourc)'` |

Indexes: unique on `company_key` (needed for `REFRESH … CONCURRENTLY`), btree on
`active_count DESC`. Filtering by family uses `role_family_counts ? :family` and ordering by
`(role_family_counts->>:family)::int`; at 15k rows a sequential scan is a few ms, so no GIN index.

`ensure_schema()` carries the same `CREATE MATERIALIZED VIEW IF NOT EXISTS` for fresh DBs;
`tests/test_migration_024.py` asserts the constant equals the migration text, like 022.
Production gets the migration by hand (the view populates in a few seconds).

Refresh: `Storage.refresh_company_stats()` → `REFRESH MATERIALIZED VIEW CONCURRENTLY
company_stats`, called in `incremental_crawl.py` immediately after `refresh_posting_groups()`.

## API

All routes on the existing `companies` router, cached with `cache_response(TTL_DASHBOARD)`.
Storage access only via new `Storage` ABC methods.

### `GET /api/companies/stats`

Query: `family` (role family key), `category`, `q` (name ILIKE), `agency` = `all|direct|agency`
(default `all`), `min_active` (default 10, min 1), `sort` = `openings|repost_rate|median_salary`
(default `openings`), `limit` (default 50, max 200).

Row (`CompanyStatsRow`): `company`, `active_count`, `distinct_postings`, `reposted_count`,
`multi_company_count`, `max_repost_count`, `median_salary`, `salary_sample`,
`role_family_counts`, `family_count`, `top_family`, `total_seen`, `first_seen`, `likely_agency`,
and — when `family` is set — `family_active_count` (that family's openings, which is also the sort
key for `openings` in that case).

Response: `{ rows: CompanyStatsRow[], total_matching: int, summary: { companies, openings,
median_salary } }` where `summary` aggregates the filtered set (before `limit`).

### `GET /api/companies/{name}/profile` — extended

Adds `stats: CompanyStatsRow | null` (lookup by key) and `top_reposted: CompanyReposted[]`
(≤ 5): the company's active posting groups with `repost_count >= 2`, ordered by `repost_count`
desc — `canonical_job_uuid`, `title`, `repost_count`, `reposts_365d`, `distinct_companies`,
`first_posted`, `last_posted`, `latest_salary_min/max`. Storage method
`get_company_top_reposted(company, limit)` joins `jobs` (company filter, active) to
`posting_groups` on `content_hash`; uses the SGSAL-011 company indexes.

Existing fields unchanged, so the current UI keeps working during the rollout.

## Frontend

### `/companies` (`frontend/app/companies/page.tsx`)

- **Filter bar:** role family `<select>` (display names from `role_families`, fetched once via the
  existing dashboard role-family endpoint or a static map), industry `<select>` (static list of
  MCF categories seen in `category_counts`; derived from the first stats response), name search
  (debounced → `q`), agency toggle (All / Direct employers / Agencies), min-openings toggle
  (10+ / 3+ / all). Filters live in the URL query string so views are shareable.
- **Summary strip** above the table: "N companies · M openings · median $X" for the filtered set.
- **Table** (`CompanyStatsTable.tsx`), sortable headers: Company (link to profile; "likely agency"
  pill rendered as "across 18 families" fact) · Openings (and "x distinct" when
  `distinct_postings < active_count`) · Repost rate (`reposted_count / active_count`, a small
  track bar + %) · Median salary · Role mix (`RoleMixBar.tsx`: stacked bar of top 3 families +
  other, palette from `dataviz`, tooltip lists counts) · Hiring since (`monthYear(first_seen)`).
- **Mobile:** rows collapse to a card layout (company, openings, repost %, mini bar).
- Empty state when no company meets the floor; hint to lower it.
- Keep `companiesApi.list`/`getPopular` for other callers; this page stops using them.

### `/company/[name]` (`CompanyContent.tsx`)

- Stat tiles become five: Latest openings · Total seen · Median salary · Avg min exp · **Repost
  rate** (sublabel "x of y postings reposted").
- New **Reposting** card: distinct postings vs live listings, max times one ad was posted, "also
  appears under other company names" when `multi_company_count > 0`, then the `top_reposted`
  list (title, "n× · first – last", latest range) using `monthYear`/`salaryRangeText` from
  `lib/repost.ts`.
- New **Hiring by role family** horizontal bar chart from `stats.role_family_counts` (display
  names), and **Industries** from `category_counts`, placed above the existing position-level /
  employment-type charts. Charts render only when `active_count >= 3`.

All API calls go through `frontend/lib/api.ts`; new types in `frontend/lib/types.ts`.

## Error handling

- Stats missing for a company (view not yet refreshed after a brand-new company appears): profile
  returns `stats: null`, `top_reposted: []`; UI hides the new cards.
- View absent (fresh DB before migration): `get_company_stats*` catch `UndefinedTable`, log once,
  return empty; the route returns `rows: []`.
- Refresh failure at crawl end is logged and does not fail the crawl (same as posting groups).

## Testing

- `tests/test_migration_024.py`: ensure_schema constant == migration text.
- `tests/test_smoke.py`: `/api/companies/stats` returns the response shape; a `family` filter
  returns rows whose `role_family_counts` contain that family; `min_active=1&limit=1` returns ≤ 1
  row; profile of the top company from stats includes `stats` and `top_reposted` as a list.
- Storage: invariants on a live row — `reposted_count <= active_count`,
  `distinct_postings <= active_count`, `sum(role_family_counts) == active_count`.
- Frontend: `tsc --noEmit` clean; manual check of `/companies?family=data_ai_analytics`.

## Rollout

1. Migration 024 applied by hand to Supabase (view + indexes), first refresh included.
2. Code (storage, routes, crawl hook, frontend) in one PR; smoke tests pass against the live view.
3. Deploy; the daily crawl keeps the view fresh from then on.

## Open questions deferred

- Role-family **centroid routing** (SGSAL-025 step 3) could later give each company a "nearest
  family" even without a Jev label; not needed here since active coverage is 100%.
- Whether to surface `likely_agency` as a filter on the checker's similar-roles cards (SGSAL-023
  territory). Out of scope.
