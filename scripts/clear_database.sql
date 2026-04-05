-- Clear all MCF Job Matcher data for a clean start
-- Run in Supabase SQL Editor: copy-paste and execute
-- WARNING: This deletes ALL data. Users will need to re-upload resumes.
-- Note: Supabase Storage (resumes bucket) is NOT cleared. Clear it manually in Storage if needed.

-- Truncate in order (no foreign keys, but order avoids any edge cases)
TRUNCATE TABLE job_run_status;
TRUNCATE TABLE job_embeddings;
TRUNCATE TABLE job_interactions;
TRUNCATE TABLE matches;
TRUNCATE TABLE candidate_embeddings;
TRUNCATE TABLE candidate_profiles;
TRUNCATE TABLE jobs;
TRUNCATE TABLE crawl_runs;
TRUNCATE TABLE users;

-- Reclaim disk space
VACUUM job_run_status;
VACUUM job_embeddings;
VACUUM job_interactions;
VACUUM matches;
VACUUM candidate_embeddings;
VACUUM candidate_profiles;
VACUUM jobs;
VACUUM crawl_runs;
VACUUM users;
