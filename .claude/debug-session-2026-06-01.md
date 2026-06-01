# Debug Session — 2026-06-01

Production incident: CPU maxing out on Railway + Supabase 100% CPU, connection pool exhaustion, rate limiter misfiring.

---

## Issues Found & Fixed

### 1. Connection pool exhaustion — FIXED (f5ba181, bc4bba3)
**Symptom:** `psycopg2.pool.PoolError: connection pool exhausted` 500s under load.  
**Root cause:** FastAPI runs sync routes in a 40-thread threadpool. Pool was capped at 8 connections — far too small.  
**Fix:** Bumped `maxconn` 8 → 20 → 30 (Supabase Pro gives 60 direct connections).  
**File:** `src/mcf/lib/storage/postgres_store.py` lines 29-35.

### 2. Rate limiter using wrong IP — FIXED (f5ba181)
**Symptom:** All users sharing one rate limit bucket, legitimate users hitting 429.  
**Root cause:** `get_remote_address` returned Railway's internal CGNAT IP (`100.64.x.x`) for all requests.  
**Fix:** Replaced with `_get_real_ip()` reading `X-Forwarded-For` header.  
**File:** `src/mcf/api/limiter.py`.

### 3. HNSW query over-scanning — FIXED (fbb4eb7)
**Symptom:** Supabase at 100% CPU. EXPLAIN showed 913ms, nested loop estimating 134,313 rows.  
**Root cause:** JOIN with `jobs` table prevented planner from isolating the HNSW index scan. Also `ef_search` was hardcoded to 100 regardless of `limit`, so limit=500 was only exploring 100 candidates.  
**Fix:** Rewrote as subquery — HNSW scans `job_embeddings` alone first, then joins results to `jobs`. Set `ef_search = min(max(limit, 100), 500)` so it scales with limit but is capped at 500.  
**File:** `src/mcf/lib/storage/postgres_store.py` `get_all_embedded_job_ids_ranked()`.

---

## Key Findings

- **No orphaned embeddings** — `job_embeddings` has 135,778 rows, all matched to a `jobs` row. The 41-row EXPLAIN result was purely from ef_search=100 cap, not orphans.
- **BGE model is 768 dimensions** (not 384 as README states — README is wrong).
- **LLM cleaner already absent from lowball route** — CLAUDE.md listed it as issue #1, but `_cleaner.clean()` is not present in `src/mcf/api/routes/lowball.py`. Non-issue.
- **CORS 400 on dashboard endpoints** — not a code bug. `ALLOWED_ORIGINS` env var on Railway likely missing a Vercel preview URL. Check Railway env vars when dashboard preflight errors recur.
- **Middleware order note:** In `server.py`, the comment "CORSEnforcement runs first (outermost)" is wrong — `CORSMiddleware` is actually outermost (last added = outermost in Starlette).

---

## Session 2 — 2026-06-01 (post-deploy incidents)

### 6. Stale SSL connections causing 500s on lowball + company routes — FIXED (41f530e, a44cbb3)
**Symptom:** `psycopg2.OperationalError: SSL connection has been closed unexpectedly` at `register_vector(conn)` inside `_transaction_cur` and `_cur`. Affected both `/api/lowball/check` and `/api/companies`. Occurred after idle periods (burst traffic pattern).  
**Root cause:** Supabase's load balancer/NAT drops idle TCP connections server-side after ~350–600s. `ThreadedConnectionPool` holds connections open but has no health check — `getconn()` returns dead connections without detecting the SSL drop. The first operation on the dead connection (`register_vector`'s `pg_type` SELECT) raises `OperationalError`.  
**Fix (41f530e):** Added `_get_conn()` helper that calls `register_vector` as a health probe and retries once with a fresh connection on `OperationalError`, discarding the stale one with `putconn(close=True)`. Both `_cur()` and `_transaction_cur()` now go through `_get_conn()`.  
**Fix (41f530e):** Added TCP keepalives to the pool (`keepalives=1, keepalives_idle=60, keepalives_interval=10, keepalives_count=5`) so the OS sends keepalive probes every 60s, preventing NAT table entries from expiring and stale connections from forming in the first place.  
**Fix (a44cbb3):** `_get_conn()` initially introduced a new bug — fresh pool connections have `autocommit=False` by default. `register_vector`'s SELECT implicitly opened a transaction, then `_cur()`'s `conn.autocommit = True` raised `ProgrammingError: set_session cannot be used inside a transaction`. Fixed by normalising connection state in `_get_conn()`: if `autocommit=False`, rollback any pending transaction first, then set `autocommit=True`, then call `register_vector`. `_get_conn()` now always returns a connection in `autocommit=True` state. `_transaction_cur()` explicitly sets `autocommit=False` after receiving it.  
**File:** `src/mcf/lib/storage/postgres_store.py` `_get_conn()`, `_cur()`, `_transaction_cur()`, `__init__()`.

---

### 4. `get_active_jobs_pool` hitting statement timeout on cache miss — FIXED (d2214cb)
**Symptom:** `psycopg2.errors.QueryCanceled: canceling statement due to statement timeout` on `/api/lowball/check` every ~15 minutes.  
**Root cause:** The active-jobs pool cache (15-min TTL) was pre-warmed at startup with `statement_timeout = 0`, but the per-request refetch path (triggered on TTL expiry) ran inside `_transaction_cur` without disabling the timeout. Large query hitting Supabase's default statement timeout.  
**Fix:** Added `SET LOCAL statement_timeout = 0` at the top of `get_active_jobs_pool()` so both the startup warmup and TTL-expiry refetch paths are protected.  
**File:** `src/mcf/lib/storage/postgres_store.py` `get_active_jobs_pool()`.

### 5. Dirty connections leaking into pool on request cancellation — FIXED (d43abe2, b42518a)
**Symptom:** `psycopg2.ProgrammingError: set_session cannot be used inside a transaction` cascading across all routes (`/api/lowball/check`, `/api/companies`). Triggered by one bad request, then every subsequent request 500'd.  
**Root cause:** `_transaction_cur` used `except Exception` for rollback, which does not catch `asyncio.CancelledError` (a `BaseException` in Python 3.8+). When a request was cancelled (client disconnect, timeout), the rollback was skipped, and the finally block tried `conn.autocommit = True` on a connection with an open transaction — which itself raised. This meant `putconn` was never called, leaking the connection. A second fix attempt still called `putconn` after swallowing the autocommit error, returning the dirty connection to the pool.  
**Fix (d43abe2):** Changed `except Exception` → `except BaseException` so `CancelledError` triggers rollback.  
**Fix (b42518a):** In the finally block, attempt `rollback()` + `autocommit = True` restoration. If either fails, call `putconn(close=True)` to discard the connection from the pool entirely rather than returning it dirty. Pool creates a fresh connection on next `getconn`.  
**File:** `src/mcf/lib/storage/postgres_store.py` `_transaction_cur()`.

---

---

### 7. `SET LOCAL` in `_cur()` (autocommit) was a no-op — FIXED (pending push)
**Symptom:** Statement timeouts on `get_salary_distribution` and `get_all_jobs_by_company` (reported in errors.txt), plus `get_jobs_with_salary_by_uuids` fix from 9ef3739 was silently ineffective.  
**Root cause:** `SET LOCAL` only persists within an explicit PostgreSQL transaction block. `_cur()` uses `autocommit=True` — each `execute()` is its own implicit single-statement transaction. PostgreSQL treats `SET LOCAL` outside a transaction block as a no-op. So all previous `SET LOCAL` calls in `_cur()` contexts did nothing. `_transaction_cur()` (which uses `autocommit=False` + explicit BEGIN/COMMIT) is the correct context for `SET LOCAL`.  
**Fix:** Switched 6 methods from `_cur()` to `_transaction_cur()` for the slow query block. For read-only queries this adds only a negligible BEGIN/COMMIT round-trip.  
**Methods fixed:**
- `get_jobs_with_salary_by_uuids` — existing fix was broken
- `get_salary_distribution` — new timeout from errors.txt  
- `get_all_jobs_by_company` — new timeout from errors.txt  
- `get_dashboard_summary` — full JOIN scan on jobs × job_embeddings (130k+ rows), two queries  
- `get_category_stats` — MATERIALIZED CTE with JSON extraction over all active jobs  
- `get_distinct_companies` — GROUP BY + HAVING full scan  
**File:** `src/mcf/lib/storage/postgres_store.py`

---

## Still Pending

### High priority
- **Response cache on `/api/lowball/check`** — every request re-embeds + re-queries Supabase even for identical inputs. Add 10–15 min cache keyed on `(title, description_hash, salary, company_name)`, following the pattern in `src/mcf/api/cache/response.py`. This is the biggest remaining latency win. Note: caching on company name alone won't work — the description drives the similarity search, so two different roles at the same company would collide.
- ~~**`get_jobs_with_salary_by_uuids` hitting statement timeout**~~ — FIXED (properly, via `_transaction_cur()`). Earlier fix in 9ef3739 used `_cur()` so `SET LOCAL` was a no-op.

### Medium priority
- **`salary_search` makes 4 sequential DB calls per request** — `active_job_uuids()`, `get_job_uuids_with_salary_filter()`, `get_jobs_with_salary_by_uuids()` twice. Could be consolidated.
- **`salary_search` default limit=5000** — fetches all embedded jobs then filters client-side. ef_search is now capped at 500 so HNSW is fine, but the downstream DB fetch is still large.

### Infrastructure
- ~~**Railway deployment was deleted**~~ — redeployed. Current master is live.
- ~~**CORS 400 on dashboard preflight requests**~~ — FIXED. `OPTIONS /api/dashboard/*` returning 400 because `ALLOWED_ORIGINS` on Railway only had the old Vercel URL (`https://mcf-kappa.vercel.app`). Project was renamed/moved to `https://sglowball.vercel.app` but Railway env var wasn't updated. Updated `ALLOWED_ORIGINS` to `https://sglowball.vercel.app,https://mcf-kappa.vercel.app,http://localhost:3000`. Note: only requests with `Authorization` headers or JSON bodies trigger CORS preflight — plain GETs worked fine the whole time, which is why it was intermittent.

---

## Architecture reminders
- Pool is shared across all routes + embeddings cache (`src/mcf/lib/storage/postgres_store.py` lines 29-35). maxconn=50.
- Pool has TCP keepalives (idle=60s) to prevent NAT-drop stale connections. `_get_conn()` still retries once as a safety net.
- `_get_conn()` always returns a connection in `autocommit=True` state. `_transaction_cur()` flips to `autocommit=False` explicitly.
- Lowball route (`src/mcf/api/routes/lowball.py`) is a sync `def` — runs in FastAPI's 40-thread pool.
- Active-jobs pool cache (15-min TTL) warms at startup AND refetches on TTL expiry — both paths now have `statement_timeout = 0`.
- `_transaction_cur` must handle `BaseException` (not just `Exception`) because anyio uses `CancelledError` (BaseException) for task cancellation.
- Supabase Pro: 60 direct connections available. Current pool maxconn=50 leaves headroom for crawl jobs and manual queries.
