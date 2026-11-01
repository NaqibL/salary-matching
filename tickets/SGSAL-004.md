---
id: SGSAL-004
project: salary-matching
title: Lowball latency — skip _cleaner on query path
status: done
priority: high
type: bug
labels: [backend, performance, lowball]
created: 2026-06-13
updated: 2026-06-13
---

## Summary

`/api/lowball/check` fires a network call to OpenRouter/Gemini via `_cleaner.clean()` on every request. The LLM cleaner was designed for crawl-time ingestion, not real-time queries. Embedding the raw description is sufficient for salary benchmarking.

## Context

- File: `src/mcf/api/routes/lowball.py`
- `_cleaner.clean()` adds latency proportional to Gemini API round-trip (~1–3s) on every request
- HNSW index confirmed in place (`migration 015` was a no-op — index was created in `001_add_pgvector.sql`; `postgres_store.py` already sets `hnsw.ef_search` on both ranked queries)
- This is the last major latency contributor on the lowball path

## Acceptance Criteria

- [ ] Remove `_cleaner.clean()` call from the lowball route
- [ ] Embed the raw user-provided description directly
- [ ] Verify no other lowball logic depends on cleaner output (e.g. `llm_fields_json` extraction — those fields are for ingestion only)
- [ ] Test locally: `/api/lowball/check` should respond noticeably faster

## Notes

- Do NOT remove `_cleaner` from the ingestion/crawl pipeline — only skip it in the lowball route
- A response cache on top of this was evaluated and rejected: JDs vary per user so cache hit rate would be near-zero
