-- Rich job fields and aggregate stats for dashboard
-- Run in Supabase SQL Editor after 002_add_match_sessions.sql

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS categories_json TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS employment_types_json TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS position_levels_json TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_min INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary_max INTEGER;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS posted_date DATE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS expiry_date DATE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS min_years_experience INTEGER;

CREATE TABLE IF NOT EXISTS job_daily_stats (
    stat_date           DATE NOT NULL,
    category            TEXT NOT NULL,
    employment_type     TEXT NOT NULL DEFAULT 'Unknown',
    position_level      TEXT NOT NULL DEFAULT 'Unknown',
    active_count        INTEGER NOT NULL DEFAULT 0,
    added_count         INTEGER NOT NULL DEFAULT 0,
    removed_count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (stat_date, category, employment_type, position_level)
);
CREATE INDEX IF NOT EXISTS job_daily_stats_date_idx ON job_daily_stats(stat_date DESC);
CREATE INDEX IF NOT EXISTS job_daily_stats_cat_idx ON job_daily_stats(category);
