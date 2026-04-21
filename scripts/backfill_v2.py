"""Re-classify ALL active embedded jobs with the v2 KMeans + LR models.

Overwrites role_cluster, predicted_tier, and role_clusters_json for every
active job that has an embedding — regardless of existing values.

Run this against production BEFORE pushing the classifiers.py update to Railway.

Usage:
    uv run python scripts/backfill_v2.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from mcf.matching.classifiers import classify_jobs, classify_jobs_multilabel

DATABASE_URL = os.environ["DATABASE_URL"]
BATCH = 2_000
EMBEDDING_DIMS = 768

FETCH_QUERY = """
SELECT j.job_uuid, e.embedding::text
FROM jobs j
JOIN job_embeddings e ON e.job_uuid = j.job_uuid
WHERE j.is_active = TRUE
  AND e.embedding IS NOT NULL
ORDER BY j.job_uuid
LIMIT %s OFFSET %s
"""

print("Connecting to Supabase…")
conn = psycopg2.connect(DATABASE_URL, options="-c statement_timeout=0")
conn.autocommit = False

total = 0
offset = 0
t0 = time.perf_counter()

while True:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FETCH_QUERY, (BATCH, offset))
        chunk = cur.fetchall()

    if not chunk:
        break

    rows: list[tuple[str, list[float]]] = []
    for row in chunk:
        try:
            emb = json.loads(row["embedding"]) if isinstance(row["embedding"], str) else list(row["embedding"])
            if len(emb) != EMBEDDING_DIMS:
                continue
            rows.append((row["job_uuid"], emb))
        except Exception:
            continue

    if rows:
        uuids = [r[0] for r in rows]
        X = np.array([r[1] for r in rows], dtype=np.float32)

        # Primary cluster + tier
        classifications = classify_jobs(X)
        with conn.cursor() as wc:
            psycopg2.extras.execute_batch(
                wc,
                "UPDATE jobs SET role_cluster = %s, predicted_tier = %s WHERE job_uuid = %s",
                [(rc, tier, uuid) for uuid, (rc, tier) in zip(uuids, classifications)],
                page_size=500,
            )

        # Multi-label clusters
        multi_labels = classify_jobs_multilabel(X)
        with conn.cursor() as wc:
            psycopg2.extras.execute_batch(
                wc,
                "UPDATE jobs SET role_clusters_json = %s WHERE job_uuid = %s",
                [(clusters, uuid) for uuid, clusters in zip(uuids, multi_labels)],
                page_size=500,
            )

        conn.commit()
        total += len(rows)

    offset += BATCH
    elapsed = time.perf_counter() - t0
    rate = total / elapsed if elapsed > 0 else 0
    print(f"  Classified {total:,} jobs  ({rate:.0f} jobs/s)", end="\r")

conn.close()
elapsed = time.perf_counter() - t0
print(f"\nDone. Classified {total:,} jobs in {elapsed:.1f}s ({total/elapsed:.0f} jobs/s)")
