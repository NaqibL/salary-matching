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

- [ ] Migration 025 `companies` + crawler capture + `scripts/backfill_companies.py` run
- [ ] Migration 026 `company_stats` v2 (`is_agency`, SSIC, per-family medians)
- [ ] Checker cards: agency tag, direct-employer chip, sentence copy
- [ ] Companies table v2, profile v2
- [ ] Dashboard tiles v2, admin pipeline panel
- [ ] Code-review agent findings addressed; deployed; job-seeker agent re-test findings addressed

## Parked

- Merge identical agency ads into one checker card ("Same ad from 4 agencies").
- Hot Jobs job-type filter.
