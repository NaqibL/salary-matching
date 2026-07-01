# DB Ops Guide

Operational reference for Supabase Postgres — disk management, vacuuming, and HNSW index maintenance. Born from the v2 re-embed incident (2026-06-16) where a full-table UPDATE spiked disk to the Supabase limit.

---

## Disk management

Supabase reports **database disk** (Postgres heap + indexes + WAL), not Storage (S3 buckets). These are separate quotas.

- 8 GB gp3 quota for database data; 12 GB total provisioned volume (remainder is OS/WAL overhead)

Check table sizes:

```sql
SELECT relname, pg_size_pretty(pg_total_relation_size(oid))
FROM pg_class
WHERE relkind = 'r'
ORDER BY pg_total_relation_size(oid) DESC;
```

Watch `embeddings_cache` — it accumulates stale entries silently and can grow to GBs unnoticed.

---

## Postgres MVCC bloat

Every UPDATE writes a new row version and leaves the old one as a dead tuple. Dead tuples count toward disk until autovacuum cleans them up.

**For full-table re-embeds: use TRUNCATE + INSERT, not UPDATE.** UPDATE on 172k × 768-dim rows creates ~500 MB of dead tuples and temporarily doubles disk usage.

- Regular `VACUUM` marks dead tuple space as reusable but does not shrink files on disk
- `VACUUM FULL` rewrites the table and frees disk — use this after a bloat incident
- After any large backfill: `VACUUM ANALYZE <table>` to update planner stats

---

## VACUUM FULL

**Requirements:**
- Requires exclusive lock — blocks all reads and writes on the table while running
- Must run with `statement_timeout = 0` (default will time out on large tables)
- Must run with `autocommit = True` — cannot execute inside a transaction

**Always drop the HNSW index first.** VACUUM FULL rebuilds all indexes inline. On `job_embeddings` this adds 4–5+ hours and stalls at ~50% for an hour or more. Drop the index, VACUUM, then rebuild separately.

```sql
-- 1. Drop index first
DROP INDEX idx_job_embeddings_vector;

-- 2. VACUUM FULL (run outside a transaction, with autocommit)
SET statement_timeout = 0;
VACUUM FULL job_embeddings;

-- 3. Rebuild index afterward (see HNSW section)
```

Monitor progress (VACUUM FULL uses cluster internals, not the vacuum view):

```sql
SELECT * FROM pg_stat_progress_cluster;
```

Check if it's still running:

```sql
SELECT pid, query, state, wait_event
FROM pg_stat_activity
WHERE query ILIKE '%vacuum%';
```

Disk usage drops immediately after VACUUM FULL completes (unlike regular VACUUM).

---

## HNSW index management

Current index: `idx_job_embeddings_vector` on `job_embeddings.embedding` (`vector_cosine_ops`, `m=16`, `ef_construction=64`)

**Build time:** 4–5+ hours for 172k × 768-dim on Supabase shared compute. Run overnight.

**Always use `CREATE INDEX CONCURRENTLY`** — avoids the exclusive lock that `CREATE INDEX` would take, so production queries continue during the build.

```sql
SET statement_timeout = 0;
CREATE INDEX CONCURRENTLY idx_job_embeddings_vector
ON job_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

Verify after build:

```sql
SELECT indexname, indisvalid
FROM pg_indexes
JOIN pg_class ON relname = indexname
JOIN pg_index ON indexrelid = pg_class.oid
WHERE tablename = 'job_embeddings';
```

**If the build is cancelled mid-run:**

`CREATE INDEX CONCURRENTLY` leaves an invalid index behind (`indisvalid = false`) and lingering worker PIDs that hold locks, blocking `DROP INDEX`. Cleanup sequence:

```sql
-- 1. Find and terminate worker PIDs
SELECT pid, query FROM pg_stat_activity WHERE query ILIKE '%idx_job_embeddings_vector%';
SELECT pg_terminate_backend(<pid>);

-- 2. Drop the invalid index
DROP INDEX idx_job_embeddings_vector;

-- 3. Retry the build
```

Monitor build progress:

```sql
SELECT * FROM pg_stat_progress_create_index;
```

---

## Routine checks

After any large backfill:

```sql
VACUUM ANALYZE job_embeddings;
VACUUM ANALYZE embeddings_cache;
```

Check for stale `embeddings_cache` bloat:

```sql
SELECT COUNT(*), pg_size_pretty(pg_total_relation_size('embeddings_cache'))
FROM embeddings_cache;
```

Truncate if stale (cache is regenerated on demand):

```sql
TRUNCATE embeddings_cache;
```
