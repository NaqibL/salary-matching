-- Migration 009: add role_cluster and predicted_tier to jobs table
-- role_cluster: K-Means cluster ID (0-34), maps to role taxonomy
-- predicted_tier: experience tier (T1_Entry / T2_Junior / T3_Senior / T4_Management)

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_cluster INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS predicted_tier TEXT;

-- Indexes for filtering/faceting
CREATE INDEX IF NOT EXISTS idx_jobs_role_cluster   ON jobs (role_cluster);
CREATE INDEX IF NOT EXISTS idx_jobs_predicted_tier ON jobs (predicted_tier);
