-- Migration 015: restore HNSW index on job_embeddings.embedding (768-dim)
-- Dropped in 002_upgrade_embeddings_768.sql, never rebuilt.
-- Build time: ~1-5 min on Supabase free tier depending on row count.
-- Queries continue to work during build (full scan until index is ready).

-- idx_job_embeddings_vector already exists from migration 001.
-- This migration is a no-op — kept for deploy audit trail.
-- CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector
--   ON job_embeddings USING hnsw (embedding vector_cosine_ops);
