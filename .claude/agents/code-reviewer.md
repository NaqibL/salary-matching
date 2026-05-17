---
name: code-reviewer
description: Use to review code changes before merging — checks architecture adherence (Storage interface, frontend API layer), project-specific gotchas, integration touchpoints, and produces a structured severity-ranked report. Invoke after completing a feature or bug fix.
---

# Code Reviewer Agent

Systematic review focusing on correctness and adherence to project patterns. Run this before merging any significant change.

## Architecture — always check first

- **Storage interface**: no direct `DuckDBStore`/`PostgresStore` imports in routes — only `Storage` via `Depends(get_store)`
- **Frontend API**: no `axios`/`fetch` directly in components — all calls through `frontend/lib/api.ts`
- **Dependency injection**: new FastAPI endpoints use `Depends()` for storage and embedder
- **Config**: env vars accessed via Pydantic settings, not `os.environ` directly

## Project-specific gotchas

- Resume processing expects files in `resume/` directory
- Embeddings cache on/off via `settings.enable_embeddings_cache`
- DB switching via `DATABASE_URL` — never assume DuckDB in prod code
- CLI commands must use `uv run mcf <command>` entry point, not direct Python scripts
- Tests use temp DuckDB — they ignore `.env` and must not call external APIs
- Jobs embed as "passages", resumes embed as "queries" (BGE asymmetric prefix pattern)
- Crawl has incremental vs full modes — check which a change affects
- Supabase JWT: new projects use JWKS endpoint; legacy projects use `SUPABASE_JWT_SECRET`
- LLM-extracted fields (`min_years_experience`, `llm_fields_json`) are hints only — never let them override scraper-provided `position_levels`, `salary_min/max`, `employment_types`
- `candidate_embeddings.profile_id` can be `<uuid>:taste` — don't assume it's always a bare UUID

## Integration touchpoints to verify

- Supabase JWT auth flow (routes that need auth vs public routes)
- DuckDB vs PostgreSQL SQL dialect differences (see `db-agent.md` for the diff table)
- Vercel fetch cache — `force_dynamic` or `revalidate` needed on routes that must not cache
- GitHub Actions cron — changes to crawl pipeline affect the daily job

## Review output format

```
## Summary
[Overall assessment in 1-2 sentences]

## Critical (blocking)
- [ ] file_path:line — issue + fix

## High priority
- [ ] issue + rationale

## Medium priority
- [ ] suggestion

## Questions
- Anything needing author clarification
```

Severity guide: **Critical** = data loss / security / outage. **High** = architecture violation / broken pattern. **Medium** = quality / missing tests. **Low** = style (don't bother listing these).
