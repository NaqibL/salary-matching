"""FastAPI dependencies — store initialisation and shared access.

The global _store is set once during the FastAPI lifespan (server.py) via
set_store(). All routes call get_store() to obtain the active Storage instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcf.lib.storage.base import Storage

_store: Storage | None = None


def _make_store() -> Storage:
    """Return a DuckDBStore or PostgresStore depending on DATABASE_URL."""
    from mcf.api.config import settings

    if settings.database_url:
        from mcf.lib.storage.postgres_store import PostgresStore

        return PostgresStore(settings.database_url)

    from mcf.lib.storage.duckdb_store import DuckDBStore

    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return DuckDBStore(str(db_path))


def set_store(s: Storage) -> None:
    """Set the global store. Called once from the FastAPI lifespan."""
    global _store
    _store = s


def get_store() -> Storage:
    """Return the active Storage instance. Raises if not yet initialised."""
    if _store is None:
        raise RuntimeError("Store not initialised")
    return _store


def close_store() -> None:
    """Close and clear the global store. Called on lifespan shutdown."""
    global _store
    if _store:
        _store.close()
        _store = None
