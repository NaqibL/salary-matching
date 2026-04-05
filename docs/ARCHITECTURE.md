# MCF Job Matcher — Architecture

For onboarding and env details, see [HANDOVER.md](../HANDOVER.md), [TECH_STACK.md](TECH_STACK.md), and [RUNTIME_FLOWS.md](RUNTIME_FLOWS.md).

## High-Level Overview

```mermaid
flowchart TB
    subgraph sources [Job Sources]
        MCF[MCF API]
        CAG[Careers@Gov Algolia]
    end

    subgraph crawl [Crawl Pipeline]
        List[list_job_ids]
        Diff[Diff vs DB]
        Fetch[fetch_detail]
        Embed[embed_job_text]
    end

    subgraph storage [Storage]
        Store[(Storage)]
    end

    subgraph match [Matching]
        MS[MatchingService]
        Vector[get_active_job_ids_ranked]
        Score[score + filter]
        Session[create_match_session]
    end

    subgraph api [API]
        FastAPI[FastAPI server]
    end

    subgraph frontend [Frontend]
        Next[Next.js]
    end

    MCF --> List
    CAG --> List
    List --> Diff
    Diff --> Fetch
    Fetch --> Embed
    Embed --> Store
    Store --> Vector
    Vector --> Score
    Score --> Session
    Session --> FastAPI
    FastAPI --> Next
```

## Data Flow

1. **Crawl** (`incremental_crawl.py`): List job IDs from MCF/CAG → diff with DB → fetch detail for new jobs → embed job text → upsert to storage.
2. **Storage**: Jobs and embeddings stored via `Storage` interface. `PostgresStore` or `DuckDBStore` chosen by `DATABASE_URL`.
3. **Matching** (`matching_service.py`): Get profile embedding → `get_active_job_ids_ranked(limit=2000)` → score (semantic similarity + recency; skills weight is 0) → filter (min_similarity, max_days_old, exclude interacted) → create match session.
4. **API** (`server.py`): Serves matches, profile, dashboard, interactions.
5. **Frontend**: Next.js app with Discover (taste), Matches, Dashboard.

## Storage Abstraction

| Component | Purpose |
|-----------|---------|
| `Storage` (base.py) | Abstract interface — all methods must be implemented by both stores |
| `PostgresStore` | Supabase/Postgres. Uses pgvector for fast similarity when migration 001 applied. |
| `DuckDBStore` | Local file. No vector index; full scan for similarity. |

**When to use which:**
- **Postgres**: Production (Supabase), deployed API, pgvector for fast matching.
- **DuckDB**: Local dev, no cloud, `data/mcf.duckdb`. Export to Postgres via `mcf export-to-postgres`.

## Key Paths

| Layer | Path |
|-------|------|
| Crawl | `src/mcf/lib/pipeline/incremental_crawl.py` |
| Sources | `src/mcf/lib/sources/mcf_source.py`, `cag_source.py` |
| Storage | `src/mcf/lib/storage/base.py`, `postgres_store.py`, `duckdb_store.py` |
| Embeddings | `src/mcf/lib/embeddings/embedder.py`, `job_text.py`, `resume.py` |
| Matching | `src/mcf/api/services/matching_service.py` |
| API | `src/mcf/api/server.py` |
| Frontend | `frontend/app/`, `frontend/lib/api.ts` |
