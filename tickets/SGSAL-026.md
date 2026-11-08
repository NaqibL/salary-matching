---
id: SGSAL-026
project: salary-matching
title: Companies page rework — explore by role family / industry, repost facts per company
status: done
priority: medium
type: feature
labels: [frontend, companies, reposts, product]
created: 2026-11-08
updated: 2026-11-08
depends_on: [SGSAL-024]
blocks: []
---

## Summary

`/companies` becomes a filterable ranking (role family, industry, name, agency toggle,
minimum openings) over a new `company_stats` materialised view refreshed at crawl end;
`/company/[name]` gains repost facts (rate, distinct postings vs live, most-reposted
postings, multi-company sharing) and role-family / industry charts from the same view.

Design: `docs/superpowers/specs/2026-11-08-companies-page-rework-design.md`
(decisions delegated by Luqman 2026-11-08: explore-first, agencies shown with facts +
toggle, floor of 10 openings, one view).

## Checklist

- [x] Migration 024 `company_stats` (view + indexes) + `ensure_schema` copy + constant test
- [x] Storage ABC + PostgresStore: `get_company_stats`, `get_company_stats_one`,
      `get_company_top_reposted`, `refresh_company_stats`; crawl hook after `posting_groups`
- [x] Routes: `GET /api/companies/stats`; profile extended with `stats` + `top_reposted`
- [x] Frontend: `/companies` filter bar + summary strip + `CompanyStatsTable` + `RoleMixBar`;
      `CompanyContent` repost tile/card + role-family and industry charts; `api.ts`/`types.ts`
- [x] Smoke tests for the new route shapes; `tsc --noEmit` clean
- [x] Migration applied to Supabase by hand 2026-11-08 (14,700 rows, 21 s build, 20 s concurrent refresh); local `/companies?family=data_ai_analytics`, agency toggle, `/company/RECRUIT EXPRESS PTE LTD` checked in Chrome
- [ ] Deployed to Railway + Vercel; production `/companies` checked

## Notes (2026-11-08)

- Palette: 24 families map to the dataviz reference 8-slot categorical palette by sector
  (`frontend/lib/roleFamilies.ts`), validated light + dark with `validate_palette.js`;
  colours live in `globals.css` as `--viz-1..8`.
- Known follow-ups: the profile endpoint still aggregates every job row per company in
  Python (slow cold load for the big agencies — Recruit Express is ~31k rows); "Tracked
  since" is March 2026 for almost everyone until the history grows; some search firms post
  annual figures as monthly, so the median-salary sort surfaces them (NAT AND NAT SEARCH).
