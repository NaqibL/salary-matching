-- Enable Row Level Security (RLS) on all public tables
-- Supabase warns when public tables don't have RLS enabled (PostgREST exposure).
-- All these tables are accessed by FastAPI (DATABASE_URL) or RPC (SECURITY DEFINER),
-- both of which bypass RLS. No policies needed — PostgREST direct access is blocked.
--
-- Run: psql $DATABASE_URL -f scripts/migrations/008_enable_rls_public_tables.sql

ALTER TABLE crawl_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_run_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_daily_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rpc_result_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_sessions ENABLE ROW LEVEL SECURITY;
