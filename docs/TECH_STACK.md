# Tech stack

Canonical reference for runtimes, dependencies, environment variables, and external services. See also [REPOSITORY_MAP.md](REPOSITORY_MAP.md) and [RUNTIME_FLOWS.md](RUNTIME_FLOWS.md).

---

## Runtimes and package management

| Component | Version / tool | Declared in |
|-----------|----------------|-------------|
| Python | ≥ 3.13 | [pyproject.toml](../pyproject.toml) `requires-python` |
| Node | ≥ 18 typical (Next.js 14) | Use LTS; `frontend/package.json` |
| Python deps | **uv** — `uv sync` | `pyproject.toml`, [uv.lock](../uv.lock) |
| Node deps | **npm** — `npm install` in `frontend/` | [frontend/package.json](../frontend/package.json) |
| Docker API image | pip install from **requirements.txt** | [Dockerfile.api](../Dockerfile.api) |

### `requirements.txt` vs `pyproject.toml`

[requirements.txt](../requirements.txt) is **generated** (see file header). **`Dockerfile.api` installs from `requirements.txt`**, not `pyproject.toml` directly.

After changing Python dependencies in `pyproject.toml`, regenerate:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

Then commit both files so Docker builds stay in sync.

---

## Backend (Python)

| Area | Libraries / notes |
|------|---------------------|
| HTTP API | FastAPI, Uvicorn, Starlette |
| Config | Pydantic Settings ([`src/mcf/api/config.py`](../src/mcf/api/config.py)) |
| CLI | Typer ([`src/mcf/cli/cli.py`](../src/mcf/cli/cli.py)) |
| HTTP client | httpx, tenacity (retries on MCF client) |
| Database | psycopg2-binary (Postgres), duckdb |
| Auth | PyJWT with cryptography (JWKS / HS256) |
| Embeddings | sentence-transformers; default model **BAAI/bge-small-en-v1.5** (384 dims), asymmetric query vs passage |
| Resume | pypdf, python-docx |
| CLI UX | rich |

**Embedding cold start:** The model (~130 MB) is downloaded on **first use at runtime**, not during Docker build ([Dockerfile.api](../Dockerfile.api)). First request after deploy can take **30–60 seconds**.

---

## Frontend (Node)

| Area | Libraries / notes |
|------|---------------------|
| Framework | Next.js 14 App Router, React 18 |
| Styling | Tailwind CSS 3, tailwind-merge, class-variance-authority |
| Data | axios (FastAPI), SWR, fetch |
| Auth | @supabase/supabase-js (session); **jose** for server-side JWT in Route Handlers ([`frontend/lib/jwt-verify.ts`](../frontend/lib/jwt-verify.ts)) |
| Charts | Recharts |
| Toasts | sonner |

---

## Environment variables

All application settings load from environment / `.env` via [`Settings`](../src/mcf/api/config.py) unless noted.

| Variable | Role |
|----------|------|
| `DATABASE_URL` | If set → Postgres ([`PostgresStore`](../src/mcf/lib/storage/postgres_store.py)). If unset → DuckDB at `DB_PATH`. |
| `DB_PATH` | DuckDB file path (default `data/mcf.duckdb`). |
| `SUPABASE_URL` | Supabase project URL; enables JWKS JWT verification when set (with or without legacy secret). |
| `SUPABASE_SERVICE_KEY` | Backend Storage/API; optional features when combined with URL. |
| `SUPABASE_JWT_SECRET` | Legacy HS256; omit if using JWKS only. |
| `DEFAULT_USER_ID` | Fallback user when auth disabled. |
| `RESUME_PATH` | Local resume path for CLI. |
| `ENABLE_MATCHES_CACHE` | `1` → FastAPI in-memory matches cache (when bypassing Next proxy). |
| `ENABLE_ACTIVE_JOBS_POOL_CACHE` | `1` → cache active job embedding pool in memory. |
| `ENABLE_RESPONSE_CACHE` | `1` → TTL cache for dashboard / job detail / matches on FastAPI. |
| `ENABLE_EMBEDDINGS_CACHE` | `1` (default) → content-hash embedding cache (LRU + optional DB). |
| `ADMIN_USER_IDS` | Comma-separated Supabase user UUIDs for admin routes. |
| `CRON_SECRET` / `REVALIDATE_SECRET` | Secret for `X-Crawl-Secret` on webhooks and admin fallbacks. |
| `API_PORT` | Default 8000. |
| `ALLOWED_ORIGINS` | CORS allowlist (comma-separated). |
| `ALLOW_ANONYMOUS_LOCAL` | `true` → allow unauthenticated requests to use `DEFAULT_USER_ID` (local only). |

**Frontend (Vercel / `.env.local`):** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`; for Route Handler JWT verification, `SUPABASE_JWT_SECRET` if legacy, else JWKS from public URL.

---

## External services

| Service | Usage |
|---------|--------|
| **MyCareersFuture API** | `https://api.mycareersfuture.gov.sg` — search and job detail ([`client.py`](../src/mcf/lib/api/client.py)). |
| **Careers@Gov (Algolia)** | Search index in [`cag_source.py`](../src/mcf/lib/sources/cag_source.py). Uses a **hardcoded** Algolia app id + **search-only API key** (public, same as browser). If crawl fails, key or index may have changed. |
| **Supabase** | Hosted Postgres, Auth, Storage (resumes) when deployed. |
| **Hugging Face** | Model download for sentence-transformers at runtime. |

---

## Database extensions

- **pgvector** (optional): [scripts/migrations/001_add_pgvector.sql](../scripts/migrations/001_add_pgvector.sql) — vector similarity for Postgres.
