"""Backfill the posting-company registry (SGSAL-028).

For every active MyCareersFuture company with no `companies` row, fetch one of its job details
from the MCF API and store the posting company's UEN, SSIC codes and headcount. Idempotent and
resumable: re-running only touches companies that are still missing.

    uv run python scripts/backfill_companies.py [--min-active 1] [--limit 20000] [--rps 4]

Afterwards: REFRESH MATERIALIZED VIEW CONCURRENTLY company_stats (or wait for the next crawl).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

MCF_JOB_URL = "https://api.mycareersfuture.gov.sg/v2/jobs/{uuid}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sglowball-registry/1.0)", "Accept": "application/json"}


def fetch_posted_company(job_uuid: str) -> dict | None:
    req = urllib.request.Request(MCF_JOB_URL.format(uuid=job_uuid), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    company = data.get("postedCompany") or data.get("hiringCompany")
    return company if isinstance(company, dict) else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-active", type=int, default=1, help="only companies with at least this many active jobs")
    ap.add_argument("--limit", type=int, default=20000)
    ap.add_argument("--rps", type=float, default=4.0, help="max requests per second to the MCF API")
    args = ap.parse_args()

    load_dotenv(".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    from mcf.lib.storage.postgres_store import PostgresStore

    store = PostgresStore(url)
    todo = store.get_companies_missing_registry(min_active=args.min_active, limit=args.limit)
    print(f"{len(todo):,} companies missing from the registry")
    delay = 1.0 / max(args.rps, 0.1)
    done = failed = empty = 0
    t0 = time.time()
    for i, (name, job_uuid) in enumerate(todo, 1):
        started = time.time()
        try:
            pc = fetch_posted_company(job_uuid)
        except urllib.error.HTTPError as e:
            failed += 1
            if e.code == 429:
                time.sleep(10)
            pc = None
        except Exception:  # noqa: BLE001
            failed += 1
            pc = None
        if pc is None:
            # record the miss so we do not retry forever; source stays 'mcf' with no SSIC
            try:
                store.upsert_company(name=name, source="mcf")
                empty += 1
            except Exception as e:  # noqa: BLE001
                print(f"  upsert failed for {name!r}: {e}")
        else:
            emp = pc.get("employeeCount")
            try:
                store.upsert_company(
                    name=pc.get("name") or name,
                    uen=pc.get("uen") or None,
                    ssic_code=pc.get("ssicCode") or None,
                    ssic_code_2020=pc.get("ssicCode2020") or None,
                    ssic_description=(pc.get("ssicDescription2020") or "").strip() or None,
                    employee_count=int(emp) if isinstance(emp, (int, float)) else None,
                    source="mcf",
                )
                # the posting company name on the job row may differ in case/alias from the
                # registry name; key both so the aggregation join always hits
                if (pc.get("name") or "").strip().lower() != name.strip().lower():
                    store.upsert_company(
                        name=name,
                        uen=pc.get("uen") or None,
                        ssic_code=pc.get("ssicCode") or None,
                        ssic_code_2020=pc.get("ssicCode2020") or None,
                        ssic_description=(pc.get("ssicDescription2020") or "").strip() or None,
                        employee_count=int(emp) if isinstance(emp, (int, float)) else None,
                        source="mcf",
                    )
                done += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"  upsert failed for {name!r}: {e}")
        if i % 200 == 0 or i == len(todo):
            rate = i / max(time.time() - t0, 1e-6)
            print(f"  {i:,}/{len(todo):,}  stored {done:,}  no-company {empty:,}  failed {failed:,}  "
                  f"({rate:.1f}/s, ~{(len(todo) - i) / max(rate, 1e-6) / 60:.0f} min left)", flush=True)
        spent = time.time() - started
        if spent < delay:
            time.sleep(delay - spent)
    print(f"done: stored {done:,}, no-company {empty:,}, failed {failed:,} in {(time.time() - t0) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
