-- pgvector migration for MCF Job Matcher
-- Run once in Supabase SQL Editor after scripts/schema.sql
-- Enables fast vector similarity search for job embeddings (BGE 384 dimensions)

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add vector column to job_embeddings (keep embedding_json for backward compatibility)
ALTER TABLE job_embeddings ADD COLUMN IF NOT EXISTS embedding vector(384);

-- 3. Backfill from embedding_json (JSON array text like '[0.1, -0.2, ...]')
UPDATE job_embeddings
SET embedding = embedding_json::vector
WHERE embedding_json IS NOT NULL
  AND embedding_json != ''
  AND embedding IS NULL;

-- 4. HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector
ON job_embeddings
USING hnsw (embedding vector_cosine_ops);

-- 5. Add vector column to candidate_embeddings (resume + taste profiles)
ALTER TABLE candidate_embeddings ADD COLUMN IF NOT EXISTS embedding vector(384);

-- 6. Backfill candidate embeddings
UPDATE candidate_embeddings
SET embedding = embedding_json::vector
WHERE embedding_json IS NOT NULL
  AND embedding_json != ''
  AND embedding IS NULL;

-- 7. Index for candidate embedding lookups (optional, smaller table)
CREATE INDEX IF NOT EXISTS idx_candidate_embeddings_vector
ON candidate_embeddings
USING hnsw (embedding vector_cosine_ops);
