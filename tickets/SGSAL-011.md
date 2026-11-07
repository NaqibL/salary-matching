---
id: SGSAL-011
project: salary-matching
title: Backend + UI — company dropdown canonicalization
status: done
priority: low
type: feature
labels: [backend, frontend, dashboard, data-quality]
created: 2026-06-13
updated: 2026-11-08
---

> **Closed 2026-11-08 (status reconciliation).** Shipped in a17964d (2026-05-24): both storage
> methods already read `COALESCE(company_canonical, company_name)` / match on
> `company_canonical` + `company_aliases`, and `daily-crawl-2.yml` runs
> `canonicalize_companies.py --skip-first-pass --skip-second-pass` after every crawl so new
> rows of known companies get their canonical name. `company_aliases` holds 2,192 names
> (last LLM pass 2026-05-24); the LLM "popular filter" means only well-known employers are
> canonicalised, so `company_canonical` is NULL on ~90% of rows by design (COALESCE handles it).
> Re-run the script without the skip flags to pick up companies that became popular since May.

## Summary

Company names in the DB have duplicates (e.g. "Google" vs "Google Singapore" vs "Google Asia Pacific"). Canonicalize them so the company autocomplete collapses duplicates and company-tab results still work.

## Context

- Prerequisite: run `scripts/canonicalize_companies.py` to populate `company_canonical` column
- Agent: db-agent (storage methods) + frontend-agent (autocomplete)

## Acceptance Criteria

- [x] Run `scripts/canonicalize_companies.py` to populate `company_canonical`
- [x] Update `get_distinct_companies()` — use `DISTINCT COALESCE(company_canonical, company_name)` so duplicates collapse in autocomplete
- [x] Update `get_active_job_uuids_by_company()` — match on `company_canonical = %s OR (company_canonical IS NULL AND company_name = %s)` so company results tab works after canonicalization
- [x] Both DuckDB and Postgres stores updated (if DuckDB store still exists) — DuckDB store removed; only `PostgresStore` exists

## Notes

- Schema already has `company_canonical` column — this is a data population + query update task, not a migration
