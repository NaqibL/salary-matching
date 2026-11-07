---
id: SGSAL-025
project: salary-matching
title: Vector storage roadmap — halfvec now, role-family routed partitions, cold-tier quantisation (keep all history)
status: in-progress
priority: medium
type: chore
labels: [storage, embeddings, performance, infra, design]
created: 2026-11-07
updated: 2026-11-08
depends_on: [SGSAL-024]
blocks: []
---

## Policy

Never delete job rows or expired postings (see SGSAL-024). This ticket is the
plan for keeping *all* vectors searchable as the history grows, with a working
set that fits the database's memory, instead of a retention rule.

## Facts (2026-11-07)

| item | value |
|---|---|
| Postgres / pgvector | 17.6 / 0.8.0 (halfvec, `binary_quantize`, iterative scans available) |
| other extensions available | `pg_partman` 5.3.1, `pg_cron` 1.6.4 — **not** VectorChord / pgvectorscale (checked `pg_available_extensions`), so disk-native quantised engines are out unless we leave Supabase |
| instance | Small, 2 GB RAM, `shared_buffers` 512 MB, `effective_cache_size` **128 MB** (misconfigured low), `maintenance_work_mem` 64 MB |
| `idx_job_embeddings_vector` (HNSW, m=16, ef_construction=64) | 1.9 GB |
| vectors | 616k before SGSAL-024, ≈ 340–400k after; 768-d; 448k `v2`, 74k `v1`, 104k `BAAI/bge-base` |
| growth | ≈ 21k jobs/week, ≈ 12–13k new texts/week after dedup |
| disk price | $0.125/GB/month beyond 8 GB — disk is not the constraint, memory is |
| role families | 24 Jev families; largest is 12% of active jobs; 641k expired jobs are unlabelled (backfill was active-only) |

2026-11-08 pre-apply: job_embeddings 627,040 rows / 4521 MB, DB 7087 MB; dry run says --apply removes 255,252 duplicate vectors (→ ≈371.8k rows).

The checker's main query (`get_all_embedded_job_ids_ranked`) scans the whole
index, active + expired, so a cold query touches an index 4× larger than
`shared_buffers`.

## Steps (do in order; each is independently reversible)

### 1. halfvec (now, after SGSAL-024's dedup)

- `CREATE INDEX CONCURRENTLY idx_job_embeddings_halfvec ON job_embeddings USING
  hnsw ((embedding::halfvec(768)) halfvec_cosine_ops) WITH (m=16,
  ef_construction=64);` — set `maintenance_work_mem` as high as the session
  allows first (build is much slower when the graph spills).
- Switch the five similarity queries (`get_active_job_ids_ranked`,
  `get_all_embedded_job_ids_ranked`, `get_company_jobs_ranked`,
  `get_active_jobs_pool`'s callers, `assign_hot_jobs_scores`) to
  `embedding::halfvec(768) <=> %s::halfvec(768)`; the candidate-side queries in
  `candidate_embeddings` stay as they are.
- Drop `idx_job_embeddings_vector` (this also reclaims the dead-tuple space
  left by SGSAL-024's deletes). Expected index ≈ 0.5–0.6 GB → fits in
  `shared_buffers`.
- Later, in a quiet window: `ALTER TABLE job_embeddings ALTER COLUMN embedding
  TYPE halfvec(768)` to halve TOAST too (table rewrite, takes a lock; or add a
  column and swap). Expected `job_embeddings` total ≈ 1.1–1.3 GB.
- Benchmarks (pgvector issue 326, Supabase 0.7.0 post, Neon): recall identical
  to three decimals, index ~50% smaller, builds faster.
- Also: `ALTER DATABASE postgres SET effective_cache_size = '1536MB'` (planner hint
  only; harmless; new sessions only). **Owner must run it** — Claude's auto mode
  refuses the ALTER (2026-11-08).

#### Step 1 status (2026-11-08)

- [x] Code: five job-side queries use `embedding::halfvec(768) <=> %s::halfvec(768)`
      (ec44030, **held back locally, not pushed**).
- [x] Migration 023 written (`scripts/migrations/023_halfvec_index.sql`).
- [x] Workflows: the "Rebuild HNSW indexes" safety-net step in `daily-embed.yml` and
      `re-embed.yml` used to `CREATE INDEX IF NOT EXISTS idx_job_embeddings_vector` —
      it would have silently rebuilt the 1.9 GB full-precision index the night after
      we drop it. Both now create the halfvec index instead (same local commit batch).
- [x] Docs: `CLAUDE.md`, `.claude/agents/db-ops.md` point at the halfvec index.
- [ ] `--apply` VACUUM finished (running since ≈03:30 SGT; `vacuuming indexes` phase
      is the old HNSW index, disk-bound).
- [ ] Build `idx_job_embeddings_halfvec` CONCURRENTLY (by hand; see migration header
      for the session settings). Best done with no embed running: `daily-embed.yml`
      is triggered by `daily-crawl-2.yml` (10:00 UTC / 18:00 SGT) and writes to
      `job_embeddings`; the build survives writes but slows down.
- [ ] Push master (ec44030 + today's docs/workflow commits) → Railway deploy →
      `EXPLAIN (ANALYZE, BUFFERS)` of `get_all_embedded_job_ids_ranked` shows
      `idx_job_embeddings_halfvec`. Checker p95 cold-query timing noted here.
- [ ] `DROP INDEX CONCURRENTLY idx_job_embeddings_vector` — **only after the push**,
      otherwise the next daily embed (old workflow on origin) recreates it.
- [ ] `effective_cache_size` (owner, above).
- [ ] Record `pg_relation_size` of the halfvec index (target ≤ 0.7 GB) and
      `pg_total_relation_size('job_embeddings')`.

**Order matters:** build → push → drop. Pushing before the index exists makes
every checker query a sequential scan with the halfvec cast (the old index no
longer matches the expression); dropping before the push lets the origin
workflow rebuild the old index.

### 2. Re-embed the old-model vectors with `v2`

178k vectors are from `BAAI/bge-base` or `v1` (fewer after dedup). The checker
embeds the query with `v2`, so the oldest history matches worse than it
should. Run the existing `re-embed` workflow with a `--model-not v2` style
selector; no LLM cost (`skip_llm`, LLM fields already stored). Only canonical
jobs.

### 3. Route by role family (measure first, then partition)

Idea: inverted-file search with partitions that mean something. List-partition
`job_embeddings` by family (24 partitions, HNSW per partition); at query time
pick the 2–3 nearest **family centroids** (mean `v2` vector per family, stored
on `role_families`) and search only those partitions. Each query then touches
≈ 1/10 of the index, so the working set stays in memory however large the
history gets.

- Partition key must exist for every row: use nearest-centroid family (free,
  deterministic) rather than the Jev label — 641k expired jobs have no Jev
  label, and the key only needs to agree with the routing, not with the
  product label.
- **Gate:** before partitioning, measure routing recall offline — 200 real
  checker queries (`scripts/finetune/eval_lowball.py` has the harness), top-500
  from the full index vs. union of top-500 from the 2 / 3 nearest families.
  Proceed only if overlap ≥ 0.95 at k=3. Partition sizes are balanced enough
  (largest 12%).
- `pg_partman` for partition management; `pg_cron` for the nightly centroid
  refresh and `posting_groups` refresh so space management is automatic.
- Cost: HNSW per partition, a routing step in `PostgresStore`, and
  `hnsw.iterative_scan = relaxed_order` for the filtered scans.

### 4. Cold tier: binary quantisation for old partitions (when needed)

When the hot index approaches memory again (≈ 12–18 months at post-dedup
growth): for partitions / rows older than ~12 months, index
`(binary_quantize(embedding)::bit(768)) bit_hamming_ops` (≈ 96 bytes/vector,
~30× smaller) and re-rank the top ~5× candidates by exact halfvec distance.
Acceptable for history because the final percentile uses exact salaries from
`jobs`. Measure recall on BGE vectors first (AWS/Neon report BQ needs a large
re-rank pool to hold recall).

### Rejected

- 90/180-day deletion of expired embeddings (SGSAL-022 E6): saves ≈ $1/month of
  disk and damages the checker's benchmark pool. Rejected 2026-11-07.
- Medium compute (+$45/month) as the fix: halfvec gives the same headroom free.
- Label-only history (benchmark pool from family + tier + skills without
  vectors): removes the vector problem entirely but makes historical matches
  coarser; keep as the fallback if vectors ever become the cost driver.

## Acceptance

- Step 1: `pg_relation_size` of the halfvec index ≤ 0.7 GB; checker p95 on a
  cold query lower than before (measure with the response cache bypassed);
  `tests/test_smoke.py` passes; no query still references
  `idx_job_embeddings_vector`.
- Step 2: `SELECT model_name, count(*) FROM job_embeddings GROUP BY 1` shows
  only `v2`.
- Step 3: routing recall report committed under `scripts/eval/`; partitions
  created only if the gate passes.

## Sources

- pgvector README (halfvec, binary_quantize, partitioning, iterative scans):
  https://github.com/pgvector/pgvector
- halfvec benchmarks: https://github.com/pgvector/pgvector/issues/326 ,
  https://supabase.com/blog/pgvector-0-7-0 ,
  https://neon.com/blog/dont-use-vector-use-halvec-instead-and-save-50-of-your-storage-cost
- binary quantisation + re-rank: https://aws.amazon.com/blogs/database/scale-pgvector-with-binary-quantization-on-amazon-aurora-postgresql/
- Supabase pricing (disk $0.125/GB/mo, Small 2 GB): https://supabase.com/pricing
