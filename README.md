# Lowball — SG Salary Checker

Singapore salary intelligence tool. Check if a job offer is competitive, explore what companies pay, and browse market benchmarks — all sourced from live MyCareersFuture and Careers@Gov listings.

**Live at:** [lowball.sg](https://lowball.sg) (or wherever you've deployed it)

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

See [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT
