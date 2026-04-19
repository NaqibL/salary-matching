-- Migration 014: archive stale non-embedded jobs
-- Jobs with no embedding and not seen in 90 days are dead weight.
-- The matching query already filters is_active=TRUE + JOIN job_embeddings,
-- so this is cleanup only — no behaviour change.
-- Run in Supabase SQL Editor or via psql.

UPDATE jobs
SET is_active = FALSE
WHERE is_active = TRUE
  AND job_uuid NOT IN (SELECT job_uuid FROM job_embeddings)
  AND (last_seen_at < NOW() - INTERVAL '90 days' OR last_seen_at IS NULL);
