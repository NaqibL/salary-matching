-- Cache metadata for last crawl/cache update timestamp.
-- Run: psql $DATABASE_URL -f scripts/migrations/007_cache_metadata.sql

CREATE TABLE IF NOT EXISTS cache_metadata (
  key TEXT PRIMARY KEY,
  value_json JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
