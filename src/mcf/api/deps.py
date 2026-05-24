"""FastAPI dependencies — store and embedder initialisation and shared access.

The globals _store and _embedder are set once during the FastAPI lifespan
(server.py) via set_store() / set_embedder(). All routes call get_store() /
get_embedder() to obtain the active instances.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcf.lib.embeddings.base import EmbedderProtocol
    from mcf.lib.storage.base import Storage

_store: Storage | None = None
_embedder: EmbedderProtocol | None = None


def _make_store() -> Storage:
    """Return a PostgresStore using DATABASE_URL."""
    from mcf.api.config import settings

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")

    from mcf.lib.storage.postgres_store import PostgresStore

    return PostgresStore(settings.database_url)


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


def set_embedder(e: EmbedderProtocol) -> None:
    """Set the global embedder. Called once from the FastAPI lifespan."""
    global _embedder
    _embedder = e


def get_embedder() -> EmbedderProtocol:
    """Return the active Embedder instance. Raises if not yet initialised."""
    if _embedder is None:
        raise RuntimeError("Embedder not initialised")
    return _embedder
