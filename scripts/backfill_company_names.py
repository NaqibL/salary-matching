"""Backfill company_name for jobs where it is currently NULL.

Usage:
    uv run python scripts/backfill_company_names.py [--rate-limit 8] [--batch 200] [--dry-run]

Fetches each job's detail from the MCF API and updates company_name in the
database. The COALESCE upsert pattern is NOT used here — we do a direct UPDATE
so only NULL rows are touched and existing names are never overwritten.

Rate limit defaults to 8 req/s (~100 min for 47k jobs). Increase with caution
to avoid 403 blocks; the MCFClient will retry but with long waits.
"""

from __future__ import annotations

import argparse
import sys
import time

import psycopg2

from mcf.lib.external.client import MCFClient
from mcf.lib.sources.mcf_source import _mcf_raw_to_normalized
from mcf.api.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill company_name from MCF API")
    parser.add_argument("--rate-limit", type=float, default=8.0, help="Requests per second (default 8)")
    parser.add_argument("--batch", type=int, default=200, help="DB commit batch size (default 200)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but do not write to DB")
    args = parser.parse_args()

    db_url = settings.database_url
    if not db_url:
        sys.exit("DATABASE_URL is not set")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute(
        "SELECT job_uuid FROM jobs WHERE is_active = TRUE AND (company_name IS NULL OR company_name = '') ORDER BY last_seen_at DESC"
    )
    uuids: list[str] = [r[0] for r in cur.fetchall()]
    total = len(uuids)
    print(f"Jobs needing company_name backfill: {total}")

    if total == 0:
        print("Nothing to do.")
        conn.close()
        return

    updated = 0
    skipped = 0
    errors = 0
    start = time.monotonic()

    with MCFClient(rate_limit=args.rate_limit) as client:
        for i, uuid in enumerate(uuids, 1):
            try:
                detail = client.get_job_detail(uuid)
                raw = detail.model_dump(by_alias=True, mode="json")
                job = _mcf_raw_to_normalized(raw, uuid)

                if job.company_name:
                    if not args.dry_run:
                        cur.execute(
                            "UPDATE jobs SET company_name = %s WHERE job_uuid = %s AND company_name IS NULL",
                            (job.company_name, uuid),
                        )
                    updated += 1
                else:
                    skipped += 1

                if not args.dry_run and i % args.batch == 0:
                    conn.commit()

            except Exception as exc:
                errors += 1
                print(f"  [ERROR] {uuid}: {exc}")

            if i % 500 == 0 or i == total:
                elapsed = time.monotonic() - start
                rate = i / elapsed
                eta = (total - i) / rate if rate > 0 else 0
                print(
                    f"  {i}/{total} — updated={updated} skipped={skipped} errors={errors} "
                    f"rate={rate:.1f}/s ETA={eta/60:.1f}min"
                )

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone. updated={updated} skipped={skipped} errors={errors}")
    if args.dry_run:
        print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
