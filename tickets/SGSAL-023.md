---
id: SGSAL-023
project: salary-matching
title: Dedup near-identical active postings (recruiter reposts) in dashboard counts and benchmarks
status: todo
priority: medium
type: feature
labels: [data-quality, dashboard, salary-checker, product]
created: 2026-11-07
updated: 2026-11-07
depends_on: []
blocks: []
---

## Problem

Recruiters and some employers post the same role many times. Measured 2026-11-07
on active jobs (exact match on lower-cased `COALESCE(company_canonical, company_name)`
+ `title`):

| metric | value |
|---|---|
| duplicate (company, title) groups | 2,555 |
| excess active rows (beyond the first per group) | 3,751 (≈ 5% of 70k active) |
| worst offenders | RMR INTERNATIONAL PRIVATE LIMITED: "Construction Project Manager" ×26, "Business Development Manager" ×25, "Civil Construction Project Engineer" ×22; MARTINO AGENCY: "F&B Supervisor" ×17, "Marketing Manager" ×16 |

Exact-title matching is a lower bound; near-identical descriptions with slightly
different titles are not counted yet.

## Why it matters (product change, not a bug fix)

- Dashboard counts (jobs by role family / seniority / skills trend) over-weight
  spammy posters.
- Salary checker "similar roles" can show the same posting several times, and
  the benchmark percentile is pulled towards whatever that poster offers.
- Company tab results repeat.

Any fix changes published numbers, so decide the rule explicitly and note it in
the dashboard methodology copy.

## Options

1. **Query-time collapse (cheapest):** `DISTINCT ON (company, title)` keeping the
   most recent posting in the dashboard aggregates and in the similar-roles
   top-N (dedup after the ANN query, before the top-20 cut). No schema change.
2. **Crawl-time flag:** add `jobs.duplicate_of TEXT` set during the crawl when
   an active job with the same (company, normalised title) and ≥ 0.98 cosine
   description similarity exists; all public queries add `duplicate_of IS NULL`.
   Keeps the raw rows, makes the rule auditable, one-off backfill needed.
3. Also cap per-company share in benchmarks (e.g. a company contributes at most
   3 postings to a percentile) — orthogonal, protects against legitimate bulk
   hirers too.

Recommendation: start with 1 for the salary checker (user-visible repeats), then
2 once the rule is settled, so the dashboard counts and the checker agree.

## Acceptance

- Similar-roles list shows a (company, title) at most once.
- Dashboard methodology note states the dedup rule.
- Spot check: RMR INTERNATIONAL counts once per title in role-family breakdown.
