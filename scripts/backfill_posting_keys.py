# scripts/backfill_posting_keys.py
"""One-off backfill for SGSAL-024: content hashes, canonical pointers, field copy,
duplicate-vector deletion, posting_groups refresh.

Resumable: hashing selects only rows without a content_hash; canonical
assignment only touches NULL pointers; deletion recomputes its list each run.

Usage (repo root, DATABASE_URL in .env):
  uv run python scripts/backfill_posting_keys.py --dry-run      # hashes + canonicals + stats, NO deletes
  uv run python scripts/backfill_posting_keys.py --apply        # also copies fields and deletes dup vectors
  uv run python scripts/backfill_posting_keys.py --hash-only    # just step 1 (safe to run anytime)
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

from mcf.lib.pipeline.posting_key import posting_key  # noqa: E402
from mcf.lib.storage.postgres_store import PostgresStore  # noqa: E402


def step_hash(store: PostgresStore, batch: int) -> int:
    done, after, t0 = 0, "", time.perf_counter()
    while True:
        rows = store.iter_jobs_needing_hash(after, batch)
        if not rows:
            break
        store.set_content_hashes([(u, posting_key(t, d)) for u, t, d in rows])
        done += len(rows)
        after = rows[-1][0]
        if done % (batch * 10) == 0:
            rate = done / (time.perf_counter() - t0)
            print(f"  hashed {done:,} ({rate:,.0f}/s)", flush=True)
    print(f"step 1: hashed {done:,} jobs in {time.perf_counter() - t0:,.0f}s")
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=5000)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="hash + assign canonicals + print stats; no field copy, no deletes")
    g.add_argument("--apply", action="store_true", help="everything incl. deleting non-canonical vectors")
    g.add_argument("--hash-only", action="store_true")
    a = ap.parse_args()

    store = PostgresStore(os.environ["DATABASE_URL"])
    store.ensure_schema()

    step_hash(store, a.batch)
    if a.hash_only:
        return

    t = time.perf_counter()
    n = store.assign_canonicals()
    print(f"step 2: assigned {n:,} canonical pointers in {time.perf_counter() - t:,.0f}s")

    dups = store.noncanonical_embedded_uuids()
    print(f"        {len(dups):,} non-canonical jobs still hold a vector")

    if a.dry_run:
        t = time.perf_counter()
        store.refresh_posting_groups()
        print(f"step 5: posting_groups refreshed in {time.perf_counter() - t:,.0f}s")
        print("stats:", store.posting_group_stats())
        print("DRY RUN: no fields copied, no vectors deleted. Re-run with --apply.")
        return

    t = time.perf_counter()
    n = store.copy_fields_from_canonicals()
    print(f"step 3: copied LLM fields / Jev labels into {n:,} reposts in {time.perf_counter() - t:,.0f}s")

    t = time.perf_counter()
    deleted = 0
    for i in range(0, len(dups), a.batch):
        deleted += store.delete_embeddings_by_uuids(dups[i : i + a.batch])
        if (i // a.batch) % 10 == 0:
            print(f"  deleted {deleted:,}/{len(dups):,}", flush=True)
    print(f"step 4: deleted {deleted:,} duplicate vectors in {time.perf_counter() - t:,.0f}s")

    t = time.perf_counter()
    store.refresh_posting_groups()
    print(f"step 5: posting_groups refreshed in {time.perf_counter() - t:,.0f}s")
    print("stats:", store.posting_group_stats())
    print("Next: VACUUM (ANALYZE) job_embeddings; then SGSAL-025 step 1 (halfvec index) reclaims the HNSW space.")


if __name__ == "__main__":
    main()
