"""
Backfill role_cluster and predicted_tier for all active jobs that already have embeddings.
Run once after applying migration 009.

Usage:
    uv run python scripts/backfill_classifications.py
"""

from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")

import json, os, time
from pathlib import Path

import numpy as np
import psycopg2, psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from mcf.lib.classifiers import classify_jobs

DATABASE_URL = os.environ["DATABASE_URL"]

FETCH_QUERY = """
SELECT j.job_uuid, e.embedding::text
FROM jobs j
JOIN job_embeddings e ON e.job_uuid = j.job_uuid
WHERE j.is_active = TRUE
  AND e.embedding IS NOT NULL
  AND j.role_cluster IS NULL
"""

BATCH = 2000

def flush(buf: list[tuple[str, list[float]]], conn) -> None:
    if not buf:
        return
    uuids = [r[0] for r in buf]
    X = np.array([r[1] for r in buf], dtype=np.float32)
    results = classify_jobs(X)
    with conn.cursor() as wc:
        psycopg2.extras.execute_batch(
            wc,
            "UPDATE jobs SET role_cluster = %s, predicted_tier = %s WHERE job_uuid = %s",
            [(rc, tier, uuid) for uuid, (rc, tier) in zip(uuids, results)],
            page_size=500,
        )
    conn.commit()

print("Connecting to Supabase...")
conn = psycopg2.connect(DATABASE_URL, options="-c statement_timeout=0")
conn.autocommit = False

total = 0
t0 = time.perf_counter()

# Re-query after each commit — processed jobs have role_cluster set so won't reappear
while True:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FETCH_QUERY + f" LIMIT {BATCH}")
        chunk = cur.fetchall()

    if not chunk:
        break

    rows_buf: list[tuple[str, list[float]]] = []
    for row in chunk:
        try:
            emb = json.loads(row["embedding"]) if isinstance(row["embedding"], str) else list(row["embedding"])
            if len(emb) != 768:
                continue
            rows_buf.append((row["job_uuid"], emb))
        except Exception:
            continue

    flush(rows_buf, conn)
    total += len(rows_buf)
    elapsed = time.perf_counter() - t0
    print(f"  Classified {total:,} jobs  ({total/elapsed:.0f} jobs/s)", end="\r")

conn.close()

elapsed = time.perf_counter() - t0
print(f"\nDone. Classified {total:,} jobs in {elapsed:.1f}s ({total/elapsed:.0f} jobs/s)")
