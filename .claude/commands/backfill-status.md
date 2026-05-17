Report the backfill status of jobs in the database. Check and report:

1. **Total active jobs** — count from `jobs` where `is_active = true`.

2. **Missing embeddings** — active jobs with no row in `job_embeddings`. These jobs cannot be matched.

3. **Missing LLM fields** — active jobs where `min_years_experience IS NULL` or `llm_fields_json IS NULL`. These jobs lack experience-level and canonical skill data.

4. **Missing rich fields** — active jobs where `category IS NULL` (not yet backfilled from MCF API).

5. **Estimated backfill time** at current rate limits:
   - `mcf re-embed`: ~1–2 jobs/sec (CPU-bound BGE inference)
   - `mcf backfill-rich-fields`: ~4 req/s (MCF API rate limit)

**To run backfills:**
```bash
# Re-embed + extract LLM fields (min_years_experience, llm_fields_json)
uv run mcf re-embed

# Backfill salary/category from MCF API
uv run mcf backfill-rich-fields
```

For large backlogs on Railway, use `--limit` to batch the work across runs:
```bash
uv run mcf re-embed --limit 500
```

Refer to `scripts/BACKFILL_README.md` for the full backfill workflow.
