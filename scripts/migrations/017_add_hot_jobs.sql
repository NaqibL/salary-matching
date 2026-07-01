-- Migration 017: hot-jobs feature (SGSAL-019)
-- hot_jobs_cluster / above_market_pct: separate from the existing role_cluster
-- (35-cluster matching taxonomy, kmeans_role_v2.pkl) — this is a fresh k=23
-- K-means fit for peer-group salary comparison. Do not conflate the two.

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS hot_jobs_cluster INT,
  ADD COLUMN IF NOT EXISTS above_market_pct FLOAT;

CREATE TABLE IF NOT EXISTS hot_jobs_cluster_centroids (
  cluster_id  INT PRIMARY KEY,
  label       TEXT,          -- human-readable name, e.g. "Senior Software Engineers"
  centroid    vector(768) NOT NULL
);

CREATE TABLE IF NOT EXISTS hot_jobs_salary_profiles (
  cluster_id     INT,
  seniority      TEXT,
  salary_median  FLOAT,
  salary_p25     FLOAT,
  salary_p75     FLOAT,
  n_jobs         INT,
  viable         BOOLEAN,
  PRIMARY KEY (cluster_id, seniority)
);

-- Partial index for the hot-jobs query (Step 11) — only indexes rows the
-- page actually reads, safe to create after the backfill.
CREATE INDEX IF NOT EXISTS idx_jobs_hot_jobs
  ON jobs (above_market_pct DESC)
  WHERE is_active = TRUE AND above_market_pct IS NOT NULL;
