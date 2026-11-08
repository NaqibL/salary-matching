-- scripts/migrations/028_market_stats.sql
-- SGSAL-030: one small long-format materialised view behind the whole public dashboard.
-- Every number a visitor sees (tiles, job-types table, "Posted before" section) is a row here,
-- so the dashboard never aggregates `jobs` per request. Refreshed at crawl end right after
-- company_stats (Storage.refresh_market_stats); now() is evaluated at refresh time, which is
-- what the week/4-week windows want.
--
-- dimension / key:
--   'total'  / 'all'                        one row, every column filled
--   'family' / <role_family or 'other'>     live-ad metrics + new/closed windows per job type
--   'poster' / 'direct' | 'agency'          live, live_reposts (who placed the live ad)
--   'bucket' / '1','2','3-5','6-10','11+'   texts = distinct ad texts with a live copy posted
--                                           that many times; live = live ads carrying them
--
-- Apply to Supabase BY HAND (additive; ~30-60 s to populate). ensure_schema() carries the CREATE copy.

CREATE MATERIALIZED VIEW IF NOT EXISTS market_stats AS
WITH live AS (
    SELECT COALESCE(j.role_family, 'other') AS role_family,
           CASE WHEN j.salary_min > 0 AND j.salary_max IS NOT NULL AND j.salary_max <= 2 * j.salary_min
                THEN (j.salary_min + j.salary_max) / 2.0 END          AS mid_ok,
           COALESCE(pg.repost_count, 1) >= 2                           AS is_repost,
           COALESCE(pg.distinct_companies, 1) >= 2                     AS is_multi_company,
           COALESCE(cs.is_agency, FALSE)                               AS is_agency
      FROM jobs j
      LEFT JOIN posting_groups pg ON pg.content_hash = j.content_hash
      LEFT JOIN company_stats cs ON cs.company_key = lower(COALESCE(j.company_canonical, j.company_name))
     WHERE j.is_active = TRUE
), live_by_family AS (
    SELECT role_family,
           count(*)::int                                               AS live,
           count(*) FILTER (WHERE is_repost)::int                      AS live_reposts,
           count(*) FILTER (WHERE is_agency)::int                      AS live_agency,
           count(*) FILTER (WHERE is_multi_company)::int               AS live_multi_company,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY mid_ok))::int  AS median_salary,
           count(mid_ok)::int                                          AS salary_n
      FROM live GROUP BY role_family
), windows AS (
    SELECT COALESCE(role_family, 'other') AS role_family,
           count(*) FILTER (WHERE first_seen_at >= now() - interval '7 days')::int                                           AS new_7d,
           count(*) FILTER (WHERE first_seen_at >= now() - interval '14 days' AND first_seen_at < now() - interval '7 days')::int   AS new_prev_7d,
           count(*) FILTER (WHERE first_seen_at >= now() - interval '28 days')::int                                          AS new_28d,
           count(*) FILTER (WHERE first_seen_at >= now() - interval '56 days' AND first_seen_at < now() - interval '28 days')::int AS new_prev_28d,
           count(*) FILTER (WHERE is_active = FALSE AND last_seen_at >= now() - interval '7 days')::int                      AS closed_7d,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM last_seen_at - first_seen_at) / 86400.0)
                FILTER (WHERE is_active = FALSE AND last_seen_at >= now() - interval '30 days'))::numeric(6,1)              AS median_days_up,
           count(*) FILTER (WHERE first_seen_at < now() - interval '7 days'
                              AND (is_active = TRUE OR last_seen_at >= now() - interval '7 days'))::int                      AS live_7d_ago
      FROM jobs
     GROUP BY 1
), families AS (
    SELECT 'family'::text AS dimension, f.role_family AS key,
           COALESCE(l.live, 0) AS live, COALESCE(l.live_reposts, 0) AS live_reposts,
           COALESCE(l.live_agency, 0) AS live_agency, COALESCE(l.live_multi_company, 0) AS live_multi_company,
           l.median_salary, COALESCE(l.salary_n, 0) AS salary_n,
           COALESCE(w.new_7d, 0) AS new_7d, COALESCE(w.new_prev_7d, 0) AS new_prev_7d,
           COALESCE(w.new_28d, 0) AS new_28d, COALESCE(w.new_prev_28d, 0) AS new_prev_28d,
           COALESCE(w.closed_7d, 0) AS closed_7d, w.median_days_up, COALESCE(w.live_7d_ago, 0) AS live_7d_ago,
           NULL::int AS texts
      FROM (SELECT role_family FROM live_by_family UNION SELECT role_family FROM windows) f
      LEFT JOIN live_by_family l USING (role_family)
      LEFT JOIN windows w USING (role_family)
), total AS (
    SELECT 'total'::text, 'all'::text,
           count(*)::int, count(*) FILTER (WHERE is_repost)::int, count(*) FILTER (WHERE is_agency)::int,
           count(*) FILTER (WHERE is_multi_company)::int,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY mid_ok))::int, count(mid_ok)::int,
           (SELECT sum(new_7d)::int FROM windows), (SELECT sum(new_prev_7d)::int FROM windows),
           (SELECT sum(new_28d)::int FROM windows), (SELECT sum(new_prev_28d)::int FROM windows),
           (SELECT sum(closed_7d)::int FROM windows),
           (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM last_seen_at - first_seen_at) / 86400.0))::numeric(6,1)
              FROM jobs WHERE is_active = FALSE AND last_seen_at >= now() - interval '30 days'),
           (SELECT sum(live_7d_ago)::int FROM windows),
           NULL::int
      FROM live
), poster AS (
    SELECT 'poster'::text, CASE WHEN is_agency THEN 'agency' ELSE 'direct' END,
           count(*)::int, count(*) FILTER (WHERE is_repost)::int, count(*) FILTER (WHERE is_agency)::int,
           count(*) FILTER (WHERE is_multi_company)::int,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY mid_ok))::int, count(mid_ok)::int,
           NULL::int, NULL::int, NULL::int, NULL::int, NULL::int, NULL::numeric(6,1), NULL::int, NULL::int
      FROM live GROUP BY is_agency
), bucket AS (
    SELECT 'bucket'::text,
           CASE WHEN repost_count = 1 THEN '1' WHEN repost_count = 2 THEN '2'
                WHEN repost_count <= 5 THEN '3-5' WHEN repost_count <= 10 THEN '6-10' ELSE '11+' END,
           sum(active_count)::int, NULL::int, NULL::int, NULL::int, NULL::int, NULL::int,
           NULL::int, NULL::int, NULL::int, NULL::int, NULL::int, NULL::numeric(6,1), NULL::int,
           count(*)::int
      FROM posting_groups WHERE active_count > 0 GROUP BY 2
)
SELECT *, now() AS computed_at FROM families
UNION ALL SELECT *, now() FROM total
UNION ALL SELECT *, now() FROM poster
UNION ALL SELECT *, now() FROM bucket;

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_stats_key ON market_stats (dimension, key);
