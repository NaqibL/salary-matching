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
