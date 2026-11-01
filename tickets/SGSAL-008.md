---
id: SGSAL-008
project: salary-matching
title: Backend + UI — filter non-compliant salary ranges + surface midpoint
status: done
priority: medium
type: feature
labels: [backend, frontend, salary-checker, data-quality]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

MCF salary ranges where `salary_max > 2 × salary_min` are non-compliant with EP rules and skew benchmarks upward. Filtering them and surfacing the midpoint of compliant ranges as the headline figure gives users a more reliable estimate.

## Context

- EP compliance rule: `salary_max <= 2 * salary_min`
- Midpoint of compliant ranges is a reliable proxy for actual hiring salary (validated against MBB postings by a recruiter)
- Estimated effort: ~1 day
- Agent: db-agent (backend) + frontend-agent (UI)

## Acceptance Criteria

- [ ] **Backend** — add `AND salary_max <= 2 * salary_min` filter to storage query that fetches salary comps (`src/mcf/lib/storage/`)
- [ ] **Frontend** — compute midpoint `(salary_min + salary_max) / 2`
- [ ] **Frontend** — surface midpoint as `"Typical salary: $X,XXX/mo"` as the headline figure
- [ ] **Frontend** — show the range as secondary context beneath the headline
- [ ] Postgres store updated (DuckDB store no longer exists — Postgres only)

## Notes

- From feedback review 2026-06-02 — confirmed as SHIP IT
- Backend change is a query filter only — no schema migration required
