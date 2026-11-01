"""Bulk-import re-embeddings from Kaggle output back into Supabase.

Batches the COPY + UPDATE in chunks to stay within Supabase's statement timeout.
Safe to run while production is live — no locks on the jobs table.

After this completes:
  1. Restart the Railway service to bust the 15-min active-jobs pool cache.
  2. Re-run scripts/finetune/casestudy_debug.py to verify score improvement.
  3. Re-run scripts/finetune/eval_lowball.py to verify pairwise accuracy holds.

Usage:
    uv run python scripts/finetune/import_embeddings.py
    uv run python scripts/finetune/import_embeddings.py --input data/job_embeddings_v2.parquet
"""

from __future__ import annotations

import argparse
import io
import os
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDING_DIMS = 768
BATCH = 500



def main(input_path: str) -> None:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    print(f"Loading {path} ({path.stat().st_size / 1e6:.0f} MB) — this may take ~30s…")
    df = pd.read_parquet(path)
    print(f"  {len(df):,} rows loaded")

    if "job_uuid" not in df.columns or "embedding" not in df.columns:
        raise ValueError("Parquet must have columns: job_uuid, embedding")

    sample = df["embedding"].iloc[0]
    if len(sample) != EMBEDDING_DIMS:
        raise ValueError(f"Expected {EMBEDDING_DIMS}-dim embeddings, got {len(sample)}")

    print("Connecting to Supabase…")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    print("  Connected.")
    conn.autocommit = False

    progress_file = Path(input_path).with_suffix(".progress")
    start_offset = 0
    if progress_file.exists():
        start_offset = int(progress_file.read_text().strip())
        print(f"Resuming from row {start_offset:,}")

    total_updated = 0
    t0 = time.perf_counter()
    chunks = [df.iloc[i:i + BATCH] for i in range(start_offset, len(df), BATCH)]
    print(f"Importing in {len(chunks)} batches of {BATCH:,}…\n")

    with tqdm(total=len(df), initial=start_offset, unit="rows", desc="Importing", mininterval=1.0) as pbar:
        for chunk_idx, chunk in enumerate(chunks):
            t_batch = time.perf_counter()
            for attempt in range(1, 6):
                try:
                    conn.rollback()
                    with conn.cursor() as cur:
                        cur.execute("SET LOCAL statement_timeout = 0")
                        cur.execute("SET LOCAL lock_timeout = '30s'")
                        cur.execute("DROP TABLE IF EXISTS _reembed_staging")
                        cur.execute(f"""
                            CREATE TEMP TABLE _reembed_staging (
                                job_uuid TEXT NOT NULL,
                                embedding vector({EMBEDDING_DIMS}) NOT NULL
                            ) ON COMMIT DROP
                        """)

                        lines = [
                            f"{job_uuid}\t[{','.join(map(str, emb))}]"
                            for job_uuid, emb in zip(chunk["job_uuid"], chunk["embedding"])
                        ]
                        buf = io.StringIO("\n".join(lines) + "\n")
                        cur.copy_expert("COPY _reembed_staging (job_uuid, embedding) FROM STDIN", buf)

                        cur.execute("SELECT COUNT(*) FROM _reembed_staging")
                        staged = cur.fetchone()[0]
                        if staged == 0:
                            raise RuntimeError("COPY loaded 0 rows into staging — format error?")

                        cur.execute("""
                            UPDATE job_embeddings je
                            SET embedding = s.embedding
                            FROM _reembed_staging s
                            WHERE je.job_uuid = s.job_uuid
                        """)
                        updated = cur.rowcount
                        tqdm.write(f"  staged={staged} updated={updated} first_uuid={lines[0].split(chr(9))[0]}", nolock=True)

                    conn.commit()
                    break
                except psycopg2.errors.LockNotAvailable:
                    conn.rollback()
                    wait = 15 * attempt
                    tqdm.write(f"  Lock contention (attempt {attempt}/5) — retrying in {wait}s…")
                    time.sleep(wait)
            else:
                raise RuntimeError("Failed to acquire lock after 5 attempts — autovacuum still running?")

            total_updated += updated
            current_pos = start_offset + (chunk_idx + 1) * BATCH
            progress_file.write_text(str(min(current_pos, len(df))))
            elapsed_batch = time.perf_counter() - t_batch
            rows_per_sec = len(chunk) / elapsed_batch if elapsed_batch > 0 else 0
            pbar.update(len(chunk))
            pbar.set_postfix(updated=f"{total_updated:,}", rows_s=f"{rows_per_sec:.0f}")

    conn.close()
    if progress_file.exists():
        progress_file.unlink()
    elapsed = time.perf_counter() - t0
    print(f"\n\nDone. Updated {total_updated:,} rows in {elapsed:.1f}s")
    print("\nNext steps:")
    print("  1. Restart Railway service to bust active-jobs pool cache")
    print("  2. uv run python scripts/finetune/casestudy_debug.py")
    print("  3. uv run python scripts/finetune/eval_lowball.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/job_embeddings_v2.parquet")
    args = parser.parse_args()
    main(args.input)
