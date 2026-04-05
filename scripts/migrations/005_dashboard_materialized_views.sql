-- Materialized views for dashboard — pre-aggregated from job_daily_stats
-- Reduces load on heavy dashboard queries. Refresh on crawl completion.
-- Run: psql $DATABASE_URL -f scripts/migrations/005_dashboard_materialized_views.sql
--
-- Supabase: call refresh via SQL or RPC:
--   SELECT refresh_dashboard_materialized_views();
--   -- or from JS: await supabase.rpc('refresh_dashboard_materialized_views')
--
-- Scheduled refresh (pg_cron, if enabled):
--   SELECT cron.schedule('refresh-dashboard-mvs', '0 * * * *', 'SELECT refresh_dashboard_materialized_views()');

-- Daily totals (used by get_jobs_over_time_posted_and_removed, get_active_jobs_over_time)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dashboard_daily_stats AS
SELECT
    stat_date::date AS stat_date,
    SUM(active_count)::int AS active_count,
    SUM(added_count)::int AS added_count,
    SUM(removed_count)::int AS removed_count
FROM job_daily_stats
WHERE category != 'Unknown'
GROUP BY stat_date
ORDER BY stat_date ASC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dashboard_daily_stats_date
    ON mv_dashboard_daily_stats(stat_date);

-- Category-level trends (used by get_category_trends)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_dashboard_category_trends AS
SELECT
    stat_date::date AS stat_date,
    category,
    SUM(active_count)::int AS active_count,
    SUM(added_count)::int AS added_count,
    SUM(removed_count)::int AS removed_count
FROM job_daily_stats
WHERE category != 'Unknown'
GROUP BY stat_date, category
ORDER BY stat_date ASC, category;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_dashboard_category_trends_pk
    ON mv_dashboard_category_trends(stat_date, category);

-- PostgreSQL function to refresh both views (call on crawl completion)
-- Requires unique indexes (created above) for CONCURRENTLY.
-- Also invalidates get_dashboard_summary RPC cache if migration 006 applied.
CREATE OR REPLACE FUNCTION refresh_dashboard_materialized_views()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_dashboard_daily_stats;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_dashboard_category_trends;
    BEGIN
        PERFORM invalidate_rpc_cache('dashboard_summary');
    EXCEPTION WHEN undefined_function THEN
        NULL;  -- migration 006 not applied
    END;
END;
$$;

COMMENT ON FUNCTION refresh_dashboard_materialized_views() IS
    'Refresh dashboard materialized views. Call after crawl completion.';
