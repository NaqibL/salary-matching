"""Job classification utilities — role cluster + experience tier.

Models are loaded lazily on first call and cached for the lifetime of the process.

Usage:
    from mcf.matching.classifiers import classify_jobs
    results = classify_jobs(embeddings)   # list of (role_cluster, predicted_tier)
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.linear_model import LogisticRegression

_MODELS_DIR = Path(__file__).parent.parent / "models"

_km: MiniBatchKMeans | None = None
_lr: LogisticRegression | None = None
_taxonomy: dict[int, str] | None = None


def _load() -> None:
    global _km, _lr, _taxonomy
    if _km is not None:
        return
    with open(_MODELS_DIR / "kmeans_role_v2.pkl", "rb") as f:
        _km = pickle.load(f)
    with open(_MODELS_DIR / "lr_tier_v2.pkl", "rb") as f:
        _lr = pickle.load(f)
    _taxonomy = {
        int(k): v
        for k, v in json.loads((_MODELS_DIR / "role_taxonomy_v2.json").read_text()).items()
    }


def classify_jobs(
    embeddings: np.ndarray,
) -> list[tuple[int, str]]:
    """Classify a batch of job embeddings.

    Args:
        embeddings: float32 array of shape (n, 768), L2-normalised.

    Returns:
        List of (role_cluster_id, predicted_tier) per job.
        role_cluster_id is 0-38, predicted_tier is one of:
        T1_Entry / T2_Junior / T3_Senior / T4_Management.
    """
    _load()
    assert _km is not None and _lr is not None
    role_clusters = _km.predict(embeddings)
    predicted_tiers = _lr.predict(embeddings)
    return list(zip((int(c) for c in role_clusters), predicted_tiers))


def classify_jobs_multilabel(
    embeddings: np.ndarray,
    threshold: float = 0.85,
) -> list[list[int]]:
    """Return all cluster IDs with cosine similarity >= threshold for each embedding.

    The primary cluster (nearest centroid) is always included, even if below threshold.
    At threshold=0.85, ~45% of jobs match 2+ clusters (avg 1.89 labels/job).

    Args:
        embeddings: float32 array of shape (n, 768), L2-normalised.
        threshold: cosine similarity cutoff (default 0.85).

    Returns:
        List of cluster ID lists, one per job. Always non-empty.
    """
    _load()
    assert _km is not None

    centroids = _km.cluster_centers_  # (35, 768)
    centroid_norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    centroids_normed = centroids / np.clip(centroid_norms, 1e-10, None)

    emb_norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embs_normed = embeddings / np.clip(emb_norms, 1e-10, None)

    # similarities: (n_jobs, 35)
    similarities = embs_normed @ centroids_normed.T

    result = []
    for i, sim_row in enumerate(similarities):
        clusters = [int(j) for j, s in enumerate(sim_row) if s >= threshold]
        if not clusters:
            # Always include at least the nearest centroid
            clusters = [int(np.argmax(sim_row))]
        result.append(clusters)
    return result


def predict_candidate_tier(embedding: list[float] | np.ndarray) -> str:
    """Predict experience tier for a single candidate embedding.

    Args:
        embedding: 768-dim float vector (L2-normalised resume embedding).

    Returns:
        One of T1_Entry / T2_Junior / T3_Senior / T4_Management.
    """
    _load()
    assert _lr is not None
    arr = np.array(embedding, dtype=np.float32).reshape(1, -1)
    return str(_lr.predict(arr)[0])


def role_name(cluster_id: int) -> str:
    """Return the human-readable role name for a cluster ID."""
    _load()
    assert _taxonomy is not None
    return _taxonomy.get(cluster_id, f"Cluster {cluster_id}")
