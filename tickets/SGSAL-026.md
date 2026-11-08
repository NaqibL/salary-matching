---
id: SGSAL-026
project: salary-matching
title: Companies page rework — explore by role family / industry, repost facts per company
status: in-progress
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

- [ ] Migration 024 `company_stats` (view + indexes) + `ensure_schema` copy + constant test
- [ ] Storage ABC + PostgresStore: `get_company_stats`, `get_company_stats_one`,
      `get_company_top_reposted`, `refresh_company_stats`; crawl hook after `posting_groups`
- [ ] Routes: `GET /api/companies/stats`; profile extended with `stats` + `top_reposted`
- [ ] Frontend: `/companies` filter bar + summary strip + `CompanyStatsTable` + `RoleMixBar`;
      `CompanyContent` repost tile/card + role-family and industry charts; `api.ts`/`types.ts`
- [ ] Smoke tests for the new route shapes; `tsc --noEmit` clean
- [ ] Migration applied to Supabase by hand; deploy; `/companies?family=data_ai_analytics` checked
