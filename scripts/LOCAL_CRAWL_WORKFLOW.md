# Local Crawl → Supabase Workflow

Use this when you want to crawl locally (with GPU) and write directly to Supabase.

---

## Step 1: Clear Supabase Database (if needed)

1. Open [Supabase Dashboard](https://supabase.com/dashboard) → your project → **SQL Editor**
2. Open `scripts/clear_database.sql` from this project
3. Copy all contents, paste into the SQL Editor, and click **Run**

---

## Step 2: Crawl Directly to Supabase

Set `DATABASE_URL` in your `.env` (or export it), then crawl:

```bash
# Option A: Careers@Gov only (~2k jobs, quick)
uv run mcf crawl-incremental --source cag

# Option B: MyCareersFuture — one category for testing
uv run mcf crawl-incremental --source mcf --categories "Information Technology" --limit 500

# Option C: Full MCF
uv run mcf crawl-incremental --source mcf --categories "Accounting / Auditing / Taxation,..."
```

`DATABASE_URL` is read automatically from the environment. You can also pass it explicitly with `--db-url`.

---

## Step 3: (Optional) Run pgvector Migration

If you want fast vector search, run `scripts/migrations/001_add_pgvector.sql` in the Supabase SQL Editor. This backfills the vector column from `embedding_json` and creates indexes.

---

## Summary

| Step | Command / Action |
|------|------------------|
| 1. Clear DB | Run `scripts/clear_database.sql` in Supabase (optional) |
| 2. Crawl | `uv run mcf crawl-incremental --source cag` (or mcf) |
| 3. pgvector | Run `scripts/migrations/001_add_pgvector.sql` (optional) |
