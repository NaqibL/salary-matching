-- scripts/migrations/022_posting_groups.sql
-- SGSAL-024: content-addressed embeddings + repost history.
--
-- jobs.content_hash        = posting_key(title, description) computed in Python
--                            (src/mcf/lib/pipeline/posting_key.py). NULL when no description.
-- jobs.canonical_job_uuid  = the job in the same group that owns the job_embeddings
--                            row / LLM fields / Jev labels (= job_uuid for the canonical).
-- posting_groups           = one row per content_hash, rebuilt at the end of each crawl
--                            (Storage.refresh_posting_groups) and by the backfill.
--
-- Apply to Supabase BY HAND, in this order, outside a transaction (CONCURRENTLY):
--   1) the two ALTER TABLE statements
--   2) the two CREATE INDEX CONCURRENTLY statements
--   3) the CREATE MATERIALIZED VIEW (populates: ~30 s) and its indexes
-- ensure_schema() carries IF NOT EXISTS / non-concurrent copies for fresh DBs only.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_job_uuid TEXT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_content_hash
  ON jobs (content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_canonical
  ON jobs (canonical_job_uuid) WHERE canonical_job_uuid IS NOT NULL;

CREATE MATERIALIZED VIEW IF NOT EXISTS posting_groups AS
WITH occ AS (
    SELECT job_uuid, content_hash, canonical_job_uuid, is_active, first_seen_at,
           COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date) AS occurrence_date,
           lower(COALESCE(company_canonical, company_name)) AS company_key,
           COALESCE(company_canonical, company_name) AS company,
           salary_min, salary_max
      FROM jobs
     WHERE content_hash IS NOT NULL
), ranked AS (
    SELECT occ.*,
           row_number() OVER (PARTITION BY content_hash
                              ORDER BY is_active DESC, occurrence_date DESC, first_seen_at DESC) AS rn
      FROM occ
)
SELECT content_hash,
       min(canonical_job_uuid)                                           AS canonical_job_uuid,
       max(job_uuid)    FILTER (WHERE rn = 1)                            AS latest_job_uuid,
       count(*)::int                                                     AS repost_count,
       (count(*) FILTER (WHERE is_active))::int                          AS active_count,
       min(occurrence_date)                                              AS first_posted,
       max(occurrence_date)                                              AS last_posted,
       (count(*) FILTER (WHERE occurrence_date >= current_date - 90))::int  AS reposts_90d,
       (count(*) FILTER (WHERE occurrence_date >= current_date - 365))::int AS reposts_365d,
       count(DISTINCT company_key)::int                                  AS distinct_companies,
       max(salary_min)  FILTER (WHERE rn = 1)                            AS latest_salary_min,
       max(salary_max)  FILTER (WHERE rn = 1)                            AS latest_salary_max,
       min(salary_min)                                                   AS min_salary_seen,
       max(salary_max)                                                   AS max_salary_seen,
       jsonb_agg(jsonb_build_object(
           'job_uuid', job_uuid, 'date', occurrence_date, 'company', company,
           'salary_min', salary_min, 'salary_max', salary_max, 'is_active', is_active)
           ORDER BY occurrence_date DESC, first_seen_at DESC)            AS occurrences
  FROM ranked
 GROUP BY content_hash;

CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_groups_hash ON posting_groups (content_hash);
CREATE INDEX IF NOT EXISTS idx_posting_groups_canonical ON posting_groups (canonical_job_uuid);
CREATE INDEX IF NOT EXISTS idx_posting_groups_reposts_365d ON posting_groups (reposts_365d DESC);
