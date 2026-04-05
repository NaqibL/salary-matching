# Storage Layer (`src/mcf/lib/storage/`)

## Purpose

Provides a database-agnostic abstraction over all persistence operations. The `Storage` abstract base class defines ~36 methods covering jobs, embeddings, user profiles, ratings, and analytics. Two concrete implementations (`DuckDBStore`, `PostgresStore`) allow the same application code to run against a local DuckDB file (dev) or a managed PostgreSQL database (production) via a single env var switch.

## Key Files

| File | Purpose |
|---|---|
| `base.py` | `Storage` ABC — complete interface contract, ~36 abstract methods |
| `duckdb_store.py` | DuckDB implementation (~2000 lines). Used when `DATABASE_URL` is not set. |
| `postgres_store.py` | PostgreSQL/Supabase implementation. Used when `DATABASE_URL` is set. |

## Dependencies

| Package | Use |
|---|---|
| `duckdb` | Local columnar DB (dev/test) |
| `psycopg2` | PostgreSQL adapter (production) |
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
store.get_active_job_ids_ranked(query_embedding: np.ndarray) -> list[tuple[str, float, datetime | None]]

# Embeddings
store.upsert_job_embedding(uuid: str, embedding: np.ndarray) -> None
store.get_job_embeddings(uuids: list[str]) -> dict[str, np.ndarray]
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

## How the Switch Works

In `src/mcf/api/server.py` lifespan:
```python
def _make_store() -> Storage:
    if settings.database_url:
        from mcf.lib.storage.postgres_store import PostgresStore
        return PostgresStore(settings.database_url)
    else:
        from mcf.lib.storage.duckdb_store import DuckDBStore
        return DuckDBStore(str(db_path))
```

## State Management

The `Storage` object is a singleton initialised at startup (FastAPI lifespan) and injected into route handlers via `Depends(get_store)`. It manages its own connection lifecycle. DuckDB uses a single in-process connection; Postgres uses a connection pool.

## Testing

Tests use a real DuckDB instance (no mocking). The DuckDB file is created fresh for each test session via the `TestClient` fixture.

```bash
uv run pytest tests/ -v
```

## Common Modifications

- **Add a new DB operation**: See [Adding a New Storage Method](../../../.ai/common-tasks.md#adding-a-new-storage-method)
- **Schema changes**: Add `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE` in both `duckdb_store.py` and `postgres_store.py` schema setup methods
