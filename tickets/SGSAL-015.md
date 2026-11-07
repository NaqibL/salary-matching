---
id: SGSAL-015
project: salary-matching
title: Re-embed job DB with v2 model (backfill)
status: done
priority: high
type: chore
labels: [ml, embeddings, backfill, bge]
created: 2026-06-14
updated: 2026-11-08
depends_on: [SGSAL-003]
blocks: []
---

> **Closed 2026-11-08.** The bulk v2 re-embed landed with 99da0d9; as of 2026-11-07 448k of the vectors are `v2` and ≈178k (`v1` / `BAAI/bge-base`, fewer after the SGSAL-024 dedup) remain. Re-embedding that remainder is tracked as **SGSAL-025 step 2**, so this ticket is superseded rather than reopened.

## Summary

The `job_embeddings` table was populated using v1 (`NaqibL/bge-base-sgmarket-v1`). The query path now uses v2 (`NaqibL/bge-base-sgmarket-v2`). Cross-model similarity comparisons work (shared base model keeps spaces close) but we're leaving v2's full improvement on the table until stored embeddings are regenerated with v2.

## Context

- v2 eval showed +2.5pp improvement and +0.09 BI Analyst similarity score — but these numbers were measured with cross-model comparison (v2 query vs v1 stored embeddings)
- A full re-embed will yield the true v2 performance ceiling
- Embedding is done at ingestion time in `src/mcf/lib/pipeline/incremental_crawl.py` via `Embedder.embed_text()`
- Stored in `job_embeddings.embedding` (768-dim vector, pgvector)
- Existing backfill pattern: `scripts/backfill_v2.py` (classification backfill) — use same batch loop structure

## Script to write

`scripts/reembed_jobs.py` — iterates all jobs with existing embeddings, re-embeds job text with the current `Embedder` (v2), writes back to `job_embeddings.embedding`.

```
SELECT j.job_uuid, j.title, j.description
FROM jobs j
JOIN job_embeddings e ON e.job_uuid = j.job_uuid
ORDER BY j.job_uuid
LIMIT %s OFFSET %s
```

Job text format (must match ingestion pipeline):
```python
desc_text, _ = extract_high_signal_description(description, title)
job_text = f"Job Title: {title}\nDescription: {desc_text}"
vector = embedder.embed_text(job_text)
```

Then `UPDATE job_embeddings SET embedding = %s WHERE job_uuid = %s`.

## Acceptance Criteria

- [ ] Write `scripts/reembed_jobs.py` — batch loop, progress output, same pattern as `backfill_v2.py`
- [ ] Run against production DB (can run locally against Supabase)
- [ ] Re-run `scripts/casestudy_debug.py` after backfill — Shopee BI Analyst score should improve further
- [ ] Re-run `scripts/eval_lowball.py` — pairwise accuracy should hold or improve vs 87.5%

## Current status (2026-06-15)

Using `scripts/import_embeddings.py` to import pre-computed embeddings from `data/job_embeddings_v2.parquet` (172,484 rows). First 100k rows imported successfully before autovacuum lock contention caused stuck sessions. Sessions cleared, autovacuum finished. On resume, UPDATE runs without error but `rowcount = 0` — no rows matched. Suspect job_uuid mismatch between parquet rows 100k+ and what's in `job_embeddings`. Need to:
- Run diagnostic: compare parquet job_uuids against DB to find overlap
- Check if first 100k actually committed (query `SELECT COUNT(*) FROM job_embeddings WHERE embedding IS NOT NULL`)

## Notes

- Estimated row count: check `SELECT COUNT(*) FROM job_embeddings`
- BGE encodes ~500 tokens/s on CPU — estimate runtime before starting
- Safe to run while production is live; writes are per-row, no locking
- After backfill, the active-jobs pool cache (15-min TTL) will serve stale v1 embeddings until it expires — consider restarting Railway after backfill completes
