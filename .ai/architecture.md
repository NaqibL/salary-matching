# Architecture Overview

## System Overview

MCF Job Matcher is a semantic job matching platform built on Singapore's MyCareersFuture (MCF) and Careers@Gov (CAG) job listing APIs. Users upload a resume or rate jobs to build a taste profile; the system embeds both the resume/profile and live job listings into a shared vector space using a lightweight BGE model, then ranks jobs by cosine similarity. Results are served through a Next.js frontend backed by a FastAPI REST API.

The platform solves the signal-to-noise problem in job searching: instead of keyword filters, it uses dense embeddings and Rocchio-style relevance feedback so results improve the more a user interacts. A public analytics dashboard surfaces aggregate salary and hiring trends without requiring sign-in.

A background crawl pipeline (triggered daily by GitHub Actions via webhook) keeps the job database fresh. The system is designed to run cheaply in production — DuckDB for local dev, PostgreSQL (Supabase) for deployment — with a single env-var switch between them.

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | FastAPI 0.128 | Async, typed, auto-OpenAPI |
| Backend runtime | Python 3.13 + uvicorn | Modern async ASGI |
| Package manager | uv | Fast, lock-file based |
| Data validation | Pydantic v2 | Schema + settings from env |
| CLI | Typer + Rich | Crawl/embed/match scripts |
| Embeddings | SentenceTransformers (BAAI/bge-small-en-v1.5) | 384-dim, fast, asymmetric retrieval |
| ML/math | NumPy, scikit-learn, SciPy | Cosine similarity, Rocchio |
| Local DB | DuckDB 1.4 | Zero-config, columnar, fast analytics |
| Production DB | PostgreSQL via Supabase | Managed, same Storage interface |
| Auth | Supabase Auth + PyJWT | JWT-based, free tier |
| HTTP client (BE) | httpx | Async-native |
| File parsing | pypdf, python-docx | Resume extraction |
| Frontend framework | Next.js 14 (App Router) | SSR/ISR + client interactivity |
| Frontend language | TypeScript 5.5 | Type safety |
| UI primitives | shadcn/ui (Radix-based) | Accessible, unstyled base |
| Styling | Tailwind CSS 3.4 | Utility-first, dark mode |
| Data fetching | SWR 2.4 | Client-side caching + revalidation |
| API client (FE) | Axios 1.7 | Interceptors for JWT injection |
| Charts | Recharts 2.12 | Dashboard visualisations |
| Notifications | Sonner | Toast alerts |
| Hosting (BE) | Railway | Always-on, ~$5/mo |
| Hosting (FE) | Vercel | Free tier, ISR |
| Crawl orchestration | GitHub Actions (cron → webhook) | No long-running worker needed |

---

## Directory Structure

| Directory | Purpose | Key Files |
|---|---|---|
| `src/mcf/api/` | FastAPI app factory, middleware, config, auth, deps | `server.py`, `config.py`, `auth.py`, `deps.py` |
| `src/mcf/api/cache/` | In-memory caches (matches, response, job pool) | `matches.py`, `response.py`, `job_pool.py` |
| `src/mcf/api/routes/` | Route handlers split by domain | `jobs.py`, `dashboard.py`, `profile.py`, `matches.py`, `admin.py`, `lowball.py` |
| `src/mcf/matching/` | Algorithm layer — scoring, Rocchio, classifiers | `service.py`, `classifiers.py` |
| `src/mcf/cli/` | Typer CLI — crawl, embed, match scripts | `cli.py` |
| `src/mcf/lib/external/` | External API clients (MCF, CAG) | `client.py` |
| `src/mcf/lib/crawler/` | Job UUID listing with rate limiting | `crawler.py` |
| `src/mcf/lib/embeddings/` | BGE wrapper, caching, resume/job text extraction | `embedder.py`, `resume.py`, `job_text.py` |
| `src/mcf/lib/models/` | Pydantic models for MCF API responses | `models.py`, `job_detail.py` |
| `src/mcf/lib/sources/` | Job source abstractions (MCF, CAG) | `base.py`, `mcf_source.py`, `cag_source.py` |
| `src/mcf/lib/storage/` | Storage abstraction + DuckDB/Postgres impls | `base.py`, `duckdb_store.py`, `postgres_store.py` |
| `src/mcf/lib/pipeline/` | Crawl orchestration | `incremental_crawl.py` |
| `frontend/app/` | Next.js App Router pages | `page.tsx`, `layout.tsx`, `providers.tsx` |
| `frontend/app/api/` | Next.js API routes (proxy + BFF logic) | `matches/`, `dashboard/`, `lowball/`, `webhooks/` |
| `frontend/app/components/` | Shared React components | `JobCard.tsx`, `ResumeTab.tsx`, `TasteTab.tsx` |
| `frontend/lib/` | Frontend utilities, types, API client | `api.ts`, `types.ts`, `supabase.ts` |
| `frontend/components/ui/` | shadcn/ui component library | buttons, cards, dialogs, etc. |
| `tests/` | Pytest smoke tests | `test_smoke.py` |
| `docs/` | Additional docs | deployment, architecture notes |
| `scripts/` | Dev helper scripts | - |
| `data/` | DuckDB file (gitignored) | `mcf.duckdb` |
| `resume/` | Local resume file for dev | `resume.pdf` |

---

## Architecture Pattern

**Full-stack monolith with decoupled FE/BE and a dual-DB abstraction.**

```
GitHub Actions (cron)
        │ webhook
        ▼
Next.js API route (/api/webhooks/crawl)
        │ HTTP POST to Railway
        ▼
FastAPI (Railway) ──► CLI: incremental_crawl
                           │
                    ┌──────┴──────────────┐
                    │                     │
              MCF REST API          Careers@Gov
              (gov.sg)              (Algolia)
                    │
              NormalizedJob objects
                    │
              BGE embeddings
                    │
          DuckDB (dev) / PostgreSQL (prod)
                    │
        FastAPI REST endpoints (port 8000)
                    │
        Next.js App Router (Vercel)
                    │
              Browser (SWR, Axios)
```

The `Storage` abstract base class allows seamless switching between DuckDB (local, file-based) and PostgreSQL (production, Supabase) via a single `DATABASE_URL` env var. All business logic talks only to the `Storage` interface.

---

## Data Flow

### Crawl Pipeline (nightly, or manual)
1. GitHub Actions triggers cron → webhook → Vercel `/api/webhooks/crawl`
2. Vercel proxies to Railway FastAPI which spawns CLI subprocess
3. `MCFSource` / `CareersGovJobSource` list new job UUIDs (diff against DB)
4. New jobs fetched in detail, text extracted, stored in DB
5. BGE embeddings computed in batch, stored in `job_embeddings` table
6. `job_daily_stats` row inserted for dashboard trend data

### Resume Matching
1. User uploads PDF/DOCX → `/api/profile/upload-resume`
2. Backend extracts text (pypdf/python-docx), computes BGE embedding
3. Embedding stored in user profile row
4. `GET /api/matches` → `MatchingService.get_matches(user_id, mode='resume')`
5. All active job embeddings loaded (pool cache or DB), cosine distances computed
6. Recency decay applied (0.5%/day floor 0.5), interacted jobs filtered
7. Session (ranked IDs) stored in `api/cache/matches`, paginated results returned

### Taste Matching (Rocchio)
1. User rates jobs liked/disliked via `/api/profile/rate`
2. `GET /api/matches?mode=taste` → Rocchio expansion:
   `query = α·resume_emb + β·mean(liked_embs) − γ·mean(disliked_embs)`
3. Same ranking pipeline as resume mode with expanded query vector

### Salary Check (Lowball)
1. User pastes job description + salary → `POST /api/lowball/check`
2. Backend embeds description, finds cosine-similar jobs with salary data
3. Computes percentile of offered salary vs market sample
4. Returns verdict: `lowballed` / `at_median` / `insufficient_data`

### Dashboard (Public, ISR)
1. Browser hits Next.js page `/dashboard` (statically generated, ISR 1h)
2. Page fetches `/api/dashboard/summary-public`, `/api/dashboard/active-jobs`
3. FastAPI response cache (TTL 1h) serves cached aggregations from DuckDB/Postgres

---

## Entry Points

| Scenario | Entry Point | Command/URL |
|---|---|---|
| Start API server | `src/mcf/api/server.py:app` | `uv run uvicorn mcf.api.server:app --reload` |
| CLI crawl | `src/mcf/cli/cli.py:app` | `uv run mcf crawl-incremental` |
| CLI match (debug) | `src/mcf/cli/cli.py` | `uv run mcf match-jobs` |
| Frontend dev | `frontend/app/layout.tsx` | `cd frontend && npm run dev` |
| Run tests | `tests/test_smoke.py` | `uv run pytest tests/ -v` |
| Crawl webhook (prod) | `frontend/app/api/webhooks/` | `POST /api/webhooks/crawl` |
| ISR revalidation | `frontend/app/api/revalidate/` | `POST /api/revalidate` |

---

## External Integrations

| Service | Purpose | Auth |
|---|---|---|
| MyCareersFuture REST API (`api.mycareersfuture.gov.sg`) | Primary job data source | None (public) |
| Careers@Gov via Algolia | Secondary job source (govt jobs) | Public read-only API key (hardcoded) |
| Supabase Auth | User authentication (JWT) | `SUPABASE_JWT_SECRET` or JWKS |
| Supabase PostgreSQL | Production database | `DATABASE_URL` |
| Supabase Storage | Resume file storage (optional) | `SUPABASE_SERVICE_KEY` |
| Hugging Face (auto-download) | BGE model weights on first run | None |
| Railway | Backend hosting | Deployment env |
| Vercel | Frontend hosting + ISR | Deployment env |
| GitHub Actions | Daily crawl cron job | `CRON_SECRET` webhook |
