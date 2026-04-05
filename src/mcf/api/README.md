# API Layer (`src/mcf/api/`)

## Purpose

FastAPI application that exposes the REST API consumed by the Next.js frontend. Handles authentication, request routing, response caching, and delegates business logic to `services/`. Also exposes a CLI-invokable webhook endpoint for triggering crawls from GitHub Actions.

## Key Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI `app`, all route handlers, CORS config, lifespan (store + embedder init) |
| `config.py` | `Settings` class (Pydantic BaseSettings) — all env vars with defaults |
| `auth.py` | JWT verification, `get_current_user` FastAPI dependency |
| `matches_cache.py` | In-memory session cache: `user_id → [ranked_job_ids]` with TTL |
| `response_cache.py` | TTL-based cache for dashboard/job list responses (avoids repeated DB aggregations) |
| `active_jobs_pool_cache.py` | Pre-loads all active job embeddings into memory at startup (15min TTL) for fast vector search |
| `services/matching_service.py` | Core matching: cosine similarity, Rocchio expansion, recency decay |

## Dependencies

| Package | Use |
|---|---|
| `fastapi` | Framework, routing, dependency injection |
| `uvicorn` | ASGI server |
| `pydantic-settings` | Settings from env |
| `PyJWT` | JWT verification |
| `numpy` | Vector math in matching service |
| `scikit-learn` | Additional ML utilities |

## Internal Dependencies

- `mcf.lib.storage.base` — all data access via `Storage` interface
- `mcf.lib.embeddings.embedder` — BGE embedding computation
- `mcf.lib.embeddings.resume` — resume text extraction
- `mcf.lib.models` — Pydantic response models
- `mcf.lib.pipeline.incremental_crawl` — invoked by crawl webhook

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | None | Health check |
| GET | `/api/jobs/{uuid}` | None | Job detail |
| GET | `/api/matches` | Required | Paginated semantic matches |
| POST | `/api/profile/upload-resume` | Required | Upload + embed resume |
| GET | `/api/profile` | Required | User profile (embedding status, ratings) |
| POST | `/api/profile/rate` | Required | Rate a job (like/dislike/save) |
| GET | `/api/saved` | Required | Saved jobs list |
| POST | `/api/lowball/check` | None | Salary vs market check |
| GET | `/api/dashboard/summary-public` | None | Aggregate stats (cached 1h) |
| GET | `/api/dashboard/active-jobs` | None | Active job counts (cached 24h) |
| POST | `/api/admin/cache/flush` | Admin | Flush response/pool caches |
| GET | `/api/admin/cache/stats` | Admin | Cache hit/miss stats |
| POST | `/api/crawl` | Secret | Trigger crawl (from webhook) |

## Caching Strategy

Three independent caches, each toggled by an env var:

| Cache | Env Var | TTL | What it caches |
|---|---|---|---|
| `ResponseCache` | `ENABLE_RESPONSE_CACHE=1` | 1h / 24h | Dashboard JSON responses |
| `ActiveJobsPoolCache` | `ENABLE_ACTIVE_JOBS_POOL_CACHE=1` | 15min | All job embeddings (in-memory matrix) |
| `MatchesCache` | `ENABLE_MATCHES_CACHE=1` | Session | Ranked job ID lists per user |

## State Management

All mutable state is in the database (via `Storage`). The three caches above are in-process memory and are lost on restart — this is intentional (they're performance optimisations, not source of truth).

## Testing

```bash
uv run pytest tests/ -v
```

Smoke tests in `tests/test_smoke.py` test routes against a real DuckDB instance.

## Common Modifications

- **Add endpoint**: See [Adding a New FastAPI Endpoint](../../.ai/common-tasks.md#adding-a-new-fastapi-endpoint)
- **Add auth to endpoint**: See [Adding Authentication to an Endpoint](../../.ai/common-tasks.md#adding-authentication-to-an-endpoint)
- **Modify matching**: See [Modifying the Matching Algorithm](../../.ai/common-tasks.md#modifying-the-matching-algorithm)
- **Add config option**: See [Adding a New Configuration Option](../../.ai/common-tasks.md#adding-a-new-configuration-option)
