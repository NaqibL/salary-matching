-- Migration 018: index company lookup columns (see .claude/plans/db-performance-fixes.md)
-- Fixes 205-454s Parallel Seq Scans on:
--   WHERE company_canonical = %s OR (company_canonical IS NULL AND company_name = %s)
--
-- CONCURRENTLY cannot run inside a transaction block, so this file is NOT run
-- through PostgresStore.ensure_schema() (which wraps its migrations in one
-- transaction). Run this manually against Supabase, e.g. via the SQL editor
-- or `psql "$DATABASE_URL" -f scripts/migrations/018_add_company_indexes.sql`.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_company_canonical
  ON jobs (company_canonical);

-- Partial: only covers the OR branch that's actually taken when
-- company_canonical is NULL, keeping the index small.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_company_name
  ON jobs (company_name) WHERE company_canonical IS NULL;
