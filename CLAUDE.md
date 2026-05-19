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
# Backend
uv run uvicorn mcf.api.server:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests (smoke only, real DuckDB, no mocks)
uv run pytest tests/ -v

# All CLI commands
uv run mcf <command>
```

Local dev: copy `.env.example` to `.env`. Leave `DATABASE_URL` unset for local DuckDB. Set `ALLOW_ANONYMOUS_LOCAL=true` to skip Supabase auth.

---

## Architecture boundaries — never break these

| Rule | Detail |
|---|---|
| **Storage interface** | All DB access through `Storage` ABC (`src/mcf/lib/storage/base.py`). Never import `DuckDBStore` or `PostgresStore` directly in routes. |
| **Frontend API layer** | All API calls through `frontend/lib/api.ts`. Never use `axios`/`fetch` directly in components. |
| **DB switching** | `DATABASE_URL` set → Postgres (prod). Unset → DuckDB (local). Handled automatically in server lifespan. |
| **Python deps** | `uv add <package>`. `requirements.txt` is auto-generated for Docker — do not hand-edit. |
| **Tests** | Real DuckDB in temp dirs. No mocks. No external API calls. |

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
| `OPENROUTER_API_KEY` | Optional | Enables GeminiFlashCleaner LLM pass during embed |
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
2. **Caching stacks (innermost → outermost):** embeddings LRU → active-jobs pool (15 min) → FastAPI matches cache (10 min/user) → FastAPI response cache → Next.js `unstable_cache`. Invalidate in reverse order.
3. **Taste embeddings:** stored as `candidate_embeddings.profile_id = <uuid>:taste` alongside the resume row for the same user.
4. **Job UUIDs:** MCF uses raw API id. Other sources prefix: `cag:<id>`.
5. **CAG Algolia key** in `cag_source.py` falls back to a hardcoded public key. If CAG crawl breaks, check if the key rotated.
6. **First request after deploy:** 30–60 s — BGE model downloads at runtime, not at build time.
7. **LLM cleaning:** `GeminiFlashCleaner` (Gemini 2.5 Flash Lite via OpenRouter) runs during embed when `OPENROUTER_API_KEY` is set. Extracts `min_years_experience` and `llm_fields_json` (canonical skills, inferred seniority). These are **hints only** — never override scraper-provided `position_levels`, `salary_min/max`, or `employment_types`.

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
| Supabase, Railway, Vercel, GitHub Actions | `.claude/agents/infra-agent.md` |

---

## Current roadmap (priority order)

### Performance — salary checker query latency

The `/api/lowball/check` endpoint is slow. Three root causes, in order of impact:

1. **LLM clean on every query** — `_cleaner.clean()` in `src/mcf/api/routes/lowball.py` fires a network call to OpenRouter/Gemini on every request before embedding. The LLM clean was designed for ingestion (indexing job descriptions at crawl time). For a real-time user query, embedding the raw description is sufficient. Fix: skip `_cleaner` in the lowball route entirely.

2. **No pgvector HNSW index** — `job_embeddings.embedding` has no ANN index. The `<=>` cosine query in `get_all_embedded_job_ids_ranked` does an exact KNN scan across every row. Fix: add index in Supabase — `CREATE INDEX ON job_embeddings USING hnsw (embedding vector_cosine_ops);` — then set `SET hnsw.ef_search = 100` at query time.

3. **No response cache on `/api/lowball/check`** — unlike the matches API, every lowball request re-embeds and re-queries even if the same role is checked repeatedly. Fix: add a short TTL response cache (10–15 min) keyed on `(title, description_hash, salary, company)`, following the same pattern as `src/mcf/api/cache/response.py`.

Also note: the active-jobs pool cache (15-min TTL, pre-stacked numpy matrix in `src/mcf/api/cache/job_pool.py`) is only used by the matches route. The lowball route bypasses it and hits the DB fresh every time.

### Client-facing (salary checker + dashboard)

- ~~**Richer salary results**~~ — done. `min_years_experience`, `inferred_seniority`, `canonical_skills` now surface on similar-roles cards.
- ~~**Salary checker UX polish**~~ — done. Loading context, empty state, smarter reset, mobile layout, description hint.
- ~~**Consolidate `/` and `/lowball`**~~ — done. `/` is now the full checker; `/lowball` redirects.
- **Dashboard improvements** — extend market analytics with seniority breakdowns and skills trend data now available from `llm_fields_json`.
- **Filters on similar roles** — client-side filtering of the already-fetched top-20 results by seniority, active-only, min experience, has-salary. No backend changes needed for v1.
- **Company dropdown canonicalization** — run `scripts/canonicalize_companies.py` first to populate `company_canonical`. Then update two storage methods: (1) `get_distinct_companies()` — use `DISTINCT COALESCE(company_canonical, company_name)` so duplicates collapse in the autocomplete; (2) `get_active_job_uuids_by_company()` — match on `company_canonical = %s OR (company_canonical IS NULL AND company_name = %s)` so the company results tab still works after canonicalization. Both DuckDB and Postgres stores need updating.

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
| `/schema-diff` | Surface DuckDB vs Postgres schema and implementation divergences |

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
