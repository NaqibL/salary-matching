-- Migration 016: index job_embeddings.embedded_at
-- get_active_jobs_embedded_since does WHERE embedded_at >= %s — without this
-- index Postgres full-scans job_embeddings and hits Supabase statement timeout.
CREATE INDEX IF NOT EXISTS idx_job_embeddings_embedded_at
  ON job_embeddings (embedded_at DESC);
