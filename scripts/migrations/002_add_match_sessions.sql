-- Match sessions for efficient pagination (Option 2 + 3)
-- Run in Supabase SQL Editor after 001_add_pgvector.sql

CREATE TABLE IF NOT EXISTS match_sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    mode        TEXT NOT NULL,
    ranked_ids  TEXT NOT NULL,  -- JSON array of job_uuid strings, in ranked order
    total       INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS match_sessions_user_idx ON match_sessions(user_id);
CREATE INDEX IF NOT EXISTS match_sessions_expires_idx ON match_sessions(expires_at);
