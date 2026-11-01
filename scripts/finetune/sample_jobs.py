"""Step 1 of the fine-tuning pipeline: sample 50k jobs from the DB.

Writes data/finetune/jobs_sample.jsonl — one job per line:
    {"job_uuid": "...", "title": "...", "description": "..."}

Usage:
    uv run python scripts/finetune/sample_jobs.py [--n 50000] [--output data/finetune/jobs_sample.jsonl]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50_000)
    parser.add_argument("--all", action="store_true", help="Dump all jobs (no LIMIT) — overrides --n")
    parser.add_argument("--output", default="data/finetune/jobs_sample.jsonl")
    args = parser.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    if args.all:
        print("Dumping ALL jobs from DB (no limit)...")
        cur.execute(
            """
            SELECT job_uuid, title, description
            FROM jobs
            WHERE description IS NOT NULL AND title IS NOT NULL
            ORDER BY last_seen_at DESC
            """
        )
    else:
        print(f"Sampling {args.n:,} jobs from DB...")
        cur.execute(
            """
            SELECT job_uuid, title, description
            FROM jobs
            WHERE description IS NOT NULL AND title IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
            """,
            (args.n,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    with out_path.open("w", encoding="utf-8") as f:
        for job_uuid, title, description in rows:
            f.write(json.dumps({"job_uuid": job_uuid, "title": title, "description": description}, ensure_ascii=False))
            f.write("\n")

    print(f"Wrote {len(rows):,} jobs to {out_path}")


if __name__ == "__main__":
    main()
