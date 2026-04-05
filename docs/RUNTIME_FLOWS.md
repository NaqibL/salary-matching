# Runtime flows

How requests, auth, caching, and background hooks fit together. See [TECH_STACK.md](TECH_STACK.md) for env vars.

---

## 1. Authentication (two independent layers)

The browser holds a **Supabase session JWT**. It is sent as `Authorization: Bearer <token>` to:

1. **Next.js Route Handlers** (`frontend/app/api/**`) — verified with **jose** + JWKS (or HS256 if `SUPABASE_JWT_SECRET` is set) in [`jwt-verify.ts`](../frontend/lib/jwt-verify.ts). Used for `/api/matches`, `/api/revalidate-matches`, and other server routes that must know `user_id` before calling upstream.

2. **FastAPI** — verified with **PyJWT** + JWKS/HS256 in [`auth.py`](../src/mcf/api/auth.py) for every `/api/*` route that uses `Depends(get_current_user)`.

**Implication:** Misconfiguration can surface as **401 from Next.js** (before FastAPI) or **401 from FastAPI**. Check both environments: Vercel env for `NEXT_PUBLIC_SUPABASE_URL` and optional `SUPABASE_JWT_SECRET`; Railway env for `SUPABASE_URL` (JWKS) or legacy secret.

Anonymous local dev: `ALLOW_ANONYMOUS_LOCAL=true` and/or no Supabase config — see [config.py](../src/mcf/api/config.py).

---

## 2. Matches request path

Typical production path when the frontend uses the Next proxy ([`matches` route handler](../frontend/app/api/matches/route.ts)):

1. User → `matchesApi.getMatches()` in [`api.ts`](../frontend/lib/api.ts) → `fetch('/api/matches?...')` (same origin).
2. Next.js `GET /api/matches` → validates JWT → **`unstable_cache`** (15 min, per-user tag).
3. On miss → `GET {NEXT_PUBLIC_API_URL}/api/matches?...` with same `Authorization` header.
4. FastAPI [`get_matches`](../src/mcf/api/server.py) → optional FastAPI [`matches_cache`](../src/mcf/api/matches_cache.py) if `ENABLE_MATCHES_CACHE=1` → [`MatchingService`](../src/mcf/api/services/matching_service.py).
5. `_build_session` loads profile embedding (resume or `:taste`), then calls `get_active_job_ids_ranked(embedding, limit=2000)` (or pool cache path if `ENABLE_ACTIVE_JOBS_POOL_CACHE=1`).
6. Scoring: **semantic cosine + recency decay** (skills weight 0). Filters → `match_sessions` pagination → JSON.

**Direct FastAPI:** If the browser calls Railway directly (no Next proxy), Next `unstable_cache` is skipped; use FastAPI caches only if enabled.

---

## 3. Caching layers (can stack)

| Layer | Where | Toggle / TTL |
|-------|--------|----------------|
| Embeddings by content hash | [`EmbeddingsCache`](../src/mcf/lib/embeddings/embeddings_cache.py) | `ENABLE_EMBEDDINGS_CACHE` (default on); LRU + optional DB |
| Active jobs pool | [`active_jobs_pool_cache.py`](../src/mcf/api/active_jobs_pool_cache.py) | `ENABLE_ACTIVE_JOBS_POOL_CACHE`; TTL 15 min |
| FastAPI matches results | [`matches_cache.py`](../src/mcf/api/matches_cache.py) | `ENABLE_MATCHES_CACHE`; TTL 15 min |
| FastAPI response cache | [`response_cache.py`](../src/mcf/api/response_cache.py) | `ENABLE_RESPONSE_CACHE`; dashboard 1h, job detail 24h, matches 15 min |
| Next.js `unstable_cache` | Route handlers under `frontend/app/api/` | e.g. matches 15 min, dashboard summary 1h |
| Supabase RPC cache | `rpc_result_cache` table | See [SUPABASE_RPC.md](SUPABASE_RPC.md) |

Invalidate user matches after resume/taste updates: `POST /api/revalidate-matches` (Next). See [CACHING_STRATEGIES.md](CACHING_STRATEGIES.md) for full details.

---

## 4. Post-crawl webhook

After `run_incremental_crawl` finishes, [`_notify_crawl_complete`](../src/mcf/lib/pipeline/incremental_crawl.py) may `POST` to `{CRAWL_WEBHOOK_URL or NEXT_PUBLIC_VERCEL_URL}/api/webhooks/crawl-complete` with header `X-Crawl-Secret: CRON_SECRET`.

**Requires** both URL and secret in the **same process** as the crawl (e.g. local CLI with `.env`). **GitHub Actions** `daily-crawl.yml` only passes `DATABASE_URL` by default — webhook does **not** run unless you add secrets and env to the workflow. See [DEPLOYMENT.md](../DEPLOYMENT.md) §4.1b.

---

## 5. Taste profile flow

1. User rates jobs on Discover → `POST /api/jobs/{uuid}/interact` with `interested` / `not_interested`.
2. User clicks compute taste → `POST /api/profile/compute-taste` → backend builds embedding from liked vs disliked job embeddings.
3. Stored as a row in `candidate_embeddings` with **`profile_id = "<uuid>:taste"`** (parallel to resume embedding row for `<uuid>`).

---

## 6. Admin access

[`_verify_admin_or_secret`](../src/mcf/api/server.py): `X-Crawl-Secret` matching `CRON_SECRET`, or JWT user in `ADMIN_USER_IDS` / DB role `admin`.
