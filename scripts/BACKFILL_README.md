# Backfill Rich Job Fields

After applying migration `003_add_rich_job_fields.sql`, existing jobs in your database have `NULL` in the new columns (categories, employment types, salary, posting dates, etc.). The **backfill** command fetches job details from the MyCareersFuture API and populates these fields.

## Prerequisites

1. **Migration applied**: Run `scripts/migrations/003_add_rich_job_fields.sql` in the Supabase SQL Editor (or your Postgres database).
2. **Database connection**: `DATABASE_URL` for Postgres, or `--db` for DuckDB.

## When to Run

- After deploying the Dashboard & DB Streamlining changes
- When you have many existing jobs (e.g. 60k+) that were crawled before the rich fields were added
- Run **locally** or via **GitHub Actions** — use batched runs (`--limit 5000`) to avoid timeouts

## How to Run

### Postgres (Supabase)

```bash
# Uses DATABASE_URL from environment
uv run mcf backfill-rich-fields

# Explicit URL
uv run mcf backfill-rich-fields --db-url "postgresql://..."
```

### DuckDB (local)

```bash
uv run mcf backfill-rich-fields --db data/mcf.duckdb
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--db` | `data/mcf.duckdb` | DuckDB file path |
| `--db-url` | *(env: DATABASE_URL)* | PostgreSQL connection URL |
| `--rate-limit`, `-r` | `4` | API requests per second |
| `--limit`, `-l` | *(none)* | Max jobs to process (for batched runs) |

### GitHub Actions (recommended if local fails)

If local runs fail (e.g. DNS/network issues with Supabase), use the workflow:

1. Ensure `DATABASE_URL` is set in **Settings → Secrets and variables → Actions**
2. Go to **Actions** → **Backfill Rich Fields** → **Run workflow**
3. Optionally set **limit** (default 5000) and **rate_limit** (default 4)
4. Run repeatedly until "No jobs need backfill"

### Batched Runs

For very large datasets, run in batches to avoid timeouts and allow resume:

```bash
# Process 5000 jobs per run; repeat until "No jobs need backfill"
uv run mcf backfill-rich-fields --limit 5000
```

### Rate Limiting

If you hit MCF API rate limits (403), lower the rate:

```bash
uv run mcf backfill-rich-fields --rate-limit 2
```

## What It Does

1. Queries jobs where `categories_json` is NULL or empty (MCF source only)
2. For each job, fetches detail from the MCF API
3. Updates the job row with: categories, employment types, position levels, salary min/max, posted date, expiry date, min years experience
4. Skips jobs that return 404 (removed from MCF)
5. Calls `update_daily_stats` at the end so the dashboard aggregate table is refreshed

## Duration

At 4 req/s, ~60k jobs ≈ 4+ hours. Run overnight or in batches.

## Output

```
Backfill Rich Fields
  Storage: Postgres: postgresql://...
  Jobs to backfill: 60,000
  Rate limit: 4 req/s

Backfilling... ████████████████████ 60000/60000 • 4:12:34 • 0:00:00

Backfill complete
  Updated: 58,200
  Skipped (404): 1,500
  Failed: 300
```
