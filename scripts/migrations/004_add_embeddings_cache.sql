-- Embeddings cache: content_hash + model_name + embed_type -> embedding
-- TTL: indefinite (embeddings are deterministic for same input)
-- Run: psql $DATABASE_URL -f scripts/migrations/004_add_embeddings_cache.sql

CREATE TABLE IF NOT EXISTS embeddings_cache (
  content_hash TEXT NOT NULL,
  model_name TEXT NOT NULL,
  embed_type TEXT NOT NULL,
  embedding_json TEXT NOT NULL,
  dim INTEGER,
  cached_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (content_hash, model_name, embed_type)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_cache_lookup
  ON embeddings_cache(content_hash, model_name, embed_type);
