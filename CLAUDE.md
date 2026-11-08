# SG Salary Check — Claude Guide

Singapore salary intelligence tool. Pulls listings from **MyCareersFuture (MCF)** and **Careers@Gov (CAG)**, embeds them with BGE, and serves a Next.js UI centred on salary benchmarking and market analytics.

## Product direction

| Surface | Audience | Status |
|---|---|---|
| **Salary Checker** (`/lowball`) | Public — anyone can use | Core feature, client-facing |
| **Market Dashboard** (`/dashboard`) | Public — anyone can use | Client-facing |
| **Resume Matching** (`/matches`) | Owner only (personal use) | Hidden from nav, code kept |
| **Saved Jobs** (`/saved`) | Owner only (personal use) | Hidden from nav, code kept |
| **Profile** (`/profile`) | Owner only (personal use) | Hidden from nav, code kept |

When working on the frontend, default to improving the salary checker and dashboard experience. Do not surface or promote the matching/saved/profile pages to general users.

---

## Quick start

```bash
# Backend (note: use python -m uvicorn, not uv run uvicorn — script path bug on Windows)
uv run python -m uvicorn mcf.api.server:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests (smoke only, real Postgres via DATABASE_URL, skipped if unset)
# note: use python -m pytest, not uv run pytest — same Windows script path bug
uv run python -m pytest tests/ -v

# All CLI commands
uv run mcf <command>
```

Local dev: copy `.env.example` to `.env`. Set `DATABASE_URL` to your Supabase connection string. Set `ALLOW_ANONYMOUS_LOCAL=true` to skip Supabase auth.

---

## Architecture boundaries — never break these

| Rule | Detail |
|---|---|
| **Storage interface** | All DB access through `Storage` ABC (`src/mcf/lib/storage/base.py`). Never import `PostgresStore` directly in routes. |
| **Frontend API layer** | All API calls through `frontend/lib/api.ts`. Never use `axios`/`fetch` directly in components. |
| **DB** | `DATABASE_URL` (Postgres/Supabase) is required — no DuckDB fallback. |
| **Python deps** | `uv add <package>`. `requirements.txt` is auto-generated for Docker — do not hand-edit. |
| **Tests** | Real Postgres via `DATABASE_URL`. No mocks. No external API calls. Tests skip if `DATABASE_URL` is unset. |

---

## Core data flow

```
External APIs (MCF REST / CAG Algolia)
  → incremental_crawl.py        src/mcf/lib/pipeline/
  → Storage (jobs + embeddings) src/mcf/lib/storage/
  → BGE embeddings              src/mcf/lib/embeddings/
  → MatchingService             src/mcf/matching/
  → FastAPI                     src/mcf/api/
  → Next.js Route Handlers      frontend/app/api/
  → Browser
```

---

## Production stack

| Service | Role | Cost |
|---|---|---|
| **Supabase** | Postgres, Auth (JWT/JWKS), Storage (`resumes` bucket) | Free |
| **Railway** | FastAPI via `Dockerfile.api` | $5/mo |
| **Vercel** | Next.js frontend (root dir: `frontend/`) | Free |
| **GitHub Actions** | Daily crawl cron (02:00 UTC / 10:00 SGT) | Free |

---

## Environment variables

**Backend (Railway):**

| Var | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Prod only | Supabase Postgres connection string |
| `SUPABASE_URL` | Yes | Project URL — used for JWT JWKS verification |
| `SUPABASE_SERVICE_KEY` | Yes | Service role key — used for resume storage uploads |
| `ALLOWED_ORIGINS` | Yes | CORS — comma-separated Vercel + localhost URLs |
| `SUPABASE_JWT_SECRET` | Legacy only | Skip if project uses JWT Signing Keys (new Supabase default) |
| `OPENROUTER_API_KEY` | Optional | Enables the OpenRouterCleaner LLM pass during embed |
| `OPENROUTER_MODEL` | Optional | Cleaner model slug (default `google/gemma-4-26b-a4b-it`) |
| `LLM_CLEAN_WORKERS` | Optional | Parallel LLM cleaning calls during crawl / re-embed (default 8) |
| `CAG_ALGOLIA_API_KEY` | Optional | CAG crawl — falls back to hardcoded public key if unset |
| `CRON_SECRET` | Optional | Auth for post-crawl cache invalidation webhook |
| `ALLOW_ANONYMOUS_LOCAL` | Dev only | Bypass Supabase auth for local testing |

**Frontend (Vercel):**

| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Railway API URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

**GitHub Actions secrets:** `DATABASE_URL` (required), `CRON_SECRET` + `CRAWL_WEBHOOK_URL` (optional — enables post-crawl cache invalidation).

---

## Design facts

1. **Matching is pure semantic** — cosine similarity + recency decay. Skills overlap code exists but weight is 0.
2. **Caching stacks (innermost → outermost):** embeddings LRU → active-jobs pool (24 h, `ACTIVE_JOBS_POOL_TTL_SECONDS`; one load is ~650 MB of Supabase egress, cleared by the post-crawl `invalidate-pool` call) → FastAPI matches cache (10 min/user) → FastAPI response cache → Next.js `unstable_cache`. Invalidate in reverse order.
3. **Taste embeddings:** stored as `candidate_embeddings.profile_id = <uuid>:taste` alongside the resume row for the same user.
4. **Job UUIDs:** MCF uses raw API id. Other sources prefix: `cag:<id>`.
5. **CAG Algolia key** in `cag_source.py` falls back to a hardcoded public key. If CAG crawl breaks, check if the key rotated.
6. **First request after deploy:** 30–60 s — BGE model downloads at runtime, not at build time.
7. **LLM cleaning:** `OpenRouterCleaner` (default model `google/gemma-4-26b-a4b-it`, set via `OPENROUTER_MODEL`; `GeminiFlashCleaner` is a kept alias) runs during embed when `OPENROUTER_API_KEY` is set, on a thread pool (`LLM_CLEAN_WORKERS`). Note `OPENROUTER_MODEL` is also read by the owner-only resume cleaner. Extracts `min_years_experience` and `llm_fields_json` (canonical skills, inferred seniority). These are **hints only** — never override scraper-provided `position_levels`, `salary_min/max`, or `employment_types`.
8. **Role family + seniority tier:** `JevClassifier` (`src/mcf/lib/embeddings/jev_classifier.py`, TypeSafe Jev via the OpenRouter decisions API) assigns one of 24 role families and a tier (`T1_Entry..T4_Management`) per job during the crawl. Written to `jobs.role_family` / `role_conf` / `tier_conf`; `role_cluster` now holds `role_families.id` and `predicted_tier` the Jev tier so the matches filters keep working. Role < 0.5 confidence → `other` (id 0). Backfill: `scripts/backfill_role_families.py` (resumable; also runs in `daily-embed.yml` after the embed step, so every new job is classified). Without an `OPENROUTER_API_KEY` the crawl leaves jobs unclassified for that step. The legacy KMeans/LR models were removed (SGSAL-022 C7); the candidate's tier on the matches page is the majority Jev tier of the 30 nearest active jobs (`infer_candidate_tier` in `mcf.matching.service`). `job_run_status` is pruned to 90 days at the end of each crawl.
9. **Posting groups (SGSAL-024):** `jobs.content_hash` = `posting_key(title, description)` (company excluded); `jobs.canonical_job_uuid` points at the group member that owns the `job_embeddings` row, LLM fields and Jev labels. `job_embeddings` holds canonical rows only once the backfill `--apply` has run (a hash can keep a second self-canonical when the first never had a vector); active-job vector queries gate on "some active member owns or points at the vector"; the crawl links reposts in Phase 1 (`mcf.lib.pipeline.reposts`) and skips cleaner/embed/Jev for them. `posting_groups` (materialised view, refreshed at crawl end) feeds the repost badge, `/api/jobs/{uuid}/reposts` and the dashboard's most-reposted table. The checker shows one card per posting (latest occurrence) and counts one salary per posting. Never delete `jobs` rows; vectors are derived and deduplicated, not pruned (policy decided 2026-11-07).

10. **Companies registry + stats (SGSAL-026/028):** `companies` (migration 025) stores each posting company's UEN and SSIC code, captured by the crawler from MCF job detail and backfilled by `scripts/backfill_companies.py`. **"Recruitment agency" = SSIC 78xxx, OR a recruitment-style name (recruit, staffing, headhunt, employment agency, personnel, human resource, HR, manpower) vetted by a known MCF registration that is not a public body (SSIC 72/84/85/86/91/94 excluded, 'ministry' excluded). Never a bare name keyword** — without a registration row a company stays untagged (A*STAR, MOM, e2i, universities, hospitals are never tagged). Rule lives in migration 027; `get_agency_company_keys` derives from `company_stats` so checker cards and the companies page agree. `company_stats` (materialised view, migration 027, refreshed at crawl end right after `posting_groups`) holds one row per company: openings, distinct postings, repost share, multi-company share, company-wide and per-role-family medians, `role_family_counts`, `top_family_share`, registered industry and `is_agency`. `/api/companies/stats`, the company profile and the checker's card tags read it; nothing aggregates `jobs` per request. Copy names facts, never judgements ("Posted 20 times since Mar 2026", "Same ad under 3 company names"; repost rates with context, no "spam" tags).
12. **Public dashboard reads one view (SGSAL-030):** `market_stats` (migration 028, long format `dimension/key`: total, family, poster, bucket; refreshed at crawl end after `company_stats`) feeds `/api/dashboard/market-stats-public` and every tile, the job-types table and the "Posted before" section. Nothing on the dashboard aggregates `jobs` per request. Copy: "Posted before" (never "reposts" in UI), "Median advertised monthly base", "Direct employers · Recruitment agencies · All". The per-family 4-week change is not shown: role families were only classified on active ads, so older closed ads sit in `other`.

11. **Checker cards show open roles first (SGSAL-027):** `check_lowball` ranks the 500 nearest postings, puts open ones first and fills with closed; the percentile pool stays the closest `top_k*5` historical ads by design. Response carries `open_matched`.

---

## Agent routing

Read the relevant agent file before starting work in that area:

| Task area | Agent file |
|---|---|
| Storage, schema changes, migrations | `.claude/agents/db-agent.md` |
| Embeddings, LLM cleaning, BGE pipeline | `.claude/agents/embeddings-agent.md` |
| Frontend, Next.js, components, API client | `.claude/agents/frontend-agent.md` |
| Matching, scoring, Rocchio, caching | `.claude/agents/matching-agent.md` |
| Code review before merging | `.claude/agents/code-reviewer.md` |
| Architecture decisions, scaling | `.claude/agents/design-consultant.md` |
| Supabase, Railway, Vercel, GitHub Actions config | `.claude/agents/infra-agent.md` |
| Live Railway queries (logs, metrics, variables, deployments) | `.claude/agents/railway-agent.md` |

---

## Current roadmap (priority order)

### Performance — salary checker query latency (done)

All three root causes of the slow `/api/lowball/check` endpoint are fixed:

1. **LLM clean on every query** — removed (SGSAL-004). The lowball route embeds the raw description.
2. **pgvector HNSW index** — `idx_job_embeddings_halfvec`, a halfvec(768) expression index (SGSAL-017 → SGSAL-025, migration 023); the job-side similarity queries must keep the exact `embedding::halfvec(768) <=> %s::halfvec(768)` expression or the planner stops using it. `hnsw.ef_search` is set per query in `postgres_store.py`.
3. **Response cache** — 15-min TTL cache on `/api/lowball/check` and `/api/salary/search` (commit cd7a30c), same pattern as `src/mcf/api/cache/response.py`.

Remaining known gap: the active-jobs pool cache (`src/mcf/api/cache/job_pool.py`, 24 h TTL) is only used by the matches route; the lowball route still queries the DB on a cache miss.

### Pipeline — Jev role families (SGSAL-022, in progress)

The daily embed workflow runs `scripts/backfill_role_families.py` after embedding, so every new active job gets a `role_family` / tier. Legacy KMeans/LR classifiers removed (C7). Left for Luqman: E1/E2 (prod auth var, stale secret). Decided 2026-11-07: **never prune job rows or expired postings**; vectors are deduplicated/compressed instead. SGSAL-024 is live (merged 2026-11-08, `backfill_posting_keys.py --apply` run the same day: ≈255k duplicate vectors deleted, 371,788 rows left). SGSAL-025 step 1 is done (2026-11-08): `idx_job_embeddings_halfvec` (719 MB) is the only vector index; `idx_job_embeddings_vector` is dropped — never recreate it. Remaining SGSAL-025 steps: re-embed old-model vectors with v2, role-family routed partitions, cold-tier quantisation. SGSAL-023 covers near-duplicate postings with changed titles.

### Client-facing (salary checker + dashboard)

- ~~**Richer salary results**~~ — done. `min_years_experience`, `inferred_seniority`, `canonical_skills` now surface on similar-roles cards.
- ~~**Salary checker UX polish**~~ — done. Loading context, empty state, smarter reset, mobile layout, description hint.
- ~~**Consolidate `/` and `/lowball`**~~ — done. `/` is now the full checker; `/lowball` redirects.
- ~~**Dashboard improvements**~~ — done (6082f2d). Seniority, top-skills, skills-trend and role-family analytics; skills-trend uses `idx_jobs_posted_or_seen_date` (migration 020).
- ~~**Filters on similar roles**~~ — done (16c7bb5). Client-side filters on the top-20 results.
- **Company dropdown canonicalization** — run `scripts/canonicalize_companies.py` first to populate `company_canonical`. Then update two storage methods: (1) `get_distinct_companies()` — use `DISTINCT COALESCE(company_canonical, company_name)` so duplicates collapse in the autocomplete; (2) `get_active_job_uuids_by_company()` — match on `company_canonical = %s OR (company_canonical IS NULL AND company_name = %s)` so the company results tab still works after canonicalization. Only `PostgresStore` needs updating.

### Personal use only (matching pipeline — do not expose publicly)

- **Filters on matches page** — seniority chips, min-years range, salary slider, employment type chips. Data already in DB. Needs filter params on matching API + filter panel on `frontend/app/matches/page.tsx`.
- **Richer job cards on matches** — experience badge, seniority tag, skill chips on `JobCard`.
- **Experience level on candidate profile** — `target_seniority` and `years_experience` to profile DB + API + UI. Soft boost/penalty in matching pipeline.

---

## Slash commands

| Command | What it does |
|---|---|
| `/crawl-check` | Report recent crawl run stats, job counts, source health |
| `/match-debug` | Run matcher, diagnose top results, suggest tuning |
| `/backfill-status` | Report jobs missing embeddings or LLM fields, estimate backfill time |
| `/schema-diff` | Surface schema divergences between the Storage ABC and PostgresStore implementation |

---

## Other docs

| Doc | What it covers |
|---|---|
| `DEPLOYMENT.md` | Step-by-step Supabase / Railway / Vercel / GitHub Actions setup |
| `README.md` | Public-facing overview and full CLI reference |
| `scripts/LOCAL_CRAWL_WORKFLOW.md` | Local crawl → Supabase export workflow |
| `scripts/BACKFILL_README.md` | Backfilling rich fields for existing jobs |
| `src/mcf/api/README.md` | FastAPI endpoints, caching, auth |
| `src/mcf/lib/*/README.md` | Module-level docs for embeddings, pipeline, sources, storage |
| `frontend/app/components/README.md` | Shared React components |
| `frontend/lib/README.md` | Frontend utilities, types, API client |
