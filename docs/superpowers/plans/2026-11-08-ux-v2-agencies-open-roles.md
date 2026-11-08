# UX v2 Implementation Plan — open roles first, agency labelling, simpler companies and dashboard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Checker cards show open roles first; companies get an official "Recruitment agency" label from SSIC; companies table, profile, checker chips and dashboard tiles are simplified to plain-language facts.

**Architecture:** A `companies` registry table filled by the crawler (SSIC from MCF job detail) and a one-off backfill; `company_stats` v2 derives `is_agency` and per-family medians from it; the lowball route widens its candidate pool to prefer open postings and annotates cards with agency / direct-employer facts; frontend copy and layout follow the spec.

**Tech Stack:** Postgres 17 (Supabase), psycopg2, FastAPI/pydantic, Next.js app router, SWR, Recharts, Tailwind.

**Spec:** `docs/superpowers/specs/2026-11-08-ux-v2-agencies-open-roles-design.md`

## Global Constraints

- Storage only via the `Storage` ABC; frontend API calls only via `frontend/lib/api.ts`.
- Tests against real Postgres with `.env` loaded: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main([...]))"`.
- `ensure_schema` constants byte-identical to migrations (tests enforce).
- Agency tag from SSIC 78 only. No name keywords anywhere in code.
- Copy per spec. Commit per task, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Work on branch `ux-v2-agencies`; merge to master only after the code-review agent's findings are addressed and the full suite + `tsc` pass.

---

### Task 1: Checker open-first (SGSAL-027)

**Files:** `src/mcf/api/routes/lowball.py` (`check_lowball`, `LowballResult`), `frontend/app/lowball/LowballContent.tsx`, `frontend/lib/types.ts` (`LowballResult.open_matched?`), `tests/test_smoke.py`.

- [ ] Smoke test: POST a Data Analyst description; assert `open_matched` in response; if `open_matched > 0` the first similar job has `is_active == True` or `active_count > 0`; `len(similar_jobs) <= top_k`.
- [ ] Route: `uuid_to_score_all` over all 500 hits; `jobs_all = get_jobs_with_salary_by_uuids(all uuids, representative=True)` → dedup/sort; `open = [j for j in jobs_all if j.get("is_active") or _int_or(j.get("active_count"), 0) > 0]`; `closed` = rest; cards from `open[:top_k] + closed[:top_k-len(open[:top_k])]`; percentile pool unchanged (top `top_k*5`). `LowballResult.open_matched: int | None = None`.
- [ ] Frontend: headline "{n} closest ads · {open} open now · {listings} listings including reposts"; benchmark line "based on {salary_coverage} ads posted since Mar 2026"; badge "{pct}% match" + title tooltip.
- [ ] Run smoke subset; `tsc`; commit `feat(SGSAL-027): checker cards show open roles first`.

### Task 2: `companies` registry — migration 025, model, crawler, storage, backfill

**Files:** `scripts/migrations/025_companies.sql`, `src/mcf/lib/storage/postgres_store.py` (`_COMPANIES_DDL`, ensure_schema, `upsert_company`, `get_companies_missing_registry`, `get_agency_company_keys`), `src/mcf/lib/storage/base.py`, `src/mcf/lib/sources/base.py` (`NormalizedJob` fields), `src/mcf/lib/sources/mcf_source.py`, `src/mcf/lib/pipeline/incremental_crawl.py`, `scripts/backfill_companies.py`, `tests/test_migration_025.py`, `tests/test_company_registry.py`.

- [ ] Migration: `CREATE TABLE IF NOT EXISTS companies (company_key TEXT PRIMARY KEY, name TEXT NOT NULL, uen TEXT, ssic_code TEXT, ssic_code_2020 TEXT, ssic_description TEXT, employee_count INTEGER, source TEXT NOT NULL DEFAULT 'mcf', fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()); CREATE INDEX IF NOT EXISTS idx_companies_uen ON companies (uen);` Constant test like 024.
- [ ] `NormalizedJob`: five optional company fields; `_mcf_raw_to_normalized` fills from `postedCompany` dict (`uen`, `ssicCode`, `ssicCode2020`, `ssicDescription2020`, `employeeCount`).
- [ ] Storage: `upsert_company(*, name, uen=None, ssic_code=None, ssic_code_2020=None, ssic_description=None, employee_count=None, source="mcf")` — `INSERT ... ON CONFLICT (company_key) DO UPDATE SET` non-null fields, `fetched_at = now()`. `get_companies_missing_registry(limit=20000) -> list[tuple[str, str]]` (distinct lower(company_name) with an active MCF job and no row, with one job_uuid). `get_agency_company_keys() -> set[str]`.
- [ ] Crawl hook after `upsert_new_job_detail`: `if normalized.company_name: store.upsert_company(name=..., uen=normalized.company_uen, ..., source=normalized.source_id)` wrapped in try/except (non-fatal).
- [ ] Backfill script: args `--limit`, `--min-active` (default 1), `--rps` (default 4); loop missing → GET `https://api.mycareersfuture.gov.sg/v2/jobs/{uuid}` → `postedCompany` → `upsert_company`; progress every 200; final counts. Apply migration 025 to Supabase, start the backfill in the background (log to scratchpad).
- [ ] Tests: registry round-trip on a `test:` key (insert, read via `get_agency_company_keys` after setting ssic 78104, cleanup). Commit `feat(SGSAL-028): companies registry (migration 025), crawler capture, backfill script`.

### Task 3: `company_stats` v2 — migration 026, storage, API

**Files:** `scripts/migrations/026_company_stats_v2.sql`, `postgres_store.py` (`_COMPANY_STATS_VIEW_SQL`, `get_company_stats`, `get_company_stats_one`, `get_company_benchmarks`, `get_posting_group_companies`, `get_dashboard_summary`), `base.py`, `src/mcf/api/routes/companies.py`, `tests/test_migration_024.py` → point at 026, `tests/test_company_stats.py`, `tests/test_smoke.py`.

- [ ] Migration 026: `DROP MATERIALIZED VIEW IF EXISTS company_stats;` then the v2 view per spec (join `companies`, `is_agency`, `ssic_code_2020`, `ssic_description`, `top_family_share`, `family_medians`, `family_salary_n`; no `likely_agency`) + the two indexes. Constant test START/END unchanged.
- [ ] Storage: columns list updated; `agency` filter on `is_agency`; with `family`: `(family_medians->>%(family)s)::int AS family_median_salary, (family_salary_n->>%(family)s)::int AS family_salary_sample`; `get_company_benchmarks()`; `get_posting_group_companies(uuids)`; summary adds `companies_hiring`, `new_this_week`.
- [ ] API: `CompanyStatsRow` gains `is_agency`, `ssic_code_2020`, `ssic_description`, `top_family_share`, `family_median_salary`, `family_salary_sample`; drops `likely_agency`. Profile adds `benchmarks: {median_repost_rate: float | None}`.
- [ ] Apply 026 to Supabase (after the backfill has made progress; re-refresh later). Tests updated/passing. Commit `feat(SGSAL-028): company_stats v2 — SSIC agency flag, per-family medians, benchmarks`.

### Task 4: Checker chips — agency tag, direct employer, sentence copy

**Files:** `lowball.py` (`_build_similar_jobs` gains `agency_keys`, `direct_by_canonical`), `frontend/lib/types.ts` (`SimilarJob.is_agency?`, `direct_employer?`), `frontend/lib/repost.ts` (`repostLabel`), `frontend/app/lowball/RepostBadge.tsx`, `LowballContent.tsx` (chips), `frontend/app/dashboard/MostRepostedTable.tsx` copy.

- [ ] Route: load agency keys (module-level 1h cache); for cards with `distinct_companies >= 2`, `get_posting_group_companies` → `direct_employer`.
- [ ] Copy per spec; `AgencyTag` component in `frontend/app/components/AgencyTag.tsx` (reused by companies table and profile).
- [ ] Smoke test asserts `is_agency` key present on cards. `tsc`. Commit `feat(SGSAL-028): checker cards — recruitment-agency tag, direct-employer chip, plain-language repost chips`.

### Task 5: Companies table v2 and profile v2

**Files:** `frontend/app/companies/page.tsx`, `CompanyStatsTable.tsx`, delete `RoleMixBar.tsx`, `frontend/app/company/[name]/CompanyContent.tsx`, `frontend/lib/api.ts` (params `agencies`), `frontend/lib/types.ts`.

- [ ] Table columns/filters per spec; agencies hidden by default (`agency=direct` unless `agencies=show`); summary strip with hidden count (needs `total_agencies_hidden`: compute as a second stats call with `agency=agency&limit=1` → `total_matching`).
- [ ] Profile per spec. `tsc`. Commit `feat(SGSAL-028): companies table and profile v2`.

### Task 6: Dashboard tiles, admin pipeline panel

**Files:** `frontend/app/dashboard/DashboardSummary.tsx`, `frontend/app/admin/PipelinePanel.tsx` (new), `frontend/app/admin/page.tsx`.

- [ ] Four public tiles; pipeline panel on admin. `tsc`. Commit `feat(SGSAL-028): dashboard tiles for visitors; pipeline health on admin`.

### Task 7: Docs, review, ship, verify

- [ ] CLAUDE.md design fact 10 updated (registry + SSIC rule), API README rows, tickets SGSAL-027/028, TICKETS.md.
- [ ] Full suite + `tsc`. Dispatch the **code-reviewer** agent on `git diff master...ux-v2-agencies`; fix findings.
- [ ] Merge to master (ff), push, watch Railway + Vercel, verify `/api/lowball/check` first card open, `/api/companies/stats` has `is_agency`.
- [ ] Dispatch the **job-seeker** agent with the same Part-1 tasks as the first review; fix what it finds; final docs commit.
