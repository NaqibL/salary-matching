---
id: SGSAL-028
project: salary-matching
title: Companies registry (SSIC) + UX v2 — recruitment-agency label, simpler companies/profile/dashboard
status: in-progress
priority: high
type: feature
labels: [companies, salary-checker, dashboard, product, ux, data-quality]
created: 2026-11-08
updated: 2026-11-08
depends_on: [SGSAL-026]
blocks: []
---

## Summary

Store each posting company's UEN and SSIC code (MCF publishes them in job detail; the crawler
parsed and discarded them). "Recruitment agency" = SSIC 78 only — never name keywords (would tag
A*STAR, MOM, e2i, TalentCorp). Tag on checker cards, companies table and profile. Companies
table simplified (Company, Openings, Hires mainly, per-family median only when a family is
chosen; agencies hidden by default). Profile: registered industry subtitle, "1 in 4 (typical 2 in
5)" reposts, repeat-postings card led by the other-company-names fact. Dashboard: four visitor
tiles; pipeline counts to admin. Checker chips become sentences ("Posted 20 times since Mar
2026", "Same ad under 3 company names", "Also posted directly by X").

Reviews that shaped it: PM agent + job-seeker agent (live-site test), 2026-11-08.
Spec: `docs/superpowers/specs/2026-11-08-ux-v2-agencies-open-roles-design.md`
Plan: `docs/superpowers/plans/2026-11-08-ux-v2-agencies-open-roles.md`

## Checklist

- [x] Migration 025 `companies` + crawler capture (batched, MCF only) + `scripts/backfill_companies.py` (running 2026-11-08 ~14:00–16:00 SGT, ~2.1 companies/s)
- [x] Migration 026 `company_stats` v2 (`is_agency`, SSIC, per-family medians) — applied 2026-11-08
- [x] Checker cards: agency tag, direct-employer chip, sentence copy
- [x] Companies table v2, profile v2
- [x] Dashboard tiles v2, admin pipeline panel
- [x] Code-review agent: 5 high / 5 medium / 7 low findings, all high+medium fixed (62f2d0c); deployed 2026-11-08 14:49 + 14:58 SGT
- [ ] Job-seeker agent re-test on production; findings addressed

## Parked

- Merge identical agency ads into one checker card ("Same ad from 4 agencies").
- Hot Jobs job-type filter.

## Notes (2026-11-08)

- Production briefly returned 500 on `/api/companies/stats` between applying migration 026
  (view column change) and the deploy (~25 min); the Vercel proxy's 15-min cache masked most of
  it. Lesson recorded in the plan: column-changing view migrations must be applied right
  before the deploy, and readers now tolerate `UndefinedColumn`.
- Registry coverage grows with the backfill; until a company has a row it is simply untagged.
  `scripts/backfill_companies.py --retry-empty` revisits rows with no identifiers.
