-- Migration 012: streamline schema
-- Removes dead columns, fixes broken embedding state, creates missing tables,
-- trims crawl tracking bloat.
-- Run in Supabase SQL Editor.

-- 1. Drop dead columns from jobs
--    job_source: all MCF, multi-source code path never used
--    min_years_experience: never read in any query, matching, or display
--    (skills_json kept: displayed in job detail UI)
--    (position_levels_json kept: feeds job_daily_stats aggregation in dashboard)
ALTER TABLE jobs DROP COLUMN IF EXISTS job_source;
ALTER TABLE jobs DROP COLUMN IF EXISTS min_years_experience;

-- 2. Drop legacy columns from candidate_embeddings
--    embedding_json: legacy TEXT fallback, job_embeddings already dropped it
--    embedding_type: never used; :taste suffix on profile_id is the mechanism
ALTER TABLE candidate_embeddings DROP COLUMN IF EXISTS embedding_json;
ALTER TABLE candidate_embeddings DROP COLUMN IF EXISTS embedding_type;

-- 3. Fix broken embedding data
--    Remove stale 384-dim job embeddings (old bge-small model, wrong for current 768-dim search)
DELETE FROM job_embeddings WHERE dim = 384 OR dim IS NULL;

--    Clear all candidate embeddings — all rows have NULL vectors (broken state).
--    Users must re-upload resume to get fresh 768-dim embeddings.
TRUNCATE candidate_embeddings;

-- 4. Trim job_run_status to last 30 days (was 478K rows)
DELETE FROM job_run_status
WHERE run_id IN (
    SELECT run_id FROM crawl_runs
    WHERE started_at < NOW() - INTERVAL '30 days'
);

-- 5. Create embeddings_cache table (migration 004 was never applied)
CREATE TABLE IF NOT EXISTS embeddings_cache (
  content_hash   TEXT NOT NULL,
  model_name     TEXT NOT NULL,
  embed_type     TEXT NOT NULL,
  embedding_json TEXT NOT NULL,
  dim            INTEGER,
  cached_at      TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (content_hash, model_name, embed_type)
);
CREATE INDEX IF NOT EXISTS idx_embeddings_cache_lookup
  ON embeddings_cache(content_hash, model_name, embed_type);

-- 6. Create cache_metadata table (migration 007 was never applied)
CREATE TABLE IF NOT EXISTS cache_metadata (
  key        TEXT PRIMARY KEY,
  value_json JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
