-- scripts/migrations/023_halfvec_index.sql
-- SGSAL-025 step 1: replace the full-precision HNSW index on job_embeddings with a
-- half-precision (halfvec) expression index. Same recall to three decimals, about
-- half the size, so the index fits in the Small instance's 512 MB shared_buffers.
--
-- Zero-downtime order (run BY HAND, autocommit, each statement separately):
--   1) build the new index CONCURRENTLY while the old one keeps serving;
--   2) deploy code whose ORDER BY uses  embedding::halfvec(768) <=> $1::halfvec(768)
--      (the planner only uses an expression index when the expression matches exactly);
--   3) drop the old index CONCURRENTLY. This is also what reclaims the space left by
--      the SGSAL-024 duplicate-vector delete (HNSW never shrinks on DELETE).
--
-- Session settings for the build (Small instance, 2 GB RAM):
--   SET statement_timeout = 0;
--   SET maintenance_work_mem = '384MB';          -- graph spills to disk above this; keep < shared_buffers
--   SET max_parallel_maintenance_workers = 1;
--
-- The column itself stays vector(768) for now; converting it to halfvec(768) halves
-- TOAST as well but needs a table rewrite under an exclusive lock (later quiet window).

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_job_embeddings_halfvec
  ON job_embeddings USING hnsw ((embedding::halfvec(768)) halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- after the code switch is deployed and verified (EXPLAIN shows idx_job_embeddings_halfvec):
-- DROP INDEX CONCURRENTLY IF EXISTS idx_job_embeddings_vector;
