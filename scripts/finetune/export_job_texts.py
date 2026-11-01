"""Export job texts for re-embedding on GPU (Kaggle).

Reads all jobs that have an existing embedding row, builds the canonical
job_text string (same format as ingestion), and writes to a Parquet file.
Run this locally before uploading to Kaggle.

Resumable: if the output file already exists, skips rows already written
and appends from where it left off.

Usage:
    uv run python scripts/finetune/export_job_texts.py
    uv run python scripts/finetune/export_job_texts.py --out data/job_texts.parquet
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description

DATABASE_URL = os.environ["DATABASE_URL"]
BATCH = 2_000

SCHEMA = pa.schema([("job_uuid", pa.string()), ("job_text", pa.string())])

FETCH_QUERY = """
SELECT j.job_uuid, j.title, j.description
FROM jobs j
JOIN job_embeddings e ON e.job_uuid = j.job_uuid
WHERE j.description IS NOT NULL
ORDER BY j.job_uuid
LIMIT %s OFFSET %s
"""

COUNT_QUERY = "SELECT COUNT(*) FROM jobs j JOIN job_embeddings e ON e.job_uuid = j.job_uuid"


def build_job_text(title: str, description: str) -> str:
    desc_text, _ = extract_high_signal_description(description, title)
    return f"Job Title: {title}\nDescription: {desc_text}"


def main(out_path: str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resume: count rows already written so we can skip them via OFFSET
    start_offset = 0
    if out.exists():
        existing = pq.read_metadata(out).num_rows
        print(f"Resuming from row {existing:,} (output file already has {existing:,} rows)")
        start_offset = existing

    print("Connecting to Supabase…")
    conn = psycopg2.connect(DATABASE_URL, options="-c statement_timeout=0")

    with conn.cursor() as cur:
        cur.execute(COUNT_QUERY)
        total_rows = cur.fetchone()[0]
    print(f"Total jobs in DB: {total_rows:,}  |  Remaining: {total_rows - start_offset:,}")

    # Write new batches to a temp file; merge with existing at the end if resuming.
    # (PyArrow doesn't support in-place append to an existing Parquet file.)
    tmp_path = out.with_suffix(".tmp.parquet")
    writer = pq.ParquetWriter(tmp_path, SCHEMA)

    total = 0
    offset = start_offset
    t0 = time.perf_counter()

    try:
        while True:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(FETCH_QUERY, (BATCH, offset))
                chunk = cur.fetchall()

            if not chunk:
                break

            uuids, texts = [], []
            for row in chunk:
                try:
                    job_text = build_job_text(row["title"] or "", row["description"] or "")
                    uuids.append(row["job_uuid"])
                    texts.append(job_text)
                except Exception as e:
                    print(f"\nSkipping {row['job_uuid']}: {e}")

            if uuids:
                writer.write_table(pa.table({"job_uuid": uuids, "job_text": texts}))
                total += len(uuids)

            offset += BATCH
            elapsed = time.perf_counter() - t0
            rate = total / elapsed if elapsed > 0 else 0
            done = start_offset + total
            print(f"  Written {done:,} / {total_rows:,}  ({rate:.0f} jobs/s)", end="\r")

    finally:
        writer.close()
        conn.close()

    elapsed = time.perf_counter() - t0
    print(f"\nDone. Wrote {total:,} new rows in {elapsed:.1f}s")

    # Merge existing + new into final output
    if start_offset > 0 and tmp_path.exists():
        print("Merging with existing file…")
        combined = pa.concat_tables([
            pq.read_table(out),
            pq.read_table(tmp_path),
        ])
        pq.write_table(combined, out)
        tmp_path.unlink()
    elif tmp_path.exists():
        tmp_path.rename(out)

    size_mb = out.stat().st_size / 1024 / 1024
    final_rows = pq.read_metadata(out).num_rows
    print(f"Saved to {out}  ({size_mb:.1f} MB, {final_rows:,} rows)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/job_texts.parquet")
    args = parser.parse_args()
    main(args.out)
