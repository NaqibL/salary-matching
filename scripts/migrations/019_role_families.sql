-- Migration 019: Jev role families (SGSAL-022 C3)
--
-- Replaces the KMeans role clusters / LR tier model with Jev-assigned
-- role families. jobs.role_cluster and jobs.predicted_tier are KEPT and now
-- hold role_families.id and the Jev tier so the matches filters keep working.
--
-- Safe to run while the API is up (nullable columns, IF NOT EXISTS). Also
-- applied automatically by PostgresStore.ensure_schema(); the seed rows for
-- role_families come from mcf.lib.embeddings.jev_classifier.role_family_rows().

CREATE TABLE IF NOT EXISTS role_families (
    id           INTEGER PRIMARY KEY,
    key          TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description  TEXT NOT NULL
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_family TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_conf REAL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tier_conf REAL;

CREATE INDEX IF NOT EXISTS idx_jobs_role_family ON jobs (role_family) WHERE is_active = TRUE;
