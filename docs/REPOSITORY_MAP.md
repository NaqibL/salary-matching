# Repository map

Where code lives. Pair with [TECH_STACK.md](TECH_STACK.md) and [RUNTIME_FLOWS.md](RUNTIME_FLOWS.md).

---

## Top-level layout

| Path | Purpose |
|------|---------|
| `src/mcf/` | Python package: API, CLI, crawl, storage, embeddings |
| `frontend/` | Next.js 14 app (App Router) |
| `scripts/` | SQL schema, migrations, utilities |
| `.github/workflows/` | CI: daily crawl, backfill |

---

## Python: `src/mcf/`

### `api/`

| File | Responsibility |
|------|----------------|
| [server.py](../src/mcf/api/server.py) | FastAPI app, lifespan, all HTTP routes (~30) |
| [auth.py](../src/mcf/api/auth.py) | JWT verification (JWKS / HS256) |
| [config.py](../src/mcf/api/config.py) | `Settings` — env vars |
| [services/matching_service.py](../src/mcf/api/services/matching_service.py) | Match sessions, semantic + recency scoring, resume/taste modes |
| [matches_cache.py](../src/mcf/api/matches_cache.py) | Optional in-memory matches result cache |
| [active_jobs_pool_cache.py](../src/mcf/api/active_jobs_pool_cache.py) | Optional pool cache for `(job_uuid, embedding, last_seen_at)` |
| [response_cache.py](../src/mcf/api/response_cache.py) | Decorator TTL cache for selected endpoints |

### `lib/storage/`

| File | Responsibility |
|------|----------------|
| [base.py](../src/mcf/lib/storage/base.py) | Abstract `Storage` interface |
| [postgres_store.py](../src/mcf/lib/storage/postgres_store.py) | Postgres / Supabase; pgvector when migrated |
| [duckdb_store.py](../src/mcf/lib/storage/duckdb_store.py) | Local DuckDB; full scan for similarity |

### `lib/pipeline/` + `lib/sources/`

| File | Responsibility |
|------|----------------|
| [incremental_crawl.py](../src/mcf/lib/pipeline/incremental_crawl.py) | List → diff → fetch → embed → upsert; optional post-crawl webhook |
| [sources/base.py](../src/mcf/lib/sources/base.py) | `NormalizedJob` dataclass, `JobSource` protocol — **extension point for new sources** |
| [sources/mcf_source.py](../src/mcf/lib/sources/mcf_source.py) | MCF listing + normalization |
| [sources/cag_source.py](../src/mcf/lib/sources/cag_source.py) | CAG via Algolia + normalization |

### `lib/crawler/`, `lib/api/`, `lib/embeddings/`, `lib/models/`

| File | Responsibility |
|------|----------------|
| [crawler/crawler.py](../src/mcf/lib/crawler/crawler.py) | MCF listing pagination, `CrawlProgress` — used by `mcf_source` |
| [api/client.py](../src/mcf/lib/api/client.py) | `MCFClient` — httpx + rate limit + retry |
| [embeddings/embedder.py](../src/mcf/lib/embeddings/embedder.py) | BGE `Embedder`, query vs passage |
| [embeddings/job_text.py](../src/mcf/lib/embeddings/job_text.py) | Build passage text from `NormalizedJob` |
| [embeddings/resume.py](../src/mcf/lib/embeddings/resume.py) | PDF/DOCX/TXT extract + preprocess |
| [embeddings/embeddings_cache.py](../src/mcf/lib/embeddings/embeddings_cache.py) | Content-hash cache |
| [models/models.py](../src/mcf/lib/models/models.py), [job_detail.py](../src/mcf/lib/models/job_detail.py) | Pydantic shapes for MCF JSON |
| [categories.py](../src/mcf/lib/categories.py) | MCF category list |

### `cli/`

| File | Responsibility |
|------|----------------|
| [cli.py](../src/mcf/cli/cli.py) | Typer entrypoint: `mcf` commands |

---

## FastAPI routes (all in `server.py`)

Grouped by prefix (see OpenAPI at `/docs` when running).

| Area | Paths (representative) |
|------|------------------------|
| Jobs | `POST /api/jobs/{uuid}/interact`, `GET /api/jobs/{uuid}`, `GET /api/jobs/interested` |
| Discover | `GET /api/discover/stats` |
| Dashboard | `GET /api/dashboard/summary`, `...-public`, `active-jobs-over-time`, `jobs-by-category`, `category-trends`, `category-stats`, `jobs-by-employment-type`, `jobs-by-position-level`, `salary-distribution`, `jobs-over-time-posted-and-removed`, … |
| Profile | `GET /api/profile`, `POST /api/profile/process-resume`, `upload-resume`, `reset-ratings`, `compute-taste` |
| Matches | `GET /api/matches` |
| Admin | `POST /api/admin/invalidate-pool`, `invalidate-cache`, `GET cache-stats`, `cache-keys`, `DELETE /api/admin/cache`, `GET cache-timestamp` |
| Health | `GET /api/health`, `GET /api/cors-check` |

---

## Next.js: `frontend/app/`

### Pages

| Route | File | Purpose |
|-------|------|---------|
| `/` | [page.tsx](../frontend/app/page.tsx) | Resume / Taste match UI |
| `/dashboard` | [dashboard/page.tsx](../frontend/app/dashboard/page.tsx) | Analytics |
| `/saved` | [saved/page.tsx](../frontend/app/saved/page.tsx) | Saved jobs |
| `/job/[uuid]` | [job/[uuid]/page.tsx](../frontend/app/job/[uuid]/page.tsx) | Job detail |
| `/how-it-works` | [how-it-works/page.tsx](../frontend/app/how-it-works/page.tsx) | Help |
| `/admin` | [admin/page.tsx](../frontend/app/admin/page.tsx) | Cache admin |

### Route Handlers (`app/api/`)

Proxy or cache FastAPI; some verify JWT via [`jwt-verify.ts`](../frontend/lib/jwt-verify.ts).

| Path | Role |
|------|------|
| `GET /api/matches` | Proxy + `unstable_cache` |
| `POST /api/revalidate-matches` | Per-user tag revalidation |
| `GET /api/dashboard/summary` | Cached summary |
| `GET /api/dashboard/summary-rpc` | Optional Supabase RPC |
| `GET /api/dashboard/jobs-over-time-*` | Cached time series |
| `POST /api/webhooks/crawl-complete` | Post-crawl revalidation |
| `api/admin/*` | Cache proxies / clear |

### Client library

| File | Role |
|------|------|
| [lib/api.ts](../frontend/lib/api.ts) | Axios client to `NEXT_PUBLIC_API_URL` |
| [lib/supabase.ts](../frontend/lib/supabase.ts) | Supabase browser client |

---

## CLI (`uv run mcf <cmd>`)

| Command | Purpose |
|---------|---------|
| `crawl-incremental` | Main crawl + embed |
| `backfill-rich-fields` | Fill salary, category, etc. |
| `backfill-job-daily-stats` | Rebuild `job_daily_stats` |
| `process-resume` | Local resume → profile |
| `match-jobs` | CLI matching |
| `mark-interaction` | DuckDB only — no `--db-url` |
| `reset-ratings` | Clear ratings |
| `re-embed` | Re-embed all jobs |
| `export-to-postgres` | DuckDB → Postgres bulk |
| `db-context` | Dump schema + samples (Postgres) |

---

## Migrations (`scripts/migrations/`)

Apply in order:

| File | Contents |
|------|----------|
| `001_add_pgvector.sql` | pgvector, vector columns, HNSW |
| `002_add_match_sessions.sql` | `match_sessions` |
| `003_add_rich_job_fields.sql` | Rich columns, `job_daily_stats` |
| `004_add_embeddings_cache.sql` | `embeddings_cache` table |
| `005_dashboard_materialized_views.sql` | Materialized views |
| `006_rpc_dashboard_and_matching.sql` | RPCs + `rpc_result_cache` |
| `007_cache_metadata.sql` | `cache_metadata` |
| `008_enable_rls_public_tables.sql` | RLS on public tables |

---

## Identity and IDs

- **`job_uuid`**: For MCF, raw listing id. For other sources, `source_id:external_id` (see `NormalizedJob.job_uuid` in [base.py](../src/mcf/lib/sources/base.py)).
- **Taste embedding**: Stored in `candidate_embeddings` with `profile_id = "<profile_uuid>:taste"` (resume row uses plain `profile_id`).
