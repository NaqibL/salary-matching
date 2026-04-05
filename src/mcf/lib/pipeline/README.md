# Pipeline (`src/mcf/lib/pipeline/`)

## Purpose

Orchestrates the full incremental crawl workflow: fetch new job IDs from a source, diff against the database, fetch details for new jobs, extract and clean text, compute embeddings, and store everything. This is the data ingestion backbone of the system.

## Key Files

| File | Purpose |
|---|---|
| `incremental_crawl.py` | `run_incremental_crawl(source, store, embedder, ...)` — end-to-end pipeline |

## Dependencies

- `mcf.lib.sources` — `JobSource` adapters (MCF, CAG)
- `mcf.lib.storage.base` — `Storage` interface
- `mcf.lib.embeddings.embedder` — `Embedder` for batch embedding
- `mcf.lib.embeddings.job_text` — text extraction from job HTML
- `mcf.lib.crawler.crawler` — UUID listing with rate limiting

## Pipeline Steps

```
1. list_job_ids()          → all currently active UUIDs from source
2. store.get_active_job_uuids() → already-stored UUIDs
3. diff                    → new UUIDs only (incremental)
4. get_job_detail(uuid)    → NormalizedJob for each new UUID
5. extract_job_text()      → clean text from description HTML
6. embedder.embed_batch()  → BGE embeddings for new jobs
7. store.upsert_job()      → persist job data
8. store.upsert_job_embedding() → persist embeddings
9. store.insert_daily_stats()   → snapshot for dashboard trends
10. mark_expired_jobs()    → jobs no longer returned by source → inactive
```

## Usage

**Via CLI (most common):**
```bash
uv run mcf crawl-incremental --source mcf
uv run mcf crawl-incremental --source cag --limit 500
```

**Via FastAPI webhook (production nightly):**
```
POST /api/crawl
Authorization: Bearer {CRON_SECRET}
```
This is called by GitHub Actions via Vercel → Railway.

## Progress Tracking

The pipeline accepts an optional `progress_callback: Callable[[CrawlProgress], None]` for CLI Rich progress bars and webhook status reporting.

## Common Modifications

- **Add new source**: Add source adapter in `../sources/`, register in `incremental_crawl.py`
- **Change embedding batch size**: Update in `embedder.py` or pass `batch_size` param
- **Add post-crawl hook**: Add step after `insert_daily_stats` in `incremental_crawl.py`
