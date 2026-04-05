-- Remove all CAG (Careers@Gov) data from Supabase
-- Run in Supabase SQL Editor: copy-paste and execute
-- This keeps MCF jobs and all user data (profiles, interactions, matches for MCF jobs).

-- Delete in order: child tables first, then jobs
DELETE FROM job_interactions
WHERE job_uuid IN (SELECT job_uuid FROM jobs WHERE job_source = 'cag');

DELETE FROM matches
WHERE job_uuid IN (SELECT job_uuid FROM jobs WHERE job_source = 'cag');

DELETE FROM job_embeddings
WHERE job_uuid IN (SELECT job_uuid FROM jobs WHERE job_source = 'cag');

DELETE FROM job_run_status
WHERE job_uuid IN (SELECT job_uuid FROM jobs WHERE job_source = 'cag');

DELETE FROM jobs
WHERE job_source = 'cag';

-- Optional: reclaim disk space (run after if you want)
-- VACUUM jobs;
-- VACUUM job_embeddings;
-- VACUUM job_run_status;
-- VACUUM job_interactions;
-- VACUUM matches;
