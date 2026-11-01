---
id: SGSAL-011
project: salary-matching
title: Backend + UI — company dropdown canonicalization
status: todo
priority: low
type: feature
labels: [backend, frontend, dashboard, data-quality]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

Company names in the DB have duplicates (e.g. "Google" vs "Google Singapore" vs "Google Asia Pacific"). Canonicalize them so the company autocomplete collapses duplicates and company-tab results still work.

## Context

- Prerequisite: run `scripts/canonicalize_companies.py` to populate `company_canonical` column
- Agent: db-agent (storage methods) + frontend-agent (autocomplete)

## Acceptance Criteria

- [ ] Run `scripts/canonicalize_companies.py` to populate `company_canonical`
- [ ] Update `get_distinct_companies()` — use `DISTINCT COALESCE(company_canonical, company_name)` so duplicates collapse in autocomplete
- [ ] Update `get_active_job_uuids_by_company()` — match on `company_canonical = %s OR (company_canonical IS NULL AND company_name = %s)` so company results tab works after canonicalization
- [ ] Both DuckDB and Postgres stores updated (if DuckDB store still exists)

## Notes

- Schema already has `company_canonical` column — this is a data population + query update task, not a migration
