-- scripts/migrations/025_companies.sql
-- SGSAL-028: posting-company registry. company_key = lower(company_name) exactly as the
-- source reports it (aliases are resolved at aggregation time, not here). SSIC codes come
-- from MyCareersFuture job detail (postedCompany.ssicCode2020); employment agencies are
-- SSIC 78xxx. CAG (government) companies are stored with source='cag' and no SSIC.
-- Filled by the crawler from now on and by scripts/backfill_companies.py for history.
--
-- Apply to Supabase BY HAND. ensure_schema() carries an identical copy.

CREATE TABLE IF NOT EXISTS companies (
    company_key      TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    uen              TEXT,
    ssic_code        TEXT,
    ssic_code_2020   TEXT,
    ssic_description TEXT,
    employee_count   INTEGER,
    source           TEXT NOT NULL DEFAULT 'mcf',
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_companies_uen ON companies (uen);
