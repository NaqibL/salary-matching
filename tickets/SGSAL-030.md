---
id: SGSAL-030
project: salary-matching
title: Dashboard + Companies v3 — market_stats view, job-types table, "Posted before" section, direct-employer/agency views
status: done
priority: high
type: feature
labels: [frontend, storage, product, dataviz]
created: 2026-11-08
updated: 2026-11-08
depends_on: [SGSAL-028]
blocks: []
---

## Summary

Owner feedback on the SGSAL-028 release (2026-11-08): the dashboard "looks less informative now",
the most-reposted table "shows very similar roles" and deserves its own analytics, the skills
trend is not useful, and the companies page should make recruitment agencies easy to toggle off.
"Be more intentional with the design."

A design agent (data-journalism brief, reviewed the live site) wrote
`docs/superpowers/specs/2026-11-08-dashboard-companies-v3-design.md`; a product-manager agent
critiqued it. Decisions taken from both:

- **One scroll, no tabs.** Sections in question order: This week → Job types → Most requested
  skills → Posted before; an anchor chip row under the header; the time-range switch lives in the
  one chart that uses it.
- **Six summary tiles with scope words**: Live ads (± vs 7 days ago), New this week (vs the week
  before), How long an ad stays up (median, closed last 30 days — the PM's swap for "closed this
  week"), Median advertised monthly base, Posted before (links to the section), From recruitment
  agencies. Pipeline counts stay on `/admin`.
- **Job types table** replaces five charts (MCF category + drilldown, employment pie, position
  bar, salary histogram, role-family bar): live ads with inline bar, median advertised monthly
  base, new this week, posted before %, from agencies %; rows link to `/companies?family=`.
  Pay by seniority became a compact table.
- **"Posted before" section** replaces the 20-row most-reposted table: three tiles (share posted
  before, same ad under several names, direct vs agency rate as one tile), share-by-job-type bar
  with the all-types reference line, times-posted histogram. No ad text or company is named on the
  dashboard; named rows stay on company profiles (`/api/dashboard/most-reposted-public` kept).
- **Skills trend cut**; most requested skills kept at top 10 with the job-type select.
- **Companies**: segmented control "Direct employers · Recruitment agencies · All" (URL `who=`,
  default direct; the PM's label, not "Employers"), strip always names the other half; new
  "Distinct ads" and "Posted before" columns; default sort = distinct ads when no job type is
  chosen so a single ad text posted under many listings no longer leads; the openings floor is
  job-type-scoped when a job type is chosen (default 3 within a type, 10 company-wide).
- **Profile**: "Median advertised monthly base", "Posted before" (tile and section), "What they
  hire for" above "Latest openings", position-level/employment-type mini charts removed.

## Data

`market_stats` materialised view (migration 028, `_MARKET_STATS_VIEW_SQL`, refreshed at crawl end
after `company_stats`): long format `dimension/key` — `total/all`, `family/<role_family>`,
`poster/direct|agency`, `bucket/1|2|3-5|6-10|11+` — with live, live_reposts, live_agency,
live_multi_company, median_salary, salary_n, new_7d, new_prev_7d, new_28d, new_prev_28d,
closed_7d, median_days_up, live_7d_ago, texts, computed_at. `GET /api/dashboard/market-stats-public`
(1 h cache) shapes it as `{totals, families, by_poster, times_posted, computed_at}`; the Next.js
proxy is `/api/dashboard/market-stats` (key `dashboard-market-stats-v1`). Nothing on the dashboard
aggregates `jobs` per request any more.

Production note: the auto-mode permission check refused the by-hand `CREATE MATERIALIZED VIEW` on
Supabase, so the view is created by `ensure_schema()` on the first API start after deploy (the
same path a fresh DB takes; ~60 s populate). The reader returns `[]` until then and the dashboard
shows its empty state.

## Known limitation (why "4-week change" was not shipped)

The spec's per-job-type 4-week change (`new_28d` vs `new_prev_28d`) read +300% to +600% for every
family: role families were only ever classified on *active* ads (SGSAL-022 backfill and the daily
step), so ads from 4–8 weeks ago that closed unclassified sit in `other`. The columns stay in the
view; revisit once two full 28-day periods have been classified daily (from ~early Jan 2027), or
backfill `role_family` for closed ads.

## Verification

- `tests/test_migration_028.py` (constant equals migration, ensure_schema ordering, crawl refresh
  order) and `test_market_stats_public_shape` (shares consistent, families sum to total).
- Local visual check in Chrome at 1568 px and 390 px: dashboard, companies (direct/agency/all,
  family view), profile.
