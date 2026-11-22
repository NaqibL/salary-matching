-- scripts/migrations/029_company_stats_v4.sql
-- SGSAL-032: company_stats v4.
--   1. "Typical pay" (median_salary, salary_sample, family_medians, family_salary_n) counts
--      full-time monthly ads only. Hourly and daily rates, part-time pay and internships are
--      counted in nonstandard_pay_count instead (rule: mcf.lib.companies.pay.pay_kind).
--   2. is_agency also covers a company whose own open ads carry an employment-agency licence
--      number (2+ ads): a licence fact stated by the company, not a name keyword.
--   3. hires_for_clients: not an agency, but 30%+ of its described open ads (10+) say the role
--      is with a client or that staff are deployed to one. Public bodies are never flagged.
-- Otherwise identical to migration 027.
--
-- market_stats reads company_stats, so it is dropped and rebuilt with it (definition unchanged,
-- migration 028). Applied automatically at the end of the next crawl
-- (Storage.upgrade_company_stats_view), in one transaction; or by hand with this file followed
-- by 028_market_stats.sql.

DROP MATERIALIZED VIEW IF EXISTS market_stats;
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
           -- pay kind (mcf.lib.companies.pay.pay_kind): hourly / daily rates and part-time or
           -- internship pay are kept out of "typical pay", which is full-time monthly only
           CASE WHEN j.salary_min IS NULL OR COALESCE(j.salary_max, j.salary_min) < 5 THEN NULL
                WHEN COALESCE(j.salary_max, j.salary_min) < 100 THEN 'hourly'
                WHEN COALESCE(j.salary_max, j.salary_min) < 500 THEN 'daily'
                WHEN j.employment_types_json ~* '"(full time|permanent)"' THEN 'standard'
                WHEN j.employment_types_json ~* '"part time"' THEN 'part_time'
                WHEN j.employment_types_json ~* '"internship' THEN 'internship'
                ELSE 'standard' END                             AS pay_kind,
           -- ad text, open ads only: an employment-agency licence number, or wording that
           -- says the role is with a client (thresholds applied per company below)
           (j.is_active AND j.description IS NOT NULL AND length(j.description) > 100)  AS described,
           (j.is_active AND j.description ~* '\mEA\s*(licen[cs]e|lic|reg|registration|personnel|no)\M|\m\d{2}C\d{4}\M') AS ea_ad,
           (j.is_active AND j.description ~* '\m(our|my) client(''s|’s)?\s*(,|is|are|has|in|based|located|-|–|:|who|which|seeks|seeking|requires|needs)|\mon behalf of (our|a|the|my) client\M|\mfor (our|my) client\M|\mpersonnel (to be|will be|shall be) deployed\M|\mname of authority\M|\m(to be|will be|shall be) (deployed|seconded|stationed) (to|at)\M|\moutsourced (staff|personnel|role|position|contract)\M') AS client_ad,
           (c.ssic_code_2020 ~ '^(72|84|85|86|91|94)'
            OR COALESCE(j.company_canonical, j.company_name) ~* 'ministry')             AS public_body_row,
           j.categories_json,
           pg.repost_count, pg.distinct_companies,
           c.ssic_code_2020, c.ssic_description,
           (c.ssic_code_2020 LIKE '78%'
            OR (c.ssic_code_2020 IS NULL AND c.ssic_code LIKE '78%')
            -- name rule, vetted by registration: only MCF companies whose SSIC is known and
            -- is not a public body (72 research, 84 public admin, 85 education, 86 health,
            -- 91 libraries/museums, 94 membership organisations) — keeps A*STAR, MOM,
            -- universities and hospitals out whatever their name says
            OR (c.source = 'mcf' AND c.ssic_code_2020 IS NOT NULL
                AND c.ssic_code_2020 !~ '^(72|84|85|86|91|94)'
                AND COALESCE(j.company_canonical, j.company_name)
                    ~* '(recruit|staffing|headhunt|employment agenc|personnel|human resource|\mhr\M|manpower)'
                AND COALESCE(j.company_canonical, j.company_name) !~* 'ministry'))  AS agency_row
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
              FROM base WHERE is_active AND salary_mid IS NOT NULL AND pay_kind = 'standard' GROUP BY 1, 2) x
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
                FILTER (WHERE is_active AND salary_mid IS NOT NULL AND pay_kind = 'standard'))::int AS median_salary,
           (count(salary_mid) FILTER (WHERE is_active AND pay_kind = 'standard'))::int  AS salary_sample,
           (count(*) FILTER (WHERE is_active AND pay_kind IS NOT NULL
                                   AND pay_kind <> 'standard'))::int                    AS nonstandard_pay_count,
           (count(*) FILTER (WHERE described))::int                                     AS described_ads,
           (count(*) FILTER (WHERE ea_ad))::int                                         AS ea_licence_ads,
           (count(*) FILTER (WHERE client_ad))::int                                     AS client_ads,
           COALESCE(bool_or(public_body_row), FALSE)                                    AS public_body,
           count(*)::int                                                                AS total_seen,
           min(first_seen_at)                                                           AS first_seen,
           max(last_seen_at)                                                            AS last_seen,
           mode() WITHIN GROUP (ORDER BY ssic_code_2020)                                AS ssic_code_2020,
           mode() WITHIN GROUP (ORDER BY ssic_description)                              AS ssic_description,
           COALESCE(bool_or(agency_row), FALSE)                                         AS registered_agency
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
       a.ssic_code_2020, a.ssic_description,
       -- agency: registered as one (SSIC 78 / vetted name), or its own open ads carry an
       -- employment-agency licence number (2+ ads; public bodies never)
       (a.registered_agency OR (a.ea_licence_ads >= 2 AND NOT a.public_body))           AS is_agency,
       -- hires for clients: not an agency, but 30%+ of its described open ads (10+) say the
       -- role is with a client or that staff are deployed to one
       (NOT a.registered_agency AND NOT (a.ea_licence_ads >= 2) AND NOT a.public_body
        AND a.described_ads >= 10 AND a.client_ads::numeric / a.described_ads >= 0.3)   AS hires_for_clients,
       a.nonstandard_pay_count, a.described_ads, a.ea_licence_ads, a.client_ads
  FROM agg a
  LEFT JOIN fam f USING (company_key)
  LEFT JOIN famsal fs USING (company_key)
  LEFT JOIN cat c USING (company_key)
 WHERE a.active_count > 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_stats_key ON company_stats (company_key);
CREATE INDEX IF NOT EXISTS idx_company_stats_active ON company_stats (active_count DESC);
