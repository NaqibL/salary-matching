-- Migration 020: index for the skills-trend dashboard query
--
-- /api/dashboard/skills-trend-public buckets jobs by
-- COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date) over the last N weeks, across
-- ALL rows (active or not — a trend needs expired postings too). jobs is
-- ~700k rows / 1.6 GB, so without an index that is a full seq scan (~3-6 s
-- cold). Recent rows sit at the end of the heap, so a bitmap scan on this
-- expression index touches roughly half the pages.
--
-- The seniority / top-skills / role-family queries only touch active rows
-- (idx_jobs_active) and need nothing new.
--
-- NOT applied automatically by PostgresStore.ensure_schema(). Run manually
-- in the Supabase SQL editor (CONCURRENTLY so the crawl is not blocked):
--
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_posted_or_seen_date
--     ON jobs ((COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date)))
--     WHERE llm_fields_json IS NOT NULL;
--
-- (CONCURRENTLY cannot run inside a transaction block, hence the manual step.)
--
-- first_seen_at is TIMESTAMPTZ: a plain ::date cast depends on the session
-- time zone and is not IMMUTABLE, so Postgres rejects it in an index
-- expression. AT TIME ZONE 'UTC' makes it immutable; the dashboard query in
-- postgres_store.py uses the identical expression so the index is matched.
-- Applied to Supabase 2026-11-07.

CREATE INDEX IF NOT EXISTS idx_jobs_posted_or_seen_date
  ON jobs ((COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date)))
  WHERE llm_fields_json IS NOT NULL;
