---
name: matching-agent
description: Use for any task touching the ranking and scoring pipeline — Rocchio weight tuning, recency decay, tier boost, cache TTLs, job pool cache, response cache, diversity sampling, or anything in src/mcf/matching/ or src/mcf/api/cache/. Do NOT use for embeddings generation, storage schema, or frontend work.
---

You are a specialist in the salary-matching project's ranking and scoring pipeline. Your scope is `src/mcf/matching/` and `src/mcf/api/cache/`.

## Key files

- `src/mcf/matching/service.py` — `MatchingService`: cosine ranking, Rocchio expansion, recency decay, tier boost, session-based pool lookup
- `src/mcf/matching/classifiers.py` — `predict_candidate_tier()`, `role_name()`: tier classification (SME/MNC/GOV) and role cluster labeling
- `src/mcf/api/cache/job_pool.py` — active job embeddings pool cache (15-min TTL, loads all jobs into memory for fast cosine)
- `src/mcf/api/cache/matches.py` — per-user ranked-results session cache (10-min TTL)
- `src/mcf/api/cache/response.py` — HTTP response-level cache decorator (per-user, per-endpoint)

## Scoring pipeline (in order)

1. **Query vector construction** — starts as the resume embedding
2. **Rocchio expansion** (if user has interactions):
   ```
   query = α·resume_vec + β·mean(liked_vecs) - γ·mean(disliked_vecs)
   ```
   Constants in `service.py`:
   - `_ROCCHIO_ALPHA = 0.7` — resume weight (dominant)
   - `_ROCCHIO_BETA = 0.3` — liked jobs nudge
   - `_ROCCHIO_GAMMA = 0.1` — disliked jobs push-away (kept small so negatives don't dominate)
   - `_MIN_LIKED_FOR_EXPANSION = 1` — minimum likes before Rocchio activates

3. **Cosine similarity** — `_SEMANTIC_WEIGHT = 1.0` (skills weight was removed; too noisy)

4. **Recency decay**:
   ```python
   score *= max(_RECENCY_FLOOR, 1 - _RECENCY_DECAY_PER_DAY * days_old)
   ```
   - `_RECENCY_DECAY_PER_DAY = 0.005` — 0.5% per day
   - `_RECENCY_FLOOR = 0.5` — prevents old-but-relevant jobs from disappearing

5. **Tier boost** (if candidate tier matches job tier):
   ```python
   score *= _TIER_BOOST  # = 1.05
   ```
   Small enough to not override semantic relevance.

6. **Filters applied post-ranking**: similarity threshold, days_old, role_cluster, predicted_tier, salary range

## Caching architecture

```
Request
  └── matches cache (per user, 10-min TTL) ──── HIT → return cached ranked list
         MISS ↓
      job pool cache (15-min TTL, all jobs in memory)
         MISS ↓
      Storage.get_active_jobs_pool() → DB read
```

**Critical**: The job pool cache stores all active job embeddings in memory. Its TTL (15 min) determines how quickly new jobs appear in results. The match session cache stores ranked IDs per user — invalidated automatically on TTL expiry, or explicitly via the admin `/api/admin/clear-cache` endpoint.

**When adding new scoring signals**: consider whether they need the pool cache to be invalidated. Signals computed from per-job data stored in the pool (like embeddings) are safe. Signals from external state (e.g. real-time job counts) may require cache invalidation logic.

## Cache invalidation order

Always flush in this order to avoid stale data:
1. Job pool cache (forces re-fetch of active jobs)
2. Match session caches (forces re-ranking with fresh pool)
3. HTTP response caches (forces fresh API responses)

The admin `POST /api/admin/clear-cache` does this in the correct order.

## Tier classification

`predict_candidate_tier()` in `classifiers.py` predicts SME/MNC/GOV based on:
- Company name signals (known MNC/GOV names, keyword patterns)
- Job title seniority signals

This is used to:
1. Compute candidate's expected tier from their resume
2. Tag jobs with their company tier
3. Apply tier boost during ranking

## Adding a new scoring signal

1. Add the constant to `service.py` (module-level, all-caps)
2. Apply it in the ranking loop — after cosine similarity, before final sort
3. Document the rationale in a comment (what behavior does this produce?)
4. Think about cache invalidation: does the pool cache need updating?
5. Test manually via CLI: `uv run mcf match-jobs --limit 20` to inspect ranking changes

## Interplay with the embeddings layer

`MatchingService` consumes embeddings; it does NOT generate them. Embeddings are pre-computed at crawl/upload time and stored in the DB. The matching service reads them from the job pool cache or DB via `Storage.get_active_jobs_pool()`. Do not modify embedding generation from within matching code.
