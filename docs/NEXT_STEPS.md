# Next steps and to-do list for incoming team

This document is the **living to-do list** for the project. It covers all pending work across every plan discussed in this handover, with enough detail for a developer or AI agent to pick up any item cold and execute it correctly without needing to ask clarifying questions.

Each item has:
- **Status**: Pending / In progress / Done / Blocked
- **Priority**: P1 (must) / P2 (high) / P3 (nice-to-have)
- **Effort**: S (small, < 1hr) / M (medium, < 1 day) / L (large, > 1 day)
- **Exact files to touch** and what to do in each

---

## Table of contents

1. [Security — Supabase RLS](#1-security--supabase-rls)
2. [Performance — Dashboard caching](#2-performance--dashboard-caching)
3. [Bug — GitHub Actions post-crawl webhook](#3-bug--github-actions-post-crawl-webhook)
4. [Bug — CLI mark-interaction Postgres parity](#4-bug--cli-mark-interaction-postgres-parity)
5. [Quality — Automated tests (smoke)](#5-quality--automated-tests-smoke)
6. [Quality — requirements.txt sync discipline](#6-quality--requirementstxt-sync-discipline)
7. [Maintenance — CAG Algolia key](#7-maintenance--cag-algolia-key)
8. [Polish — USER_GUIDE tone](#8-polish--user_guide-tone)
9. [Optional — Split server.py into routers](#9-optional--split-serverpy-into-routers)
10. [Optional — CLI check-jobs command](#10-optional--cli-check-jobs-command)
11. [Backlog — How to add a new job source](#11-backlog--how-to-add-a-new-job-source)
12. [Feature — Lowball checker](#12-feature--lowball-checker)

---

## 1. Security — Supabase RLS

**Status:** Migration file ready, not yet applied to Supabase  
**Priority:** P1  
**Effort:** S

### What

Supabase sent a warning: public tables have no Row Level Security enabled, meaning anyone with the anon key can `SELECT *` from them via PostgREST.

### What is already done

Migration file exists at [`scripts/migrations/008_enable_rls_public_tables.sql`](../scripts/migrations/008_enable_rls_public_tables.sql). It enables RLS on 10 tables without adding any policies — PostgREST access is blocked, backend (FastAPI via `DATABASE_URL`) is unaffected because it bypasses RLS.

Also add RLS for the two remaining tables not covered by 008:

```sql
ALTER TABLE candidate_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_embeddings ENABLE ROW LEVEL SECURITY;
```

### Exact steps

1. Open Supabase SQL Editor for the project.
2. Run [`scripts/migrations/008_enable_rls_public_tables.sql`](../scripts/migrations/008_enable_rls_public_tables.sql) (paste and execute).
3. Then run the two lines above for `candidate_profiles` and `candidate_embeddings`.
4. Verify: in Supabase dashboard → Table Editor, each table should show a lock icon (RLS enabled).

### Validation

```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

All rows in `rowsecurity` column should be `true`.

---

## 2. Performance — Dashboard caching

**Status:** Planned, not implemented  
**Priority:** P1  
**Effort:** M

### The problem

The dashboard fires 7 API calls on load. Only 2 of them are cached via Next.js `unstable_cache`. The other 5 hit Railway (FastAPI) → Supabase directly on every page load, adding ~200–600ms per call (cross-region).

### Uncached calls (need fixing)

| `dashboardApi` function | Current call | FastAPI route |
|-------------------------|-------------|----------------|
| `getActiveJobsOverTime` | `api.get('/api/dashboard/active-jobs-over-time')` | Direct Railway |
| `getJobsByCategory` | `api.get('/api/dashboard/jobs-by-category')` | Direct Railway |
| `getJobsByEmploymentType` | `api.get('/api/dashboard/jobs-by-employment-type')` | Direct Railway |
| `getJobsByPositionLevel` | `api.get('/api/dashboard/jobs-by-position-level')` | Direct Railway |
| `getSalaryDistribution` | `api.get('/api/dashboard/salary-distribution')` | Direct Railway |

### Fix part 1 — Add 5 Next.js Route Handlers

Create these 5 files, each following the same pattern as the existing `summary/route.ts`:

**`frontend/app/api/dashboard/active-jobs-over-time/route.ts`**
```ts
import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const REVALIDATE_SECONDS = 3600

export const revalidate = REVALIDATE_SECONDS

export async function GET(request: NextRequest) {
  const limitDays = Math.min(Math.max(parseInt(request.nextUrl.searchParams.get('limit_days') || '90', 10), 1), 365)
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(`${API_BASE_URL}/api/dashboard/active-jobs-over-time-public?limit_days=${limitDays}`, {
          headers: { 'Content-Type': 'application/json' },
          next: { revalidate: REVALIDATE_SECONDS },
        })
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-active-jobs-over-time', String(limitDays)],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/active-jobs-over-time]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
```

Apply the same pattern for:
- `frontend/app/api/dashboard/jobs-by-category/route.ts` — proxies `/api/dashboard/jobs-by-category-public?limit_days=...&limit=...`
- `frontend/app/api/dashboard/jobs-by-employment-type/route.ts` — proxies `/api/dashboard/jobs-by-employment-type` (no public variant exists; this one requires auth — see note below)
- `frontend/app/api/dashboard/jobs-by-position-level/route.ts` — same
- `frontend/app/api/dashboard/salary-distribution/route.ts` — proxies `/api/dashboard/salary-distribution`

> **Note on auth variants**: `jobs-by-employment-type`, `jobs-by-position-level`, and `salary-distribution` do not have `-public` variants in the FastAPI server. You have two options:
> - **Option A (recommended)**: Add `-public` variants to `src/mcf/api/server.py` (copy pattern from `jobs-by-category-public`), then the Next.js route handlers can call those without needing auth headers.
> - **Option B**: Forward the `Authorization` header from the incoming request to FastAPI in the route handler.
> Option A is cleaner and consistent with existing patterns.

### Fix part 2 — Update `dashboardApi` in `frontend/lib/api.ts`

For the 5 functions, switch from direct axios (`api.get(...)`) to same-origin `fetch` calls that hit the new Next.js route handlers:

```ts
// BEFORE (in frontend/lib/api.ts)
getActiveJobsOverTime: async (limitDays = 90) => {
  const response = await api.get('/api/dashboard/active-jobs-over-time', {
    params: { limit_days: limitDays },
  })
  return response.data as Array<{ date: string; active_count: number }>
},

// AFTER
getActiveJobsOverTime: async (limitDays = 90) => {
  const res = await fetch(`/api/dashboard/active-jobs-over-time?limit_days=${limitDays}`)
  if (!res.ok) throw new Error('Failed to fetch active jobs over time')
  return res.json() as Promise<Array<{ date: string; active_count: number }>>
},
```

Repeat for `getJobsByCategory`, `getJobsByEmploymentType`, `getJobsByPositionLevel`, `getSalaryDistribution`.

### Fix part 3 — Enable FastAPI response cache on Railway

In Railway environment variables, add:

```
ENABLE_RESPONSE_CACHE=1
```

No code change required. This activates [`src/mcf/api/response_cache.py`](../src/mcf/api/response_cache.py) which already decorates all dashboard routes with a 1-hour TTL.

### Expected result

- First load per `limitDays` value: one backend call. Cached by Vercel CDN after that.
- Time-range button changes (30d/90d/180d/365d): each has its own cache key.
- Daily crawl webhook at `POST /api/webhooks/crawl-complete` already revalidates the `dashboard-stats` tag — caches flush automatically after crawl.

---

## 3. Bug — GitHub Actions post-crawl webhook

**Status:** Known gap, not fixed  
**Priority:** P2  
**Effort:** S

### The problem

[`.github/workflows/daily-crawl.yml`](../.github/workflows/daily-crawl.yml) only sets `DATABASE_URL` in the crawl environment. The post-crawl webhook in `incremental_crawl.py` also needs `CRON_SECRET` and `CRAWL_WEBHOOK_URL` to fire. Without them, daily scheduled crawls do not invalidate dashboard or match caches automatically.

### Fix

**Step 1:** Add two secrets in GitHub → Settings → Secrets and variables → Actions:
- `CRON_SECRET` — same value as on Railway and Vercel
- `CRAWL_WEBHOOK_URL` — your Vercel production URL (e.g. `https://your-app.vercel.app`)

**Step 2:** Edit [`.github/workflows/daily-crawl.yml`](../.github/workflows/daily-crawl.yml) — in the `Run incremental crawl` step, add to the `env:` block:

```yaml
env:
  DATABASE_URL: ${{ secrets.DATABASE_URL }}
  CRON_SECRET: ${{ secrets.CRON_SECRET }}
  CRAWL_WEBHOOK_URL: ${{ secrets.CRAWL_WEBHOOK_URL }}
```

### Validation

After next scheduled or manual crawl run, check GitHub Actions logs for a line like `crawl webhook: POST ... 200` from `_notify_crawl_complete()` in `incremental_crawl.py`.

---

## 4. Bug — CLI mark-interaction Postgres parity

**Status:** Known limitation, pending  
**Priority:** P3  
**Effort:** M

### The problem

[`src/mcf/cli/cli.py`](../src/mcf/cli/cli.py) — `mark-interaction` command opens storage via `_open_store()` but the function signature shows it does not accept `--db-url`, so it always uses DuckDB. Anyone running the CLI against a Postgres deployment cannot mark interactions from the CLI.

### Fix

In `cli.py`, find the `mark_interaction` function (search `@app.command("mark-interaction")`). Add a `db_url` option matching the pattern used by `crawl_incremental` and `export_to_postgres`:

```python
@app.command("mark-interaction")
def mark_interaction(
    job_uuid: str = typer.Argument(...),
    interaction_type: str = typer.Option(..., "--type", "-t"),
    db: Optional[Path] = typer.Option(None, "--db"),
    db_url: Optional[str] = typer.Option(None, "--db-url", envvar="DATABASE_URL"),
    ...
):
    store, label = _open_store(db, db_url)
```

The `_open_store` helper already handles both cases — just pass `db_url` through.

---

## 5. Quality — Automated tests (smoke)

**Status:** Not started  
**Priority:** P2  
**Effort:** M

### The problem

There are zero automated tests in the repo. `pytest` is in `dev` dependencies but unused.

### Recommended minimal smoke tests

Create `tests/test_smoke.py`:

```python
from fastapi.testclient import TestClient
from mcf.api.server import app

client = TestClient(app)

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200

def test_summary_public():
    r = client.get("/api/dashboard/summary-public")
    assert r.status_code == 200
    data = r.json()
    assert "total_jobs" in data

def test_discover_stats_no_auth():
    # Returns 401 or 403 when auth is enabled, not 500
    r = client.get("/api/discover/stats")
    assert r.status_code in (200, 401, 403)
```

Run with:
```bash
uv run pytest tests/ -v
```

Add to CI by inserting a new GitHub Actions job (optional — separate workflow or step in `daily-crawl.yml`).

---

## 6. Quality — requirements.txt sync discipline

**Status:** Process gap, not fixed  
**Priority:** P2  
**Effort:** S

### The problem

[`Dockerfile.api`](../Dockerfile.api) installs from `requirements.txt`, not `pyproject.toml`. `requirements.txt` is generated by `uv` and can drift if someone updates `pyproject.toml` without regenerating.

### Fix (process, not code)

Whenever `pyproject.toml` dependencies change, run:

```bash
uv pip compile pyproject.toml -o requirements.txt
```

Then commit both files together. A note is already in [`README.md`](../README.md) and [`docs/TECH_STACK.md`](TECH_STACK.md).

**Optional: enforce via CI** — add a step to `daily-crawl.yml` or a separate `lint.yml` that checks `requirements.txt` is up to date:

```yaml
- name: Check requirements.txt is up to date
  run: |
    uv pip compile pyproject.toml -o /tmp/requirements_check.txt
    diff requirements.txt /tmp/requirements_check.txt || (echo "requirements.txt is stale — run: uv pip compile pyproject.toml -o requirements.txt" && exit 1)
```

---

## 7. Maintenance — CAG Algolia key

**Status:** Known risk, no action needed now  
**Priority:** P3 (only act when CAG crawl breaks)  
**Effort:** S when needed

### The problem

[`src/mcf/lib/sources/cag_source.py`](../src/mcf/lib/sources/cag_source.py) has a hardcoded Algolia search-only API key:

```python
_ALGOLIA_API_KEY = "32fa71d8b0bc06be1e6395bf8c430107"
```

It is a public read-only key scraped from the Careers@Gov website. It is not a secret, but if Algolia rotates it the CAG crawl will silently return 0 jobs.

### How to detect

If a daily crawl logs `cag: 0 new jobs` when that was not expected, check by visiting `https://jobs.careers.gov.sg/` in a browser and using DevTools Network tab to find the current Algolia API key in the request headers.

### How to fix

Update `_ALGOLIA_API_KEY` and optionally `_ALGOLIA_APP_ID` in `cag_source.py`. These values are visible in any browser request to the CAG job listing.

**Optional improvement:** Move these to an env var (`CAG_ALGOLIA_API_KEY`) and add to `.env.example`, so future rotations are configuration changes rather than code changes.

---

## 8. Optional — Split server.py into routers

**Status:** Optional, not started  
**Priority:** P3  
**Effort:** L

### Context

[`src/mcf/api/server.py`](../src/mcf/api/server.py) is ~795 lines and contains all ~30 routes in one file. It is well-organized with clear section comments (`# Dashboard`, `# Profile`, `# Admin`, etc.) and short functions. It works fine. This is a code hygiene refactor, not a bug fix.

### Proposed structure (if done)

```
src/mcf/api/
  server.py          # app init, lifespan, middleware — imports all routers
  routers/
    dashboard.py     # /api/dashboard/* routes
    profile.py       # /api/profile/* routes
    jobs.py          # /api/jobs/* routes
    matches.py       # /api/matches route
    admin.py         # /api/admin/* routes
    health.py        # /api/health, /api/cors-check
```

Each router file uses `APIRouter`:
```python
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/dashboard/summary")
def get_dashboard_summary(...): ...
```

`server.py` includes them:
```python
from mcf.api.routers import dashboard, profile, jobs, matches, admin, health
app.include_router(dashboard.router)
# ...
```

**Do not do this without a test run.** Dependency injection (`get_store()`, `get_current_user`) is module-level and will need to be re-threaded into each router file.

---

## 9. Optional — CLI check-jobs command

**Status:** Optional, not started
**Priority:** P3
**Effort:** S

### Context

A production health check command would show active/inactive job counts and recent run statuses without needing the Supabase SQL Editor.

### Fix

Add `mcf check-jobs --db-url $DATABASE_URL` to `src/mcf/cli/cli.py`:

1. Use `_open_store(db, db_url)` to get a store.
2. Call existing store methods: `get_dashboard_summary()`, `get_recent_runs(limit=5)`.
3. Print with `rich`.

---

## 11. Backlog — How to add a new job source

**Status:** Reference, no action needed  
**Priority:** N/A

### How it works

The source layer is designed for extension. To add a new job source (e.g. LinkedIn, Indeed):

1. Create `src/mcf/lib/sources/new_source.py`.
2. Implement the `JobSource` protocol from [`src/mcf/lib/sources/base.py`](../src/mcf/lib/sources/base.py):
   - `source_id: str` — unique short name (e.g. `"linkedin"`)
   - `list_job_ids() -> list[str]` — return current listing of external IDs
   - `fetch_job_detail(external_id) -> NormalizedJob` — fetch and return normalized job
3. All existing pipeline, embedding, and storage code is source-agnostic via `NormalizedJob`.
4. Add a `--source <name>` option to `mcf crawl-incremental` in `cli.py`.

**UUID note:** Non-MCF sources get a `source_id:external_id` composite UUID (from `NormalizedJob.job_uuid`). Dashboard queries filter `job_source = 'mcf'` — new source data is collected but excluded from the main dashboard until you add a filter option.

---

---

## 12. Feature — Lowball checker

**Status:** Planned, not started  
**Priority:** P1 (new feature, owner-requested)  
**Effort:** L

### What the feature does

A user navigates to `/lowball`, pastes a job description they have received from an employer, and enters the salary they have been offered (monthly SGD). The system:

1. Embeds the job description using the same BGE model already in use.
2. Finds the most semantically similar active jobs in the database (up to 500 candidate pool, filtered to the best 20).
3. Filters those matches to ones that have disclosed salary data.
4. Computes market salary percentiles (p25, p50, p75) from the filtered set.
5. Compares the user's offered salary to those percentiles and returns a clear verdict: **lowballed**, **below median**, **at median**, or **above median**.

The result page shows a color-coded verdict card, a salary position bar (where the user's offer sits relative to p25/p50/p75), and a table of the matched similar jobs with their salary ranges for full transparency.

### Why this is non-trivial — known issues and how they are handled

#### Issue 1 — Jobs are not actually deleted (common misconception)
The daily crawl does **not** delete rows from the `jobs` table. It only sets `is_active = FALSE`. Salary data (`jobs.salary_min`, `jobs.salary_max`) therefore survives indefinitely.

What **is** deleted is the `job_embeddings` row for inactive jobs that have never been interacted with by any user. This means vector similarity matching is limited to: active jobs + inactive jobs that were interacted with.

**Decision for MVP:** Compare against active jobs only. At any given time this is 15,000–20,000+ listings — more than enough for meaningful percentiles. The limitation is documented in the UI ("compared against currently active listings").

**Future improvement:** Modify `delete_inactive_job_embeddings()` in [`src/mcf/lib/storage/postgres_store.py`](../src/mcf/lib/storage/postgres_store.py) to preserve embeddings for jobs that have a non-null `salary_min`. This would build a permanent historical salary pool over time.

#### Issue 2 — Salary data is sparse
MCF's job listings optionally disclose salary. A meaningful fraction of listings show "Not disclosed". If only 2 of 20 matched jobs have salary data, any percentile figure would be statistically meaningless.

**Decision:** After filtering for salary-disclosed matches, require a minimum of **5 jobs** before computing percentiles. If fewer than 5 are found, return verdict `"insufficient_data"` and show an explanatory message. Always display the coverage ratio ("salary disclosed in X of Y matched jobs") so the user understands the confidence level.

#### Issue 3 — Embedding must use the passage side, not the query side
The BGE model is used asymmetrically in this codebase:
- **Job descriptions** at crawl time → `embed_text()` (passage side, no prefix)
- **Resumes** at upload time → `embed_query()` (query prefix: `"Represent this resume for job search: "`)

All stored `job_embeddings` rows are passage-side vectors. For the Lowball feature, the user's input is a **job description**, so it must be embedded with `embed_text()` to be cosine-comparable to stored job embeddings. Using `embed_query()` here would degrade match quality. This is an easy mistake to make — it is called out explicitly in the backend code comment.

#### Issue 4 — Salary units must be normalized
The database stores salary as **SGD monthly integers** (e.g., `3500` means $3,500/month). Users may not know this. The UI must be clear: "Monthly salary in SGD". When both `salary_min` and `salary_max` are provided, the comparison uses the midpoint `(salary_min + salary_max) // 2`. When only `salary_min` is provided, it is used directly.

#### Issue 5 — No existing "embed arbitrary text" API endpoint
The API has no generic "give me a vector for this text" endpoint. This is intentional — embedding is a side effect of the crawl or resume pipeline. The Lowball endpoint handles embedding internally server-side, exactly as the resume upload endpoint does. No separate embedding endpoint is needed.

#### Issue 6 — Auth gating
This endpoint embeds user-supplied text and runs a 500-job vector scan on every request. It must be auth-gated (`Depends(get_current_user)`) to prevent unauthenticated abuse. Because the endpoint does not persist anything to the database, a future `-public` variant with rate limiting is straightforward to add.

---

### Data flow

```
User (browser)
  │ POST { job_description, salary_min, salary_max }
  ▼
Next.js Route Handler  /api/lowball/check  (thin proxy, no caching)
  │ forward with auth header
  ▼
FastAPI  POST /api/lowball/check
  │ embed_text(job_description)  ← passage side, same as crawl pipeline
  │ get_active_job_ids_ranked(vector, limit=500)  ← reuses existing pool infrastructure
  │ get_jobs_with_salary_by_uuids(top 100 UUIDs)  ← new storage method
  │ filter to salary-disclosed jobs
  │ compute p25 / p50 / p75 using statistics.quantiles
  │ compare offered_salary to percentiles → verdict
  ▼
Response { verdict, offered_salary, percentile, market_p25/50/75,
           salary_coverage, total_matched, similar_jobs[] }
  ▼
LowballContent.tsx  (renders verdict card + salary bar + jobs table)
```

---

### Backend — exact changes

#### A. Pydantic models (add to `src/mcf/api/server.py`)

```python
class LowballCheckRequest(BaseModel):
    job_description: str        # raw text of the job description
    salary_min: int             # offered monthly salary in SGD (required)
    salary_max: int | None = None  # upper bound if range given (optional)
    top_k: int = 20             # number of similar jobs to include in response

class LowballResult(BaseModel):
    verdict: str                # one of: "lowballed" | "below_median" | "at_median" | "above_median" | "insufficient_data"
    offered_salary: int         # midpoint of salary_min/salary_max, or salary_min if no max given
    percentile: float | None    # where the offered salary falls (0–100), or null if insufficient_data
    market_p25: int | None      # 25th percentile of matched jobs' salary_min
    market_p50: int | None      # median
    market_p75: int | None      # 75th percentile
    salary_coverage: int        # count of matched jobs that had disclosed salary
    total_matched: int          # total semantically similar jobs found (before salary filter)
    similar_jobs: list[dict]    # top_k jobs: { title, company_name, salary_min, salary_max, similarity_score }
```

Verdict thresholds:
- `offered_salary < market_p25` → `"lowballed"`
- `market_p25 <= offered_salary < market_p50` → `"below_median"`
- `market_p50 <= offered_salary < market_p75` → `"at_median"`
- `offered_salary >= market_p75` → `"above_median"`
- Fewer than 5 salary-disclosed matches → `"insufficient_data"`

#### B. New FastAPI route (add to `src/mcf/api/server.py`)

```python
@app.post("/api/lowball/check")
def check_lowball(
    body: LowballCheckRequest,
    user_id: str = Depends(get_current_user),
):
    store = get_store()
    # IMPORTANT: use embed_text (passage side), NOT embed_query.
    # Stored job_embeddings are passage-side vectors. The input is a job description, not a resume.
    embedder = Embedder(EmbedderConfig(), embeddings_cache=embeddings_cache)
    vector = embedder.embed_text(body.job_description)

    # Fetch a wide candidate pool, then narrow down
    ranked = store.get_active_job_ids_ranked(vector, limit=500)
    # ranked entries are "uuid:score" strings — split to get UUIDs
    top_uuids_with_scores = [(e.split(":")[0], float(e.split(":")[1])) for e in ranked[: body.top_k * 5]]
    uuid_to_score = dict(top_uuids_with_scores)

    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))

    # Salary-disclosed subset
    salary_jobs = [j for j in jobs if j["salary_min"] is not None]
    offered = body.salary_min if body.salary_max is None else (body.salary_min + body.salary_max) // 2

    if len(salary_jobs) < 5:
        return LowballResult(
            verdict="insufficient_data", offered_salary=offered,
            percentile=None, market_p25=None, market_p50=None, market_p75=None,
            salary_coverage=len(salary_jobs), total_matched=len(jobs),
            similar_jobs=_build_similar_jobs(jobs[:body.top_k], uuid_to_score),
        )

    salaries = sorted(j["salary_min"] for j in salary_jobs)
    p25, p50, p75 = _salary_percentiles(salaries)  # helper using statistics.quantiles
    percentile = sum(1 for s in salaries if s <= offered) / len(salaries) * 100

    if offered < p25:
        verdict = "lowballed"
    elif offered < p50:
        verdict = "below_median"
    elif offered < p75:
        verdict = "at_median"
    else:
        verdict = "above_median"

    return LowballResult(
        verdict=verdict, offered_salary=offered, percentile=round(percentile, 1),
        market_p25=p25, market_p50=p50, market_p75=p75,
        salary_coverage=len(salary_jobs), total_matched=len(jobs),
        similar_jobs=_build_similar_jobs(jobs[:body.top_k], uuid_to_score),
    )
```

#### C. New storage method (add to all three storage files)

**`src/mcf/lib/storage/base.py`** — add abstract method:
```python
@abstractmethod
def get_jobs_with_salary_by_uuids(self, job_uuids: list[str]) -> list[dict]:
    """Return job_uuid, title, company_name, salary_min, salary_max for given UUIDs."""
```

**`src/mcf/lib/storage/postgres_store.py`** — implement:
```python
def get_jobs_with_salary_by_uuids(self, job_uuids: list[str]) -> list[dict]:
    if not job_uuids:
        return []
    with self._cur() as cur:
        cur.execute(
            "SELECT job_uuid, title, company_name, salary_min, salary_max "
            "FROM jobs WHERE job_uuid = ANY(%s)",
            (job_uuids,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
```

**`src/mcf/lib/storage/duckdb_store.py`** — implement (DuckDB uses `?` placeholders, not `ANY`):
```python
def get_jobs_with_salary_by_uuids(self, job_uuids: list[str]) -> list[dict]:
    if not job_uuids:
        return []
    placeholders = ", ".join("?" * len(job_uuids))
    rows = self._con.execute(
        f"SELECT job_uuid, title, company_name, salary_min, salary_max "
        f"FROM jobs WHERE job_uuid IN ({placeholders})",
        job_uuids,
    ).fetchall()
    cols = ["job_uuid", "title", "company_name", "salary_min", "salary_max"]
    return [dict(zip(cols, row)) for row in rows]
```

No database migration required. `salary_min` and `salary_max` already exist on the `jobs` table from [`scripts/migrations/003_add_rich_job_fields.sql`](../scripts/migrations/003_add_rich_job_fields.sql).

---

### Frontend — exact changes

#### D. New page `frontend/app/lowball/page.tsx`

Server Component wrapper. Follows the same pattern as `frontend/app/dashboard/page.tsx`. Wraps `LowballContent` in `<AuthGate>`.

```tsx
import { AuthGate } from '../components/AuthGate'
import { LowballContent } from './LowballContent'

export const metadata = { title: 'Lowball Checker — MCF' }

export default function LowballPage() {
  return (
    <AuthGate>
      <LowballContent />
    </AuthGate>
  )
}
```

#### E. New Client Component `frontend/app/lowball/LowballContent.tsx`

Three UI states managed with local state:

**State 1 — Input form**
- `<textarea>` labeled "Job description" (paste the full JD)
- Number input: "Offered salary — minimum (SGD/month)"
- Number input: "Offered salary — maximum (SGD/month, optional)"
- Number input: "How many similar jobs to compare against" (default 20, max 50)
- "Check" button → calls `lowballApi.check(...)`

**State 2 — Loading**
- Spinner with message "Analysing market data..."

**State 3 — Results**
- Verdict card: large text (`"You may be lowballed"` / `"Below market median"` / `"At market rate"` / `"Above market rate"` / `"Not enough data"`), color-coded (red / amber / green / green / grey)
- Salary position bar: horizontal bar with markers at p25 / p50 / p75 and a pin showing the user's offer
- Coverage note: "Based on X of Y matched jobs that disclosed salary"
- Collapsible table: similar jobs with title, company, salary range (shows "Not disclosed" for nulls), and similarity score

#### F. New Next.js Route Handler `frontend/app/api/lowball/check/route.ts`

No `unstable_cache` — each request is unique (different description, different salary).

```ts
import { NextRequest, NextResponse } from 'next/server'
import { getToken } from '@/lib/jwt-verify'  // or whichever auth helper is used by /api/matches

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const token = request.headers.get('Authorization')
  if (!token) return NextResponse.json({ detail: 'Unauthorized' }, { status: 401 })

  const body = await request.json()
  const res = await fetch(`${API_BASE_URL}/api/lowball/check`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: token,
    },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
```

#### G. New `lowballApi` in `frontend/lib/api.ts`

```ts
export const lowballApi = {
  check: async (
    jobDescription: string,
    salaryMin: number,
    salaryMax?: number,
    topK = 20,
  ): Promise<LowballResult> => {
    const session = await getSupabaseSession()
    const token = session?.access_token
    const res = await fetch('/api/lowball/check', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        job_description: jobDescription,
        salary_min: salaryMin,
        salary_max: salaryMax ?? null,
        top_k: topK,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Lowball check failed')
    }
    return res.json()
  },
}
```

Add the `LowballResult` TypeScript interface alongside the API function:
```ts
interface LowballResult {
  verdict: 'lowballed' | 'below_median' | 'at_median' | 'above_median' | 'insufficient_data'
  offered_salary: number
  percentile: number | null
  market_p25: number | null
  market_p50: number | null
  market_p75: number | null
  salary_coverage: number
  total_matched: number
  similar_jobs: Array<{
    job_uuid: string
    title: string
    company_name: string
    salary_min: number | null
    salary_max: number | null
    similarity_score: number
  }>
}
```

#### H. Sidebar nav link — `frontend/app/components/Sidebar.tsx`

Add a "Lowball" entry to the nav links array (exact position: after `/dashboard`, before `/how-it-works`). Use the same link shape as existing entries. A scale/balance icon from `lucide-react` or `heroicons` fits the concept.

---

### Complete file list

| Action | File | What changes |
|--------|------|-------------|
| Create | `frontend/app/lowball/page.tsx` | New Server Component page |
| Create | `frontend/app/lowball/LowballContent.tsx` | Input form + results UI |
| Create | `frontend/app/api/lowball/check/route.ts` | POST proxy to FastAPI |
| Edit | `frontend/lib/api.ts` | Add `lowballApi` + `LowballResult` interface |
| Edit | `frontend/app/components/Sidebar.tsx` | Add `/lowball` nav link |
| Edit | `src/mcf/api/server.py` | Add `LowballCheckRequest`, `LowballResult`, `POST /api/lowball/check`, helper functions |
| Edit | `src/mcf/lib/storage/base.py` | Add `get_jobs_with_salary_by_uuids` abstract method |
| Edit | `src/mcf/lib/storage/postgres_store.py` | Implement the method |
| Edit | `src/mcf/lib/storage/duckdb_store.py` | Implement the method |

**No database migrations needed.** `salary_min` and `salary_max` already exist from migration 003.

---

### Future enhancements (not in this plan, but documented for next owners)

| Enhancement | What it would take |
|-------------|-------------------|
| **Historical salary pool** | In `delete_inactive_job_embeddings()`, add a `WHERE salary_min IS NULL` guard to preserve embeddings for jobs that had salary data. This passively builds a larger comparison pool over time. |
| **Filter by category** | Add an optional `category` parameter to `LowballCheckRequest`. In the storage method, add `AND categories_json @> '["category"]'` (or equivalent) to narrow the comparison to a specific job category. |
| **Save a check** | Add a `lowball_checks` table (columns: `check_id`, `user_id`, `created_at`, `job_description_hash`, `offered_salary`, `verdict`, `market_p50`, `salary_coverage`). New storage methods: `save_lowball_check`, `get_lowball_checks_for_user`. New route: `GET /api/lowball/history`. |
| **Public endpoint** | Add `POST /api/lowball/check-public` with no auth but rate-limited by IP (e.g. via Railway or a FastAPI `slowapi` middleware). |

---

## Summary table

| # | Item | Status | Priority | Effort |
|---|------|--------|----------|--------|
| 1 | Apply RLS migrations in Supabase | **Done** | P1 | S |
| 2 | Dashboard caching (5 routes + Railway env) | **Done** | P1 | M |
| 3 | GH Actions webhook secrets | **Done** (env vars in workflow; add GitHub secrets if you want post-crawl flush) | P2 | S |
| 4 | CLI mark-interaction Postgres parity | **Done** | P3 | M |
| 5 | Smoke tests (pytest) | **Done** | P2 | M |
| 6 | requirements.txt sync | **Done** (CI check removed — platform-specific; process documented in README) | P2 | S |
| 7 | CAG Algolia key | **Done** (moved to `CAG_ALGOLIA_API_KEY` env var; hardcoded value is fallback) | P3 | S |
| 8 | Split server.py into routers | Optional | P3 | L |
| 9 | Add `mcf check-jobs` CLI command | Optional | P3 | S |
| 10 | How to add a new job source | Reference | — | — |
| 11 | Lowball checker (new feature) | Pending | P1 | L |

---

*Last updated during handover. Add new items here as they are discovered. When an item is completed, mark its status row and add a brief note on what was done and any side effects.*
