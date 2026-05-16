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

### Client-facing (salary checker + dashboard)

1. **Richer salary results** — expose `min_years_experience`, `inferred_seniority`, and `canonical_skills` (already in DB from LLM cleaning) on the similar-roles cards in `/lowball`. Update the jobs API response → `LowballResult`/`SimilarJob` types → `SimilarJobCard` component.

2. **Salary checker UX polish** — improve the homepage (`/`) and `/lowball` experience: clearer result state, better mobile layout, empty/error states.

3. **Dashboard improvements** — extend market analytics with seniority breakdowns and skills trend data now available from `llm_fields_json`.

### Personal use only (matching pipeline — do not expose publicly)

4. **Filters on matches page** — seniority chips, min-years range, salary slider, employment type chips. Data already in DB. Needs filter params on matching API + filter panel on `frontend/app/matches/page.tsx`.

5. **Richer job cards on matches** — experience badge, seniority tag, skill chips on `JobCard`.

6. **Experience level on candidate profile** — `target_seniority` and `years_experience` to profile DB + API + UI. Soft boost/penalty in matching pipeline.

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
