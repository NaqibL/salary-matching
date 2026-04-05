-- Migration 010: add role_clusters_json for multi-label role tagging
-- At cosine similarity >= 0.85, 45% of jobs belong to 2+ clusters.
-- role_clusters_json stores all matching cluster IDs (INTEGER array).
-- Enables: filter by role C17 also surfaces jobs tagged [C17, C27] etc.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_clusters_json INTEGER[];

-- GIN index for fast array overlap queries (&&)
CREATE INDEX IF NOT EXISTS idx_jobs_role_clusters_gin ON jobs USING gin(role_clusters_json);
