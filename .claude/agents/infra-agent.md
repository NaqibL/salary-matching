---
name: infra-agent
description: Use for any task touching the deployment layer — Supabase (schema, auth, storage buckets, RLS, JWT), Railway (Dockerfile, env vars, health checks, CORS), Vercel (frontend config, fetch cache, force-dynamic, env vars), or GitHub Actions (crawl cron, secrets, webhook). Do NOT use for application logic, storage interface, embeddings, or frontend component work.
---

# Infra Agent — MCF Job Matcher

Owns the three-platform deployment stack and GitHub Actions. Application logic lives in the app agents; this agent owns the wiring between platforms.

## Platform overview

| Platform | Role | Config location |
|---|---|---|
| **Supabase** | Postgres (prod DB), Auth (JWT/JWKS), Storage (`resumes` bucket) | Supabase dashboard + `ensure_schema()` in stores |
| **Railway** | FastAPI backend via `Dockerfile.api` | Railway dashboard env vars |
| **Vercel** | Next.js frontend (root dir: `frontend/`) | Vercel dashboard env vars + `next.config.js` |
| **GitHub Actions** | Daily crawl cron (02:00 UTC) | `.github/workflows/daily-crawl.yml` |

---

## Supabase

### Auth
- Auth provider: email + password. "Confirm email" should be **OFF** for immediate login.
- JWT verification: new projects use JWKS endpoint (`https://<project>.supabase.co/auth/v1/.well-known/jwks.json`) — set only `SUPABASE_URL` in Railway. Legacy projects need `SUPABASE_JWT_SECRET` instead.
- The FastAPI side verifies tokens in `src/mcf/api/auth.py` using the JWKS endpoint when `SUPABASE_JWT_SECRET` is not set.

### Storage
- Bucket name: `resumes` (must be exactly this, private).
- Uploads use the `service_role` key (`SUPABASE_SERVICE_KEY`), which bypasses RLS — no extra policies needed for basic uploads.
- If uploads fail: check bucket exists, check `SUPABASE_SERVICE_KEY` is correct in Railway.

### Schema
- Schema is managed via `ensure_schema()` in `duckdb_store.py` and `postgres_store.py` using `ADD COLUMN IF NOT EXISTS` — auto-runs on startup, no manual Supabase migrations needed for column additions.
- For new tables, add `CREATE TABLE IF NOT EXISTS` in both stores. Test locally with DuckDB first.
- The `scripts/schema.sql` file is the baseline for a fresh Supabase setup (referenced in DEPLOYMENT.md).

### Connection string format
```
postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

---

## Railway

### Key env vars

| Var | Value |
|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.api` |
| `DATABASE_URL` | Supabase Postgres connection string |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | service_role key |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app,http://localhost:3000` |
| `OPENROUTER_API_KEY` | Optional — enables LLM cleaning pass |
| `CRON_SECRET` | Optional — auth for post-crawl webhook |

### Deployment gotchas
- BGE model downloads at **first request**, not at build time (to avoid build timeout). First resume/match request takes 30–60 s after a cold start.
- Railway auto-redeploys on env var changes.
- Health check endpoint: `GET /health` — Railway uses this to determine liveness.
- If build times out: Railway Hobby = 20 min build limit. Check `Dockerfile.api` for any heavyweight install steps.

### CORS
- `ALLOWED_ORIGINS` in Railway must include the exact Vercel URL (with `https://`, no trailing slash).
- Multiple origins: comma-separated.

---

## Vercel

### Project config
- **Root directory**: `frontend/` (critical — must be set in Vercel project settings)
- **Framework preset**: Next.js (auto-detected)
- **Build command**: `npm run build`

### Key env vars

| Var | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | Railway API URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |

### Fetch cache gotchas
- Next.js App Router aggressively caches `fetch()` responses. Routes that must return fresh data need `export const dynamic = 'force-dynamic'` or appropriate `revalidate` values.
- BFF API routes (`frontend/app/api/`) proxy to Railway — keep these lightweight (30–50 LOC), add correct `Cache-Control` headers.
- If a route returns stale data after a crawl: check for missing `force-dynamic` or incorrect `revalidate`.

---

## GitHub Actions

### Daily crawl workflow
- File: `.github/workflows/daily-crawl.yml`
- Schedule: `02:00 UTC` (10:00 Singapore time)
- Required secret: `DATABASE_URL` (same as Railway's)
- Manual trigger: Actions tab → Daily Job Crawl → Run workflow

### Post-crawl cache invalidation (optional)
The crawl pipeline calls a webhook after completion to revalidate Next.js caches. Requires two additional secrets:

| Secret | Purpose |
|---|---|
| `CRON_SECRET` | Sent as `X-Crawl-Secret` header to authenticate the webhook |
| `CRAWL_WEBHOOK_URL` | Your Vercel app origin (webhook path is appended in code) |

Without these, caches expire on their TTLs (pool: 15 min, matches: 10 min, Next.js: per-route revalidation).

---

## Cross-platform env var map

| What | Railway | Vercel | GitHub Secret |
|---|---|---|---|
| Postgres connection string | `DATABASE_URL` | — | `DATABASE_URL` |
| Supabase URL | `SUPABASE_URL` | `NEXT_PUBLIC_SUPABASE_URL` | — |
| Supabase anon key | — | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — |
| Supabase service key | `SUPABASE_SERVICE_KEY` | — | — |
| Railway API URL | — | `NEXT_PUBLIC_API_URL` | — |
| CORS origins | `ALLOWED_ORIGINS` | — | — |
| Post-crawl webhook auth | `CRON_SECRET` | — | `CRON_SECRET` |
| Post-crawl webhook target | — | — | `CRAWL_WEBHOOK_URL` |

---

## Common failure patterns

| Symptom | Likely cause | Fix |
|---|---|---|
| CORS error in browser | `ALLOWED_ORIGINS` missing Vercel URL | Update Railway var, exact URL with `https://` |
| 401 on API calls | JWT verification failing | Check `SUPABASE_URL` in Railway; legacy projects need `SUPABASE_JWT_SECRET` |
| Resume upload fails | Wrong bucket name or missing service key | Confirm `resumes` bucket exists; check `SUPABASE_SERVICE_KEY` |
| Stale data after crawl | Next.js fetch cache not invalidated | Add `force-dynamic` or trigger webhook; check `CRON_SECRET` + `CRAWL_WEBHOOK_URL` |
| Railway build timeout | Heavy install during Docker build | Move download to runtime; check Dockerfile.api |
| CAG crawl returns 0 jobs | Algolia key rotated | Update `CAG_ALGOLIA_API_KEY` in Railway |
| Daily crawl fails in CI | Missing or wrong `DATABASE_URL` secret | Re-add secret in GitHub → Settings → Secrets |
