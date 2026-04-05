-- PostgreSQL schema for MCF Job Matcher
-- Run once against your Supabase/Postgres instance:
--   psql $DATABASE_URL -f scripts/schema.sql

-- Crawl runs
CREATE TABLE IF NOT EXISTS crawl_runs (
  run_id TEXT PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  kind TEXT,
  categories_json TEXT,
  total_seen INTEGER DEFAULT 0,
  added INTEGER DEFAULT 0,
  maintained INTEGER DEFAULT 0,
  removed INTEGER DEFAULT 0
);

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
  job_uuid TEXT PRIMARY KEY,
  job_source TEXT NOT NULL DEFAULT 'mcf',
  first_seen_run_id TEXT,
  last_seen_run_id TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  first_seen_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  title TEXT,
  company_name TEXT,
  location TEXT,
  job_url TEXT,
  skills_json TEXT,
  role_cluster INTEGER,
  predicted_tier TEXT,
  role_clusters_json TEXT  -- JSON array of all cluster IDs at cosine >= 0.85
);

-- Job run status
CREATE TABLE IF NOT EXISTS job_run_status (
  run_id TEXT NOT NULL,
  job_uuid TEXT NOT NULL,
  status TEXT NOT NULL,
  PRIMARY KEY (run_id, job_uuid)
);

-- Job embeddings (vector stored as JSON text for portability)
CREATE TABLE IF NOT EXISTS job_embeddings (
  job_uuid TEXT PRIMARY KEY,
  model_name TEXT,
  embedding_json TEXT NOT NULL,
  dim INTEGER,
  embedded_at TIMESTAMPTZ
);

-- User interactions with jobs
CREATE TABLE IF NOT EXISTS job_interactions (
  user_id TEXT NOT NULL,
  job_uuid TEXT NOT NULL,
  interaction_type TEXT NOT NULL,
  interacted_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (user_id, job_uuid, interaction_type)
);

-- Users (user_id matches Supabase auth.users UUID)
CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  email TEXT UNIQUE,
  role TEXT DEFAULT 'candidate',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_login TIMESTAMPTZ
);

-- Candidate profiles
CREATE TABLE IF NOT EXISTS candidate_profiles (
  profile_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  raw_resume_text TEXT,
  expanded_profile_json TEXT,
  skills_json TEXT,
  experience_json TEXT,
  resume_storage_path TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Candidate embeddings
-- profile_id may carry a ':taste' suffix to store the taste-profile embedding
-- alongside the resume embedding without a schema change.
CREATE TABLE IF NOT EXISTS candidate_embeddings (
  profile_id TEXT PRIMARY KEY,
  model_name TEXT,
  embedding_json TEXT NOT NULL,
  dim INTEGER,
  embedded_at TIMESTAMPTZ,
  embedding_type TEXT DEFAULT 'resume'
);

-- Match records (for analytics / history)
CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL,
  job_uuid TEXT NOT NULL,
  similarity_score FLOAT,
  match_type TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_jobs_active       ON jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen    ON jobs(last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_source       ON jobs(job_source);
CREATE INDEX IF NOT EXISTS idx_crawl_runs_fin    ON crawl_runs(finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_jrs_run           ON job_run_status(run_id);
CREATE INDEX IF NOT EXISTS idx_jrs_job           ON job_run_status(job_uuid);
CREATE INDEX IF NOT EXISTS idx_interactions_uj   ON job_interactions(user_id, job_uuid);
CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
CREATE INDEX IF NOT EXISTS idx_profiles_user     ON candidate_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_matches_profile   ON matches(profile_id);
CREATE INDEX IF NOT EXISTS idx_matches_job       ON matches(job_uuid);
