# Caching Strategies

The app has four stacking cache layers. Each is optional and independently toggled.

## Layer overview

```
Browser request
  └─ Next.js unstable_cache (15 min, matches; 1h, dashboard)
       └─ FastAPI response_cache (15 min matches; 1h dashboard; 24h job detail)  ← ENABLE_RESPONSE_CACHE=1
            └─ active_jobs_pool_cache (15 min, in-memory job embeddings)         ← ENABLE_ACTIVE_JOBS_POOL_CACHE=1
                 └─ matches_cache (15 min, per-user full result)                 ← ENABLE_MATCHES_CACHE=1
                      └─ embeddings_cache (indefinite LRU, content-hash)        ← ENABLE_EMBEDDINGS_CACHE=1
```

## Matches cache

`/api/matches` is the most expensive endpoint (vector similarity over ~20k jobs). Two approaches:

| Scenario | Use |
|----------|-----|
| Vercel + Next.js frontend | Next.js `unstable_cache` (default — already wired in `api.ts`) |
| FastAPI on Railway, single instance | FastAPI in-memory (`ENABLE_MATCHES_CACHE=1`) |
| Multi-instance FastAPI | Extend `matches_cache.py` with a Redis backend |

**Next.js cache** (default): cache key = `user_id + mode + params`, tag = `matches-${user_id}`. Invalidated via `POST /api/revalidate-matches` after resume update, rating, or taste compute.

**FastAPI cache** (`ENABLE_MATCHES_CACHE=1`): same TTL, in-memory per process. Invalidated internally when `mark_interaction`, `compute_taste`, or `process_resume` are called.

## Active jobs pool cache

`ENABLE_ACTIVE_JOBS_POOL_CACHE=1` — caches the full `(job_uuid, embedding, last_seen_at)` pool in-memory for 15 minutes. Avoids a DB round-trip on every match request.

Invalidation:
- TTL expiry (15 min)
- Automatic when crawl runs in-process
- Manual: `POST /api/admin/invalidate-pool` after a CLI crawl that runs in a separate process

## Dashboard cache

Dashboard routes go through Next.js route handlers (`frontend/app/api/dashboard/*/route.ts`) with 1h TTL and `dashboard-stats` tag. `ENABLE_RESPONSE_CACHE=1` adds a second layer on Railway.

The daily crawl webhook (`POST /api/webhooks/crawl-complete`) calls `revalidateTag('dashboard-stats')` to flush the Next.js cache after new jobs are ingested.

## Limits and caveats

- All FastAPI caches are **in-memory and process-local** — lost on restart, not shared across workers
- Next.js `unstable_cache` is per-serverless-instance — not shared, cleared on new deployment
- If running multiple FastAPI workers, only the instance that receives the invalidation webhook gets flushed — use Redis pub/sub or a single-instance setup to avoid stale responses
