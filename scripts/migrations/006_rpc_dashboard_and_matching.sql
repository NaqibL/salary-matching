-- Supabase RPC functions for expensive queries with optional function-level caching.
-- Call via supabase.rpc('get_dashboard_summary') or supabase.rpc('get_active_jobs_for_matching', { p_limit: 5000 })
-- Run: psql $DATABASE_URL -f scripts/migrations/006_rpc_dashboard_and_matching.sql

-- Cache table for RPC results (TTL-based)
CREATE TABLE IF NOT EXISTS rpc_result_cache (
  cache_key TEXT PRIMARY KEY,
  result_json JSONB NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rpc_cache_expires ON rpc_result_cache(expires_at);

-- Dashboard summary: total/active/inactive jobs, embeddings count, backfill count.
-- Cached 5 minutes. Use for dashboard cards.
CREATE OR REPLACE FUNCTION get_dashboard_summary()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_result JSONB;
  v_expires_at TIMESTAMPTZ;
  v_cache_key TEXT := 'dashboard_summary';
BEGIN
  -- Check cache
  SELECT result_json, expires_at INTO v_result, v_expires_at
  FROM rpc_result_cache
  WHERE cache_key = v_cache_key;

  IF v_result IS NOT NULL AND v_expires_at > NOW() THEN
    RETURN v_result;
  END IF;

  -- Compute
  WITH mcf AS (
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE is_active = TRUE)::int AS active,
      COUNT(*) FILTER (WHERE is_active = FALSE)::int AS inactive
    FROM jobs
    WHERE (job_source = 'mcf' OR job_source IS NULL)
  ),
  emb AS (
    SELECT COUNT(*)::int AS cnt
    FROM jobs j
    JOIN job_embeddings e ON e.job_uuid = j.job_uuid
    WHERE j.is_active = TRUE
      AND (j.job_source = 'mcf' OR j.job_source IS NULL)
  ),
  backfill AS (
    SELECT COUNT(*)::int AS cnt
    FROM jobs
    WHERE is_active = TRUE
      AND (job_source = 'mcf' OR job_source IS NULL)
      AND (categories_json IS NULL OR categories_json = '' OR categories_json = '[]')
  )
  SELECT jsonb_build_object(
    'total_jobs', m.total,
    'active_jobs', m.active,
    'inactive_jobs', m.inactive,
    'by_source', jsonb_build_object('mcf', m.total),
    'jobs_with_embeddings', e.cnt,
    'jobs_needing_backfill', b.cnt
  ) INTO v_result
  FROM mcf m, emb e, backfill b;

  -- Cache 5 minutes
  INSERT INTO rpc_result_cache (cache_key, result_json, expires_at)
  VALUES (v_cache_key, v_result, NOW() + interval '5 minutes')
  ON CONFLICT (cache_key) DO UPDATE SET
    result_json = EXCLUDED.result_json,
    expires_at = EXCLUDED.expires_at;

  RETURN v_result;
END;
$$;

COMMENT ON FUNCTION get_dashboard_summary() IS
  'Dashboard summary stats. Cached 5 min. Call via supabase.rpc(''get_dashboard_summary'').';

-- Active job UUIDs for matching, excluding user interactions.
-- No DB cache (user-specific). Next.js should use SWR/revalidate.
-- Use auth.uid()::text when calling from Supabase to avoid passing user_id from client.
CREATE OR REPLACE FUNCTION get_active_jobs_for_matching(
  p_user_id TEXT,
  p_limit INT DEFAULT 5000
)
RETURNS TABLE (job_uuid TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT j.job_uuid
  FROM jobs j
  JOIN job_embeddings e ON e.job_uuid = j.job_uuid
  WHERE j.is_active = TRUE
    AND (j.job_source = 'mcf' OR j.job_source IS NULL)
    AND (e.embedding_json IS NOT NULL OR e.embedding IS NOT NULL)
    AND NOT EXISTS (
      SELECT 1 FROM job_interactions i
      WHERE i.user_id = p_user_id AND i.job_uuid = j.job_uuid
    )
  ORDER BY j.last_seen_at DESC NULLS LAST
  LIMIT p_limit;
END;
$$;

COMMENT ON FUNCTION get_active_jobs_for_matching(TEXT, INT) IS
  'Job UUIDs for matching pool, excluding user interactions. Call via supabase.rpc(''get_active_jobs_for_matching'', { p_user_id, p_limit }).';

-- Optional: invalidate dashboard cache when crawl completes (call from refresh_dashboard_materialized_views or separately)
CREATE OR REPLACE FUNCTION invalidate_rpc_cache(p_key TEXT DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF p_key IS NULL THEN
    DELETE FROM rpc_result_cache WHERE expires_at < NOW();
  ELSE
    DELETE FROM rpc_result_cache WHERE cache_key = p_key;
  END IF;
END;
$$;
