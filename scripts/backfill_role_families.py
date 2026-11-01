"""Backfill Jev role families + tiers for active jobs that have none (SGSAL-022 C5).

Resumable: selects only active jobs with role_family IS NULL, so re-running
after an interruption continues where it left off.

Usage (from repo root, DATABASE_URL + OPENROUTER_API_KEY in .env):
  uv run python scripts/backfill_role_families.py --limit 200 --dry-run   # try 200
  uv run python scripts/backfill_role_families.py                         # all
  uv run python scripts/backfill_role_families.py --workers 12 --batch 400
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from mcf.lib.embeddings.jev_classifier import (  # noqa: E402
    ROLE_FAMILY_ID,
    make_jev_classifier_from_env,
    role_family_rows,
)
from mcf.lib.storage.postgres_store import PostgresStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="stop after this many jobs")
    ap.add_argument("--batch", type=int, default=400, help="jobs fetched/written per batch")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="classify but do not write")
    a = ap.parse_args()

    jev = make_jev_classifier_from_env()
    if jev is None:
        sys.exit("OPENROUTER_API_KEY missing or JEV_CLASSIFIER_ENABLED=0")
    store = PostgresStore(os.environ["DATABASE_URL"])
    store.ensure_schema()
    store.upsert_role_families(role_family_rows())

    total = store.count_active_jobs_missing_role_family()
    target = min(total, a.limit) if a.limit else total
    print(f"active jobs without role_family: {total:,}; processing {target:,} "
          f"(batch {a.batch}, {a.workers} workers, model {jev.model}{', DRY RUN' if a.dry_run else ''})")

    done = failed = 0
    cost = 0.0
    t0 = time.perf_counter()
    while done < target:
        jobs = store.get_active_jobs_missing_role_family(limit=min(a.batch, target - done))
        if not jobs:
            break
        results = jev.classify_many(
            [(j["title"], j["description"], j["position_levels"]) for j in jobs],
            workers=a.workers,
        )
        rows = []
        for j, r in zip(jobs, results):
            if r is None:
                failed += 1
                continue
            cost += r.cost_usd
            rows.append((j["job_uuid"], r.role_key, ROLE_FAMILY_ID[r.role_key], r.tier, r.role_conf, r.tier_conf))
        if a.dry_run:
            for j, r in list(zip(jobs, results))[:10]:
                print(f"  {j['title'][:55]:55} -> {r.role_key if r else 'FAIL'} / {r.tier if r else '-'}"
                      f" ({r.role_conf:.2f}/{r.tier_conf:.2f})" if r else "")
            done += len(jobs)
            if failed == len(jobs):
                sys.exit("every call failed; aborting")
            break  # dry run: one batch only
        store.batch_upsert_jev_classifications(rows)
        done += len(jobs)
        elapsed = time.perf_counter() - t0
        rate = done / elapsed if elapsed else 0.0
        eta = (target - done) / rate / 60 if rate else 0.0
        print(f"  {done:,}/{target:,} done, {failed} failed, ${cost:.3f}, "
              f"{rate:.1f} jobs/s, ~{eta:.0f} min left", flush=True)
        if failed and failed >= max(50, done // 4):
            sys.exit(f"too many failures ({failed}); aborting so a bad key/model doesn't burn the batch")

    print(f"\nfinished: {done:,} processed, {failed} failed, ${cost:.3f}, "
          f"{(time.perf_counter() - t0) / 60:.1f} min")
    jev.close()
    store.close()


if __name__ == "__main__":
    main()
