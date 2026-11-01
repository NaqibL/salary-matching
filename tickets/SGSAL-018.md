---
id: SGSAL-018
project: salary-matching
title: Write DB admin guide covering disk, vacuuming, and index management
status: done
priority: medium
type: chore
labels: [database, documentation, ops]
created: 2026-06-16
updated: 2026-06-16
depends_on: []
blocks: []
---

## Summary

After the v2 re-embed backfill caused disk to spike to the Supabase limit, we need a db-agent-readable ops guide so future large DB operations don't hit the same pitfalls.

## Problems encountered (2026-06-16)

1. **UPDATE bloat** — 167k UPDATEs on 768-dim embedding column created ~500 MB of dead tuples, doubling disk usage temporarily and hitting the Supabase limit
2. **VACUUM FULL + HNSW** — VACUUM FULL took 2.5 hours because it had to rebuild the HNSW index inline; index rebuild stalled at 50% for 1+ hour
3. **embeddings_cache table** — 264k rows of stale v1 JSON embeddings (~3.2 GB) had accumulated unnoticed
4. **CREATE INDEX CONCURRENTLY cancellation** — cancelling leaves an invalid index behind with lingering worker PIDs that hold locks, blocking DROP INDEX

## Guide to write

Create `.claude/agents/db-ops.md` (or extend `db-agent.md`) covering:

### Disk management
- Supabase reports **database disk** (Postgres heap + indexes + WAL), not Storage (S3 buckets)
- 8 GB gp3 quota for database data; 12 GB total provisioned volume (remainder is OS/WAL overhead)
- Check table sizes: `SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) FROM pg_class WHERE relkind = 'r' ORDER BY pg_total_relation_size(oid) DESC`

### Postgres MVCC bloat
- Every UPDATE writes a new row version and leaves the old one as a dead tuple
- Dead tuples count toward disk until autovacuum cleans them up
- For full-table re-embeds: prefer TRUNCATE + INSERT over UPDATE to avoid doubling disk usage
- Regular VACUUM marks space reusable but doesn't shrink files; VACUUM FULL rewrites the table and frees disk

### VACUUM FULL
- Requires exclusive lock — blocks all reads/writes on the table while running
- Must run with `statement_timeout = 0` and `autocommit = True` (cannot run inside a transaction)
- Drop HNSW index before VACUUM FULL — otherwise VACUUM rebuilds it inline, adding hours
- Monitor progress via `pg_stat_progress_cluster` (not `pg_stat_progress_vacuum`)
- Check active sessions via `pg_stat_activity WHERE query ILIKE '%vacuum%'`

### HNSW index management
- Build time: 4–5+ hours for 172k × 768-dim on Supabase shared compute
- Always use `CREATE INDEX CONCURRENTLY` — avoids exclusive lock during build
- If cancelled: leaves an invalid index (`indisvalid = false`) + lingering worker PIDs
- Cleanup sequence: `pg_terminate_backend(pid)` for workers → `DROP INDEX` → retry
- Monitor build progress via `pg_stat_progress_create_index`

### Routine checks
- Monitor `embeddings_cache` table — it accumulates stale entries and can grow to GBs unnoticed
- After any large backfill, run `VACUUM ANALYZE <table>` to update planner stats
- After VACUUM FULL, Supabase disk usage drops immediately (unlike regular VACUUM)
