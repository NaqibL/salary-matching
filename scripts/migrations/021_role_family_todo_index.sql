-- Migration 021: work-queue index for the Jev role-family backfill (SGSAL-022 C5)
--
-- scripts/backfill_role_families.py (also run daily by daily-embed.yml) selects
--   WHERE is_active AND role_family IS NULL ORDER BY job_uuid LIMIT n
-- With only idx_jobs_role_family (role_family, partial on is_active) every
-- batch re-read ~15k candidate heap rows to sort them, and the pkey walk had
-- to skip every already-classified row first: batches went from 30 s to
-- 90 s+ as the backfill advanced (2026-11-07). This partial index holds only
-- the unclassified rows, already in job_uuid order, so a batch touches n rows.
-- It shrinks to ~0 once the backlog is done and grows by one day's crawl.
--
-- Applied to Supabase 2026-11-07 with CONCURRENTLY. Also created by
-- PostgresStore.ensure_schema() (non-concurrent, IF NOT EXISTS) for new DBs.

CREATE INDEX IF NOT EXISTS idx_jobs_role_family_todo
  ON jobs (job_uuid)
  WHERE is_active = TRUE AND role_family IS NULL;
