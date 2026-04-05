# Local Crawl → Supabase Upload Workflow

Use this when you want to crawl locally (with GPU) and then upload to Supabase for a clean start.

---

## Step 1: Clear Supabase Database

1. Open [Supabase Dashboard](https://supabase.com/dashboard) → your project → **SQL Editor**
2. Open `scripts/clear_database.sql` from this project
3. Copy all contents and paste into the SQL Editor
4. Click **Run**

This wipes all job data, user profiles, and interactions. You get a clean slate.

---

## Step 2: Crawl Locally to DuckDB

Run the crawl on your machine (GPU will speed up embeddings):

```bash
# Set your DuckDB path (default: data/mcf.duckdb)
# Do NOT set DATABASE_URL — we want to write to local DuckDB

# Option A: Careers@Gov only (~2k jobs, quick)
uv run mcf crawl-incremental --db data/mcf.duckdb --source cag

# Option B: MyCareersFuture — one category for testing
uv run mcf crawl-incremental --db data/mcf.duckdb --source mcf --categories "Information Technology" --limit 500

# Option C: Full MCF — run 5 times (see docs/CRAWL_STRATEGY.md for category list)
uv run mcf crawl-incremental --db data/mcf.duckdb --source mcf --categories "Accounting / Auditing / Taxation,..."
# ... repeat for runs 2–5
```

---

## Step 3: Export to Supabase

```bash
# Set your Supabase connection string
export DATABASE_URL="postgresql://postgres.xxx:password@...?sslmode=require"

# Export DuckDB → Supabase
uv run mcf export-to-postgres --db data/mcf.duckdb --db-url "$DATABASE_URL"
```

On Windows PowerShell:

```powershell
$env:DATABASE_URL = "postgresql://postgres.xxx:password@...?sslmode=require"
uv run mcf export-to-postgres --db data/mcf.duckdb --db-url $env:DATABASE_URL
```

---

## Step 4: (Optional) Run pgvector Migration

If you want fast vector search, run `scripts/migrations/001_add_pgvector.sql` in Supabase SQL Editor. This backfills the vector column from `embedding_json` and creates indexes.

If the HNSW index times out, set `statement_timeout` first or use IVFFlat (see DEPLOYMENT.md troubleshooting).

---

## Summary

| Step | Command / Action |
|------|------------------|
| 1. Clear DB | Run `scripts/clear_database.sql` in Supabase |
| 2. Local crawl | `uv run mcf crawl-incremental --db data/mcf.duckdb --source cag` (or mcf) |
| 3. Export | `uv run mcf export-to-postgres --db data/mcf.duckdb --db-url $DATABASE_URL` |
| 4. pgvector | Run `scripts/migrations/001_add_pgvector.sql` (optional) |
