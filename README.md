# Lowball — SG Salary Checker

Singapore salary intelligence tool. Check if a job offer is competitive, explore what companies pay, and browse market benchmarks — all sourced from live MyCareersFuture and Careers@Gov listings.

**Live at:** [sglowball.vercel.app](https://sglowball.vercel.app)

---

## What it does

| Surface | Who it's for |
|---|---|
| **Salary Checker** — paste a job title + description, get a percentile rank and similar roles | Anyone |
| **Company Explorer** — browse companies, see their salary ranges, hiring patterns, and skills | Anyone |
| **Market Dashboard** — active listings, category breakdowns, salary distributions | Anyone |

Data is crawled daily from MCF and CAG, embedded with BGE, and stored in Supabase. About 20k–30k active listings at any time.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + pgvector (BGE embeddings, HNSW cosine search) |
| Frontend | Next.js 14 (App Router) |
| Database | Supabase (Postgres) |
| Hosting | Railway (API) + Vercel (frontend) |
| Crawl | GitHub Actions daily cron — MCF REST + CAG Algolia |

---

## Running locally

```bash
# 1. Install dependencies
uv sync
cd frontend && npm install && cd ..

# 2. Configure environment
cp .env.example .env
# Set DATABASE_URL to your Supabase connection string
# Set ALLOW_ANONYMOUS_LOCAL=true to skip auth

# 3. Start servers
uv run python -m uvicorn mcf.api.server:app --reload --port 8000  # terminal 1
cd frontend && npm run dev                                          # terminal 2
# Open http://localhost:3000
```

> **Windows note:** use `python -m uvicorn` / `python -m pytest`, not `uv run uvicorn` / `uv run pytest` — there's a script path bug on Windows with uv.

---

## CLI reference

```bash
# Crawl
uv run mcf crawl-incremental                          # MCF only (default)
uv run mcf crawl-incremental --source cag             # Careers@Gov only
uv run mcf crawl-incremental --source all             # both sources
uv run mcf crawl-incremental --limit 50               # test run

# Embeddings
uv run mcf re-embed                                   # batch re-embed all jobs
uv run mcf backfill-rich-fields                       # backfill LLM-extracted fields
```

For the local crawl → Supabase export workflow: [scripts/LOCAL_CRAWL_WORKFLOW.md](scripts/LOCAL_CRAWL_WORKFLOW.md)

---

## Deployment (~$5/month)

| Service | Cost | Purpose |
|---|---|---|
| Supabase | Free | Postgres, Auth, Storage |
| Railway Hobby | $5/mo | FastAPI (always-on) |
| Vercel | Free | Next.js frontend |
| GitHub Actions | Free | Daily crawl cron (10:00 SGT) |

See [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step setup.

---

## Environment variables

**Backend (Railway):**

| Var | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | Yes | Supabase Postgres connection string |
| `SUPABASE_URL` | Yes | Used for JWT/JWKS verification |
| `SUPABASE_SERVICE_KEY` | Yes | Resume storage uploads |
| `ALLOWED_ORIGINS` | Yes | CORS — comma-separated frontend URLs |
| `OPENROUTER_API_KEY` | Optional | LLM cleaning pass during embed (Gemini 2.5 Flash Lite) |
| `CAG_ALGOLIA_API_KEY` | Optional | CAG crawl (falls back to hardcoded public key) |
| `ALLOW_ANONYMOUS_LOCAL` | Dev only | Skip Supabase auth |

**Frontend (Vercel):**

| Var | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Railway API URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

---

## Development

```bash
# Add a Python dependency
uv add <package>
# Regenerate requirements.txt (used by Dockerfile.api):
uv pip compile pyproject.toml -o requirements.txt

# Run tests (requires DATABASE_URL — skipped if unset)
uv run python -m pytest tests/ -v
```

---

## Changelog

### 2026-06-02 — Salary checker polish
- **Monthly base label** — salary input and result band now explicitly labelled "Monthly Base (SGD)"
- **EP compliance filter** — malformed salary ranges (`max > 2× min`) excluded from the percentile pool
- **P50 as headline** — "Typical salary" is the primary figure; P25/P75 shown as secondary context with sample size note
- **Recruiter caveat** — note flags that posted ranges tend to run 10–20% above actual offers
- **Mobile fix** — job description text on similar-roles cards no longer overflows on small screens

### 2026-05 — Performance and reliability
- HNSW index on embeddings — cosine search is now ANN instead of a full table scan
- Binary embedding transfer via pgvector psycopg2 adapter — faster vector reads
- Active-jobs pool cache (15-min TTL, pre-stacked numpy matrix) now used by the salary checker
- SSL-resilient connection pool — stale connections detected and discarded before use; TCP keepalives enabled
- Thundering-herd guard on cache miss to prevent OOM under concurrent cold starts

### 2026-04 — Company pages and public launch
- **Companies browse page** — list all hiring companies; recruitment agencies excluded
- **Company profile page** — salary range, hiring patterns, top skills, latest openings
- **Company canonicalization** — LLM-assisted dedup merges variant spellings in autocomplete and lookup
- Removed Sign In nav link; job detail page made publicly accessible
- Open Graph meta tags + static OG screenshot for link previews
- Rebranded from "SG Salary" to **Lowball**; `/` and `/lowball` consolidated into one page

### 2026-03 — Salary checker and LLM enrichment
- Launched salary checker — paste a job title + description, get a percentile band vs. live market data
- LLM cleaning pass (Gemini 2.5 Flash Lite) extracts `min_years_experience`, inferred seniority, and canonical skills; surfaced on similar-roles cards
- Removed DuckDB — Postgres/Supabase only

---

## License

MIT
