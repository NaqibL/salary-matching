"""Seed hot_jobs_cluster_centroids from km_centroids.npy + cluster_profiles.csv.

Usage:
    uv run python scripts/seed_hot_jobs_centroids.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "cluster_analysis_output"


def main() -> None:
    centroids = np.load(OUTPUT_DIR / "km_centroids.npy")
    profiles = pd.read_csv(OUTPUT_DIR / "cluster_profiles.csv")
    labels = {
        int(row["cluster"]): row["top_titles"].split(" | ")[0]
        for _, row in profiles.iterrows()
    }

    assert centroids.shape[0] == len(labels), (
        f"centroid count {centroids.shape[0]} != cluster_profiles rows {len(labels)}"
    )

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 0")

    for cluster_id, centroid in enumerate(centroids):
        cur.execute(
            "INSERT INTO hot_jobs_cluster_centroids (cluster_id, label, centroid) VALUES (%s, %s, %s) "
            "ON CONFLICT (cluster_id) DO UPDATE SET centroid = EXCLUDED.centroid, label = EXCLUDED.label",
            (cluster_id, labels[cluster_id], json.dumps(centroid.tolist())),
        )

    conn.commit()
    cur.execute("SELECT count(*) FROM hot_jobs_cluster_centroids")
    print(f"Seeded {cur.fetchone()[0]} rows into hot_jobs_cluster_centroids")
    conn.close()


if __name__ == "__main__":
    main()
