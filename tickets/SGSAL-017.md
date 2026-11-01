---
id: SGSAL-017
project: salary-matching
title: Rebuild HNSW index on job_embeddings
status: done
priority: medium
type: chore
labels: [database, performance, pgvector]
created: 2026-06-16
updated: 2026-06-16
depends_on: [SGSAL-015]
blocks: []
---

## Summary

The HNSW index on `job_embeddings.embedding` was dropped during the v2 re-embed backfill to unblock VACUUM FULL. Without it, cosine similarity queries do exact KNN scans across all 172k rows — slower per request but functionally correct.

## Context

- Index dropped: `idx_job_embeddings_vector` (hnsw, vector_cosine_ops)
- Previous params: `m = 16, ef_construction = 64`
- Build was taking 4–5+ hours on Supabase shared compute — do this overnight
- Use `CREATE INDEX CONCURRENTLY` so production queries are not blocked

## Steps

1. Run overnight when machine is idle:

```sql
SET statement_timeout = 0;
CREATE INDEX CONCURRENTLY idx_job_embeddings_vector
ON job_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

2. Verify it's valid after build:

```sql
SELECT indexname, indisvalid
FROM pg_indexes
JOIN pg_class ON relname = indexname
JOIN pg_index ON indexrelid = pg_class.oid
WHERE tablename = 'job_embeddings';
```

## Notes

- If cancelled mid-build, `CREATE INDEX CONCURRENTLY` leaves an **invalid** index behind
- Invalid index must be dropped before retrying: `DROP INDEX idx_job_embeddings_vector`
- Lingering worker PIDs may hold locks after cancellation — terminate them via `pg_terminate_backend(pid)` before dropping
- Index size expected: ~400–500 MB
