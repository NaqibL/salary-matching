-- scripts/migrations/026_company_stats_v2.sql
-- SGSAL-028: company_stats v2. Joins the companies registry (migration 025) so each company
-- carries its registered SSIC industry and `is_agency` (SSIC 78xxx = employment agencies — the
-- ONLY source of the "Recruitment agency" label; never name keywords). Adds per-role-family
-- salary medians (family_medians / family_salary_n) and top_family_share. Drops likely_agency.
--
-- Apply to Supabase BY HAND (drop + rebuild, ~25 s). ensure_schema() carries the CREATE copy.

DROP MATERIALIZED VIEW IF EXISTS company_stats;

CREATE MATERIALIZED VIEW IF NOT EXISTS company_stats AS
WITH base AS (
    SELECT j.job_uuid,
           lower(COALESCE(j.company_canonical, j.company_name)) AS company_key,
           COALESCE(j.company_canonical, j.company_name)        AS company,
           j.is_active, j.first_seen_at, j.last_seen_at,
           COALESCE(j.content_hash, j.job_uuid)                 AS posting_key,
           COALESCE(j.role_family, 'other')                     AS role_family,
           CASE WHEN j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
                THEN (j.salary_min + j.salary_max) / 2
                ELSE j.salary_min END                           AS salary_mid,
           j.categories_json,
           pg.repost_count, pg.distinct_companies,
           c.ssic_code_2020, c.ssic_description,
           (c.ssic_code_2020 LIKE '78%'
            OR (c.ssic_code_2020 IS NULL AND c.ssic_code LIKE '78%'))  AS agency_row
      FROM jobs j
      LEFT JOIN posting_groups pg ON pg.content_hash = j.content_hash
      LEFT JOIN companies c ON c.company_key = lower(j.company_name)
     WHERE j.company_name IS NOT NULL
       AND COALESCE(j.company_canonical, j.company_name) NOT IN
           (SELECT canonical_name FROM company_aliases WHERE is_excluded = TRUE)
), fam AS (
    SELECT company_key,
           jsonb_object_agg(role_family, n)                                  AS role_family_counts,
           count(*)::int                                                     AS family_count,
           (array_agg(role_family ORDER BY n DESC, role_family))[1]          AS top_family,
           (array_agg(n ORDER BY n DESC, role_family))[1]                    AS top_family_n
      FROM (SELECT company_key, role_family, count(*)::int AS n
              FROM base WHERE is_active GROUP BY 1, 2) f
     GROUP BY company_key
), famsal AS (
    SELECT company_key,
           jsonb_object_agg(role_family, med) AS family_medians,
           jsonb_object_agg(role_family, n)   AS family_salary_n
      FROM (SELECT company_key, role_family,
                   (percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_mid))::int AS med,
                   count(*)::int AS n
              FROM base WHERE is_active AND salary_mid IS NOT NULL GROUP BY 1, 2) x
     GROUP BY company_key
), cat AS (
    SELECT company_key, jsonb_object_agg(category, n) AS category_counts
      FROM (SELECT b.company_key, c.category, count(*)::int AS n
              FROM (SELECT company_key, categories_json FROM base
                     WHERE is_active AND categories_json LIKE '[%') b,
                   jsonb_array_elements_text(b.categories_json::jsonb) AS c(category)
             GROUP BY 1, 2) x
     GROUP BY company_key
), agg AS (
    SELECT company_key,
           mode() WITHIN GROUP (ORDER BY company)                                       AS company,
           (count(*) FILTER (WHERE is_active))::int                                     AS active_count,
           (count(DISTINCT posting_key) FILTER (WHERE is_active))::int                  AS distinct_postings,
           (count(*) FILTER (WHERE is_active AND repost_count >= 2))::int               AS reposted_count,
           (count(*) FILTER (WHERE is_active AND distinct_companies >= 2))::int         AS multi_company_count,
           COALESCE(max(repost_count) FILTER (WHERE is_active), 1)::int                 AS max_repost_count,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_mid)
                FILTER (WHERE is_active AND salary_mid IS NOT NULL))::int               AS median_salary,
           (count(salary_mid) FILTER (WHERE is_active))::int                            AS salary_sample,
           count(*)::int                                                                AS total_seen,
           min(first_seen_at)                                                           AS first_seen,
           max(last_seen_at)                                                            AS last_seen,
           mode() WITHIN GROUP (ORDER BY ssic_code_2020)                                AS ssic_code_2020,
           mode() WITHIN GROUP (ORDER BY ssic_description)                              AS ssic_description,
           COALESCE(bool_or(agency_row), FALSE)                                         AS is_agency
      FROM base
     GROUP BY company_key
)
SELECT a.company_key, a.company, a.active_count, a.distinct_postings, a.reposted_count,
       a.multi_company_count, a.max_repost_count, a.median_salary, a.salary_sample,
       COALESCE(f.role_family_counts, '{}'::jsonb) AS role_family_counts,
       COALESCE(f.family_count, 0)                 AS family_count,
       f.top_family,
       CASE WHEN a.active_count > 0
            THEN round(COALESCE(f.top_family_n, 0)::numeric / a.active_count, 3) END AS top_family_share,
       COALESCE(fs.family_medians, '{}'::jsonb)    AS family_medians,
       COALESCE(fs.family_salary_n, '{}'::jsonb)   AS family_salary_n,
       COALESCE(c.category_counts, '{}'::jsonb)    AS category_counts,
       a.total_seen, a.first_seen, a.last_seen,
       a.ssic_code_2020, a.ssic_description, a.is_agency
  FROM agg a
  LEFT JOIN fam f USING (company_key)
  LEFT JOIN famsal fs USING (company_key)
  LEFT JOIN cat c USING (company_key)
 WHERE a.active_count > 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_stats_key ON company_stats (company_key);
CREATE INDEX IF NOT EXISTS idx_company_stats_active ON company_stats (active_count DESC);
