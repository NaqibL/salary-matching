# MCF Job Matcher — Handover

A Singapore job market crawler and matcher: pulls listings from **MyCareersFuture (MCF)** and **Careers@Gov (CAG)**, stores them in **DuckDB** (local) or **Postgres/Supabase** (hosted), embeds job text and resumes with **BGE**, and serves a **Next.js** UI for resume/taste matching and a dashboard of market stats.

It is **not** a job board — it aggregates public listings and helps a signed-in user find fits.

---

## Reading order

| Stakeholder | Start here | Then |
|-------------|------------|------|
| **New developer** | This file → [docs/TECH_STACK.md](docs/TECH_STACK.md) → [docs/REPOSITORY_MAP.md](docs/REPOSITORY_MAP.md) | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| **DevOps / deploy** | [DEPLOYMENT.md](DEPLOYMENT.md) | [docs/RUNTIME_FLOWS.md](docs/RUNTIME_FLOWS.md) |
| **AI coding agent** | [docs/INDEX.md](docs/INDEX.md), then `mcf db-context` when touching the DB | |

---

## Local development

1. Copy [`.env.example`](.env.example) to `.env` (leave `DATABASE_URL` unset for local DuckDB).
2. `uv sync` then `uv run uvicorn mcf.api.server:app --reload --port 8000`
3. `cd frontend && npm install && npm run dev`
4. Open `http://localhost:3000`

Without Supabase env vars, set `ALLOW_ANONYMOUS_LOCAL=true` in `.env`.

---

## Production shape

- **Vercel**: Next.js frontend (`frontend/`)
- **Railway**: FastAPI API ([`Dockerfile.api`](Dockerfile.api))
- **Supabase**: Postgres, Auth, Storage

Details: [DEPLOYMENT.md](DEPLOYMENT.md).

---

## Core data flow

External job APIs → **incremental crawl** (`src/mcf/lib/pipeline/incremental_crawl.py`) → **Storage** (`PostgresStore` / `DuckDBStore`) → **embeddings** (BGE) → **matching** (`MatchingService`) → **FastAPI** → browser. Dashboard and match traffic goes through **Next.js Route Handlers** that cache responses — see [docs/RUNTIME_FLOWS.md](docs/RUNTIME_FLOWS.md).

---

## Design facts new owners must know

1. **Matching is pure semantic** — cosine similarity + recency decay. Skills overlap exists in code but **weight is 0**.
2. **Caching stacks**: embeddings LRU, optional active-jobs pool cache, optional FastAPI matches/response caches, Next.js `unstable_cache`. See [docs/CACHING_STRATEGIES.md](docs/CACHING_STRATEGIES.md).
3. **Careers@Gov** uses an Algolia search key in `cag_source.py` (reads from `CAG_ALGOLIA_API_KEY` env var, falls back to hardcoded). If CAG crawl breaks, that key may have rotated.
4. **Taste embeddings**: `candidate_embeddings.profile_id` can be `<uuid>:taste` alongside the resume row for the same user.
5. **Job UUIDs**: MCF uses the raw API id; other sources prefix (e.g. `cag:...`).

---

## Operational notes

- **First API request after deploy** may take **30–60s**: the BGE model downloads at runtime.
- **GitHub Actions crawl** injects `DATABASE_URL`. Post-crawl cache invalidation also needs `CRON_SECRET` + `CRAWL_WEBHOOK_URL` secrets — see [DEPLOYMENT.md](DEPLOYMENT.md).
- **Smoke tests** run on every push/PR via `.github/workflows/lint.yml`.

---

## Full doc map

[docs/INDEX.md](docs/INDEX.md)
