"""Embedding cache by content hash — avoid re-computing BGE embeddings.

Cache key: content_hash(text) + model_name + embed_type (query|passage|resume).
TTL: indefinite (embeddings are deterministic for same input).

Backends: in-memory LRU (default) or embeddings_cache DB table.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from mcf.lib.storage.base import Storage

logger = logging.getLogger(__name__)

# Default in-memory LRU size (content_hash -> embedding)
DEFAULT_LRU_MAXSIZE = 10_000


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized text. Deterministic for same content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _cache_key(content_hash_val: str, model_name: str, embed_type: str) -> str:
    return f"{content_hash_val}:{model_name}:{embed_type}"


class EmbeddingsCache:
    """Cache embeddings by content hash. LRU in-memory or DB-backed."""

    def __init__(
        self,
        *,
        store: Storage | None = None,
        lru_maxsize: int = DEFAULT_LRU_MAXSIZE,
    ) -> None:
        self._store = store
        self._lru: OrderedDict[str, list[float]] = OrderedDict()
        self._lru_maxsize = lru_maxsize

    def get(self, text: str, model_name: str, embed_type: str) -> list[float] | None:
        """Return cached embedding if present, else None."""
        ch = content_hash(text)
        key = _cache_key(ch, model_name, embed_type)

        # In-memory LRU
        if key in self._lru:
            self._lru.move_to_end(key)
            return self._lru[key]

        # DB backend
        if self._store and hasattr(self._store, "get_embedding_by_content_hash"):
            try:
                emb = self._store.get_embedding_by_content_hash(
                    content_hash=ch,
                    model_name=model_name,
                    embed_type=embed_type,
                )
                if emb is not None:
                    self._set_lru(key, emb)
                    return emb
            except Exception as e:
                logger.warning("embeddings_cache DB get failed: %s", e)

        return None

    def set(self, text: str, model_name: str, embed_type: str, embedding: list[float]) -> None:
        """Store embedding in cache."""
        ch = content_hash(text)
        key = _cache_key(ch, model_name, embed_type)

        self._set_lru(key, embedding)

        if self._store and hasattr(self._store, "upsert_embedding_cache"):
            try:
                self._store.upsert_embedding_cache(
                    content_hash=ch,
                    model_name=model_name,
                    embed_type=embed_type,
                    embedding=embedding,
                )
            except Exception as e:
                logger.warning("embeddings_cache DB set failed: %s", e)

    def _set_lru(self, key: str, embedding: list[float]) -> None:
        if key in self._lru:
            self._lru.move_to_end(key)
        else:
            if len(self._lru) >= self._lru_maxsize:
                self._lru.popitem(last=False)
        self._lru[key] = embedding


def get_or_compute(
    cache: EmbeddingsCache | None,
    text: str,
    model_name: str,
    embed_type: str,
    compute_fn: Callable[[], list[float]],
) -> list[float]:
    """Get from cache or compute. Handles errors gracefully."""
    if cache is not None:
        try:
            cached = cache.get(text, model_name, embed_type)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning("embeddings_cache get failed, computing: %s", e)

    try:
        embedding = compute_fn()
    except Exception as e:
        logger.exception("embedding compute failed: %s", e)
        raise

    if cache is not None:
        try:
            cache.set(text, model_name, embed_type, embedding)
        except Exception as e:
            logger.warning("embeddings_cache set failed (embedding computed): %s", e)

    return embedding
