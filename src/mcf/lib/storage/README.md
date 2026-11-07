# Storage Layer (`src/mcf/lib/storage/`)

## Purpose

Provides a database-agnostic abstraction over all persistence operations. The `Storage` abstract base class defines the complete interface (~36 methods) covering jobs, embeddings, user profiles, ratings, and analytics. `PostgresStore` is the sole concrete implementation, backed by Supabase Postgres in production and local dev.

## Key Files

| File | Purpose |
|---|---|
| `base.py` | `Storage` ABC — complete interface contract |
| `postgres_store.py` | PostgreSQL/Supabase implementation — the only store |

## Dependencies

| Package | Use |
|---|---|
| `psycopg2` | PostgreSQL adapter |
| `numpy` | Embedding arrays stored/retrieved as binary |

## Internal Dependencies

- `mcf.lib.models` — Pydantic models used in return types
- `mcf.lib.sources.base` — `NormalizedJob` dataclass stored via `upsert_job`

## Interface (Key Methods)

```python
# Jobs
store.get_job(uuid: str) -> dict | None
store.upsert_job(job: NormalizedJob) -> None
store.get_active_job_ids() -> list[str]

# Embeddings
store.upsert_job_embedding(uuid: str, embedding: np.ndarray) -> None
store.get_all_active_job_embeddings() -> tuple[list[str], np.ndarray]

# User profiles
store.get_profile(user_id: str) -> dict | None
store.upsert_profile_embedding(user_id: str, embedding: np.ndarray) -> None

# Interactions
store.add_interaction(user_id: str, job_uuid: str, interaction_type: str) -> None
store.get_interacted_job_ids(user_id: str) -> set[str]

# Analytics
store.get_dashboard_summary() -> dict
store.get_active_jobs_by_date() -> list[dict]
```

## Posting groups (SGSAL-024)

`jobs.content_hash` and `jobs.canonical_job_uuid` (migration `scripts/migrations/022_posting_groups.sql`) group reposts of the same text; `job_embeddings` holds canonical rows only.

```python
# Write (crawl path)
store.set_content_hashes(rows: list[tuple[str, str | None]]) -> None      # (job_uuid, content_hash) pairs
store.find_canonicals(hashes: list[str]) -> dict[str, str]                # hash -> embedded canonical uuid
store.link_reposts(pairs: list[tuple[str, str]]) -> int                   # set canonical_job_uuid, copy LLM/Jev fields
store.refresh_posting_groups() -> None                                    # REFRESH MATERIALIZED VIEW CONCURRENTLY, crawl end

# Read (API)
store.get_posting_history(job_uuid: str) -> dict | None                   # group row incl. occurrences list
store.get_most_reposted(days: int = 365, limit: int = 20) -> list[dict]   # groups ranked by reposts in window (90 or 365)
store.active_canonical_uuids() -> set[str]                                # COALESCE(canonical, uuid) of active jobs
store.describe_columns(relation: str) -> set[str]                         # column names, used for feature gating
store.get_jobs_with_salary_by_uuids(..., representative=True, company_name=...)  # one card per posting

# Backfill-only (scripts/backfill_posting_keys.py)
store.iter_jobs_needing_hash(after_uuid: str, limit: int) -> list[tuple]  # keyset page of jobs without a hash
store.assign_canonicals() -> int                                          # pick a canonical per hash (embedded existing one first)
store.copy_fields_from_canonicals() -> int                                # fill NULL LLM fields / Jev labels on members
store.noncanonical_embedded_uuids() -> list[str]                          # duplicate vectors safe to delete
store.delete_embeddings_by_uuids(uuids: list[str]) -> int                 # batched by caller
store.posting_group_stats() -> dict                                       # groups, members, repost percentiles
```

`delete_inactive_job_embeddings` was removed: jobs and expired postings are never pruned.

`posting_groups` materialised view columns: `content_hash`, `canonical_job_uuid`, `latest_job_uuid`, `repost_count`, `active_count`, `first_posted`, `last_posted`, `reposts_90d`, `reposts_365d`, `distinct_companies`, `latest_salary_min`, `latest_salary_max`, `min_salary_seen`, `max_salary_seen`, `occurrences` (jsonb list of `{job_uuid, date, company, salary_min, salary_max, is_active}`).

## Configuration

`DATABASE_URL` (Postgres connection string) is required. Set it in `.env` for local dev — see `.env.example`.

## State Management

The `Storage` object is a singleton initialised at startup (FastAPI lifespan) and injected into route handlers via `Depends(get_store)`. It manages its own connection lifecycle.

## Testing

Tests require `DATABASE_URL` to be set. They are skipped automatically when it is not.

```bash
uv run pytest tests/ -v
```

## Common Modifications

- **Add a new DB operation**: Add an abstract method to `base.py`, implement it in `postgres_store.py`.
- **Schema changes**: Apply via `ALTER TABLE` in Supabase SQL editor and update `ensure_schema()` in `postgres_store.py`.
