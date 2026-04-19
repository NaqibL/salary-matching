-- Migration 013: fix RPC functions broken by migration 012 (job_source column drop)
-- Run in Supabase SQL Editor.

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
  SELECT result_json, expires_at INTO v_result, v_expires_at
  FROM rpc_result_cache
  WHERE cache_key = v_cache_key;

  IF v_result IS NOT NULL AND v_expires_at > NOW() THEN
    RETURN v_result;
  END IF;

  WITH mcf AS (
    SELECT
      COUNT(*)::int AS total,
      COUNT(*) FILTER (WHERE is_active = TRUE)::int AS active,
      COUNT(*) FILTER (WHERE is_active = FALSE)::int AS inactive
    FROM jobs
  ),
  emb AS (
    SELECT COUNT(*)::int AS cnt
    FROM jobs j
    JOIN job_embeddings e ON e.job_uuid = j.job_uuid
    WHERE j.is_active = TRUE
  ),
  backfill AS (
    SELECT COUNT(*)::int AS cnt
    FROM jobs
    WHERE is_active = TRUE
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

  INSERT INTO rpc_result_cache (cache_key, result_json, expires_at)
  VALUES (v_cache_key, v_result, NOW() + interval '5 minutes')
  ON CONFLICT (cache_key) DO UPDATE SET
    result_json = EXCLUDED.result_json,
    expires_at = EXCLUDED.expires_at;

  RETURN v_result;
END;
$$;

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
    AND (e.embedding_json IS NOT NULL OR e.embedding IS NOT NULL)
    AND NOT EXISTS (
      SELECT 1 FROM job_interactions i
      WHERE i.user_id = p_user_id AND i.job_uuid = j.job_uuid
    )
  ORDER BY j.last_seen_at DESC NULLS LAST
  LIMIT p_limit;
END;
$$;
