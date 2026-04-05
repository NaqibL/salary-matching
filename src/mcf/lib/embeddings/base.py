"""Embedder protocol – swap embedding models without touching pipeline code."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Interface that every embedder implementation must satisfy."""

    @property
    def model_name(self) -> str:
        """Identifier for the underlying model (used as a key in the DB)."""
        ...

    def embed_text(self, text: str) -> list[float]:
        """Embed a single passage text (job description side)."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of passage texts (job description side)."""
        ...

    def embed_query(self, query: str) -> list[float]:
        """Embed a query text (resume / candidate side).

        Some retrieval models (e.g. BGE) use an asymmetric setup where the
        query gets a task-specific prefix while passages do not.  Implementations
        should handle that distinction here.
        """
        ...

    def embed_resume(self, text: str, chunk_size: int = 400, overlap: int = 80) -> list[float]:
        """Embed resume text, chunking if long. Default impl: embed_query(text)."""
        ...
