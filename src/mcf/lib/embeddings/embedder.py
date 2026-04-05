"""Text embedding utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache

# BGE retrieval models perform best when the *query* (the thing being searched
# with) carries a task-specific instruction prefix.  Passages (job descriptions)
# do NOT get this prefix.  See: https://huggingface.co/BAAI/bge-small-en-v1.5
_BGE_QUERY_PREFIX = "Represent this resume for job search: "


@dataclass(frozen=True)
class EmbedderConfig:
    # BAAI/bge-base-en-v1.5 is a retrieval-optimised model:
    #   • 512 token limit
    #   • 768 dimensions  (upgraded from 384 / bge-small-en-v1.5)
    #   • asymmetric query/passage design  → better for job matching
    #   • MTEB retrieval NDCG@10: 53.3 vs 51.7 for small (~3% improvement)
    model_name: str = "BAAI/bge-base-en-v1.5"
    batch_size: int = 32


class Embedder:
    """SentenceTransformers-based embedder.

    Kept behind a small wrapper so the rest of the codebase doesn't depend on
    sentence-transformers directly.

    Usage pattern:
        embedder.embed_text(job_text)   # passage side  – job descriptions
        embedder.embed_query(resume)    # query side    – resume / candidate
    """

    def __init__(
        self,
        config: EmbedderConfig | None = None,
        embeddings_cache: EmbeddingsCache | None = None,
    ) -> None:
        self.config = config or EmbedderConfig()
        self._embeddings_cache = embeddings_cache
        # Import lazily so the base crawler can run without embedding deps installed.
        from sentence_transformers import SentenceTransformer  # type: ignore

        self._model = SentenceTransformer(self.config.model_name)

    @property
    def model_name(self) -> str:
        return self.config.model_name

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of passage texts (job descriptions).  No prefix added."""
        cache = self._embeddings_cache
        model = self.model_name

        if not cache:
            vectors = self._model.encode(
                texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return [v.tolist() for v in vectors]

        out: list[list[float]] = []
        to_compute: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            cached = cache.get(text, model, "passage")
            if cached is not None:
                out.append(cached)
            else:
                out.append([])  # placeholder
                to_compute.append((i, text))

        if to_compute:
            compute_texts = [t for _, t in to_compute]
            vectors = self._model.encode(
                compute_texts,
                batch_size=self.config.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for (idx, text), vec in zip(to_compute, vectors):
                emb = vec.tolist()
                cache.set(text, model, "passage", emb)
                out[idx] = emb

        return out

    def embed_text(self, text: str) -> list[float]:
        """Embed a single passage text (job description side)."""
        return self.embed_texts([text])[0]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query text (resume / candidate side) with the BGE task prefix.

        BGE models are trained with an asymmetric setup: the query gets a short
        instruction prefix while passages do not.  Using this method for resumes
        and ``embed_text`` for job descriptions gives the best retrieval quality.
        """
        cache = self._embeddings_cache
        model = self.model_name
        if cache:
            cached = cache.get(text, model, "query")
            if cached is not None:
                return cached

        is_bge = "bge" in model.lower()
        query = (_BGE_QUERY_PREFIX + text) if is_bge else text
        result = self.embed_texts([query])[0]

        if cache:
            cache.set(text, model, "query", result)
        return result

    def embed_resume(self, text: str, chunk_size: int = 400, overlap: int = 80) -> list[float]:
        """Embed resume text, chunking if long to avoid BGE 512-token truncation.

        For short resumes (≤ chunk_size tokens approx) this is a single embed_query.
        For longer resumes, splits into overlapping chunks, embeds each, then
        L2-normalizes the mean of chunk embeddings.
        """
        cache = self._embeddings_cache
        model = self.model_name
        if cache:
            cached = cache.get(text, model, "resume")
            if cached is not None:
                return cached

        words = text.split()
        # ~0.75 words per token; chunk_size tokens ≈ chunk_size * 4/3 words
        max_words = int(chunk_size * 4 / 3)
        overlap_words = int(overlap * 4 / 3)

        if len(words) <= max_words:
            result = self.embed_query(text)
            if cache:
                cache.set(text, model, "resume", result)
            return result

        chunks: list[str] = []
        start = 0
        while start < len(words):
            end = min(start + max_words, len(words))
            chunks.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start = end - overlap_words

        embeddings = [self.embed_query(c) for c in chunks]
        mean_vec = np.array(embeddings, dtype=np.float32).mean(axis=0)
        norm = float(np.linalg.norm(mean_vec))
        if norm > 0:
            mean_vec = mean_vec / norm
        result = mean_vec.tolist()

        if cache:
            cache.set(text, model, "resume", result)
        return result

