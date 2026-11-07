# SGSAL-019 — Hot Jobs Implementation Plan

Surfaces active job listings paying ≥20% above their peer group median on a public `/hot-jobs` page, updated daily with the crawl.

---

## Context & key decisions

- **Peer group = cluster × seniority** (stratified K-means, 84 viable pairs from today's run)
- **Baseline = `salary_max_median` from `salary_stratified_viability.csv`** (already computed)
- **Comparison field = `salary_min`** (the floor the employer committed to — conservative)
- **All DB-side** — centroid assignment runs in SQL via pgvector, zero egress
- **Active jobs only** — ~70k rows, not 230k total
- **Cluster profiles are static-ish** — refresh only on model/re-cluster events, not daily

---

## Existing artefacts to reuse

| File | Used for |
|---|---|
| `scripts/cluster_analysis_output/salary_stratified_viability.csv` | Seed `cluster_salary_profiles` table |
| `scripts/cluster_analysis_output/cluster_profiles.csv` | Cluster labels for display |
| `scripts/cluster_analysis_output/jobs_df.parquet` | Refit K-means to extract centroids |
| `scripts/cluster_analysis_output/km_labels.npy` | Reference only |

---

## Step 0 — Extract & save K-means centroids

The cluster analysis run saved labels but not centroids. Fix this before anything else.

### 0a. Modify `cluster_analysis.py` to save centroids going forward

In `fit_best_kmeans()`, add one line after fitting:

```python
np.save(OUTPUT_DIR / "km_centroids.npy", km.cluster_centers_)
```

### 0b. Derive centroids from the current run (fast path, ~5 min)

Rather than rerunning the full 40-min analysis, write a standalone script
`scripts/derive_centroids.py` that:

1. Fetches active job embeddings from Supabase (all, no sampling — same query as
   `cluster_analysis.py` with `active_only=True`, `sample=0`)
2. Fits `MiniBatchKMeans(n_clusters=23, random_state=42, n_init=10, batch_size=4096)`
   — same params as the original run so centroids match the existing labels
3. Saves `scripts/cluster_analysis_output/km_centroids.npy`

Use the same connection settings (keepalives, `SET statement_timeout = 0`) as the
fixed `cluster_analysis.py`.

Result: `km_centroids.npy` — shape `(23, 768)`, float32.

---

## Step 1 — Schema changes (Supabase SQL editor)

Run these in order in the Supabase SQL editor.

### 1a. Add columns to `jobs`

```sql
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS role_cluster     INT,
  ADD COLUMN IF NOT EXISTS above_market_pct FLOAT;
```

### 1b. Create `cluster_centroids` table

```sql
CREATE TABLE IF NOT EXISTS cluster_centroids (
  cluster_id  INT PRIMARY KEY,
  label       TEXT,          -- human-readable name, e.g. "Senior Software Engineers"
  centroid    vector(768) NOT NULL
);
```

### 1c. Create `cluster_salary_profiles` table

```sql
CREATE TABLE IF NOT EXISTS cluster_salary_profiles (
  cluster_id     INT,
  seniority      TEXT,
  salary_median  FLOAT,
  salary_p25     FLOAT,
  salary_p75     FLOAT,
  n_jobs         INT,
  viable         BOOLEAN,
  PRIMARY KEY (cluster_id, seniority)
);
```

---

## Step 2 — Seed `cluster_centroids`

Write `scripts/seed_centroids.py`:

1. Load `km_centroids.npy` → shape (23, 768)
2. Load `cluster_profiles.csv` → extract `cluster` and `top_titles` (first title = label)
3. For each of the 23 clusters, INSERT into `cluster_centroids`:
   ```python
   cur.execute(
       "INSERT INTO cluster_centroids (cluster_id, label, centroid) VALUES (%s, %s, %s)"
       "ON CONFLICT (cluster_id) DO UPDATE SET centroid = EXCLUDED.centroid, label = EXCLUDED.label",
       (int(cluster_id), label, json.dumps(centroid.tolist()))
   )
   ```
4. Commit.

Total data uploaded: 23 × 768 × 4 bytes ≈ 57 KB. Negligible.

---

## Step 3 — Seed `cluster_salary_profiles`

Write `scripts/seed_cluster_profiles.py`:

1. Load `salary_stratified_viability.csv`
2. For each row, INSERT into `cluster_salary_profiles`:
   - `cluster_id` = `cluster`
   - `seniority` = `seniority`
   - `salary_median` = `salary_max_median`
   - `salary_p25` = `salary_max_p25`
   - `salary_p75` = `salary_max_p75`
   - `n_jobs` = `n_jobs`
   - `viable` = `salary_viable`
3. Commit.

---

## Step 4 — Backfill `role_cluster` for active jobs (single SQL statement)

Run in Supabase SQL editor (or via psycopg2 with `statement_timeout = 0`):

```sql
UPDATE jobs j
SET role_cluster = (
  SELECT c.cluster_id
  FROM cluster_centroids c
  ORDER BY je.embedding <=> c.centroid
  LIMIT 1
)
FROM job_embeddings je
WHERE je.job_uuid = j.job_uuid
  AND j.is_active = TRUE
  AND j.role_cluster IS NULL;
```

**Zero egress** — runs entirely on Supabase. pgvector computes the 23-centroid
distance per job server-side. With only 23 centroids, no index is needed — brute
force is faster.

Expected runtime: a few minutes for ~70k rows.

---

## Step 5 — Populate `above_market_pct` for active jobs

Run after Step 4 (needs `role_cluster` populated):

```sql
UPDATE jobs j
SET above_market_pct = ROUND(
  CAST((j.salary_min::float / p.salary_median - 1) * 100 AS numeric), 1
)
FROM cluster_salary_profiles p
WHERE j.role_cluster = p.cluster_id
  AND COALESCE(
    (j.llm_fields_json::jsonb ->> 'inferred_seniority'),
    'Unknown'
  ) = p.seniority
  AND p.viable = TRUE
  AND j.salary_min IS NOT NULL
  AND j.is_active = TRUE;
```

Jobs in non-viable (cluster, seniority) pairs get NULL — they won't appear on the
hot-jobs page, which is correct behaviour.

---

## Step 6 — Wire cluster assignment into the crawl pipeline

New jobs need `role_cluster` assigned at ingest time, right after embedding.

In `src/mcf/lib/pipeline/incremental_crawl.py` (or wherever embeddings are written),
after inserting a new row into `job_embeddings`, run:

```sql
UPDATE jobs j
SET role_cluster = (
  SELECT c.cluster_id
  FROM cluster_centroids c
  ORDER BY je.embedding <=> c.centroid
  LIMIT 1
)
FROM job_embeddings je
WHERE je.job_uuid = j.job_uuid
  AND j.job_uuid = %s
  AND j.role_cluster IS NULL;
```

Then also run the scoring update for that single job:

```sql
UPDATE jobs j
SET above_market_pct = ROUND(
  CAST((j.salary_min::float / p.salary_median - 1) * 100 AS numeric), 1
)
FROM cluster_salary_profiles p
WHERE j.job_uuid = %s
  AND j.role_cluster = p.cluster_id
  AND COALESCE(
    (j.llm_fields_json::jsonb ->> 'inferred_seniority'),
    'Unknown'
  ) = p.seniority
  AND p.viable = TRUE
  AND j.salary_min IS NOT NULL;
```

Find the exact insertion point by reading `src/mcf/lib/pipeline/incremental_crawl.py`
before making changes.

---

## Step 7 — Storage ABC + Postgres implementation

### 7a. Add `get_hot_jobs()` to `src/mcf/lib/storage/base.py`

```python
@abstractmethod
def get_hot_jobs(
    self,
    min_pct: float = 20.0,
    category: str | None = None,
    position_level: str | None = None,
    limit: int = 50,
) -> list[dict]:
    ...
```

### 7b. Implement in `src/mcf/lib/storage/postgres.py`

```sql
SELECT
  j.job_uuid,
  j.title,
  j.company_name,
  j.salary_min,
  j.salary_max,
  j.above_market_pct,
  j.metadata_json,
  j.role_cluster,
  j.llm_fields_json,
  j.categories_json,
  j.position_levels_json,
  j.created_at,
  c.label AS cluster_label
FROM jobs j
LEFT JOIN cluster_centroids c ON c.cluster_id = j.role_cluster
WHERE j.is_active = TRUE
  AND j.above_market_pct >= %(min_pct)s
  AND (%(category)s IS NULL
       OR j.categories_json::text ILIKE '%%' || %(category)s || '%%')
  AND (%(position_level)s IS NULL
       OR j.position_levels_json::text ILIKE '%%' || %(position_level)s || '%%')
ORDER BY j.above_market_pct DESC
LIMIT %(limit)s
```

---

## Step 8 — FastAPI endpoint

New file `src/mcf/api/routes/hot_jobs.py`:

```python
@router.get("/api/hot-jobs")
async def get_hot_jobs(
    category: str | None = None,
    position_level: str | None = None,
    limit: int = Query(default=50, le=200),
    storage: Storage = Depends(get_storage),
):
    jobs = storage.get_hot_jobs(
        min_pct=20.0,
        category=category,
        position_level=position_level,
        limit=limit,
    )
    return {"jobs": jobs, "count": len(jobs)}
```

Register in `src/mcf/api/server.py` alongside existing routers.

No auth required — public endpoint.

Add a short response cache (10 min TTL, no user key) following the pattern in
`src/mcf/api/cache/response.py`.

---

## Step 9 — Frontend page

New file `frontend/app/hot-jobs/page.tsx`.

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Hot Jobs — Paying above market rate                 │
│  Updated daily · {date} · {count} listings           │
├──────────────┬──────────────────────────────────────┤
│ [Category ▾] │  ┌─ Job card ──────────────────────┐ │
│ [Seniority▾] │  │ Senior Data Engineer · Grab      │ │
│              │  │ $8,000 – $12,000 / mo            │ │
│              │  │ [+38% above market] [IT · Senior]│ │
│              │  │ Posted 2d ago              [→MCF] │ │
│              │  └──────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────┘
```

### Data fetching

Add `getHotJobs(params)` to `frontend/lib/api.ts` — follows existing API client
patterns, calls `GET /api/hot-jobs`.

### Filtering

Client-side on the already-fetched result set (no additional API calls):
- Category dropdown — populated from the fetched jobs' `categories_json`
- Seniority chips — populated from `inferred_seniority` values present in results

### Job card fields

- Title + company
- Salary range (`salary_min` – `salary_max`, labelled "Monthly base salary (SGD)")
- `above_market_pct` badge (e.g. "+38% above market") — amber/green colour
- Cluster label + seniority chips
- Posting age ("2 days ago")
- External link to MCF listing

### Empty state

> "No above-market listings right now — check back after the daily crawl (10:00 SGT)."

---

## Step 10 — Add to public nav

In the frontend nav component, add "Hot Jobs" link alongside Salary Checker and
Dashboard. Do **not** add to the personal-use section (Matches, Saved, Profile).

---

## Step 11 — Add index for hot-jobs query

After backfill is complete:

```sql
CREATE INDEX IF NOT EXISTS idx_jobs_hot
  ON jobs (above_market_pct DESC)
  WHERE is_active = TRUE AND above_market_pct IS NOT NULL;
```

Partial index — only indexes the rows the hot-jobs query actually touches.

---

## Step 12 — Update TICKETS.md

Mark SGSAL-019 as `in-progress` at the start of implementation, `done` when the
page is live and verified.

---

## Refresh cadence

| Event | Action |
|---|---|
| Daily crawl | New jobs: cluster assigned + scored in pipeline (Step 6) |
| Job expires | `is_active = FALSE` — disappears from hot-jobs automatically |
| Quarterly / model update | Re-run `cluster_analysis.py` → re-seed `cluster_centroids` + `cluster_salary_profiles` → re-run Steps 4–5 |

---

## Acceptance criteria

- [ ] `km_centroids.npy` saved and committed to `scripts/cluster_analysis_output/`
- [ ] `cluster_centroids` and `cluster_salary_profiles` tables seeded in Supabase
- [ ] `jobs.role_cluster` populated for all active jobs
- [ ] `jobs.above_market_pct` populated for all active jobs with a viable baseline
- [ ] `GET /api/hot-jobs` returns correct results, ordered by score desc
- [ ] `/hot-jobs` page renders job cards with above-market badge
- [ ] Category + seniority filters work client-side
- [ ] Page linked from public nav
- [ ] Partial index added post-backfill
- [ ] Crawl pipeline assigns cluster + score to new jobs at ingest time
