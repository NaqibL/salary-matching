"""Preview or apply the company name-variant merge (SGSAL-032).

The crawl runs the same step automatically at its end; this script is for looking first.

    uv run python scripts/link_company_names.py            # preview: prints the groups, writes nothing
    uv run python scripts/link_company_names.py --apply    # merge now, then refresh company_stats

Spelling variants of one organisation (same ``mcf.lib.companies.names.name_key``) get one
display name in ``jobs.company_canonical``; the other spellings go to ``company_aliases``.
No job row is deleted. To undo a group, set ``company_canonical`` back to NULL for its ads
and delete its ``company_aliases`` rows.
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from mcf.lib.storage.postgres_store import PostgresStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the merge (default: preview only)")
    args = parser.parse_args()
    load_dotenv()
    store = PostgresStore(os.environ["DATABASE_URL"])
    groups = store.link_company_name_variants(dry_run=not args.apply)
    for g in sorted(groups, key=lambda g: g["display"].lower()):
        print(f"{g['display']}  <=  " + "  |  ".join(g["merged"]) + (f"   ({g['jobs']} ads)" if args.apply else ""))
    print(f"\n{len(groups)} groups" + (f", {sum(g['jobs'] for g in groups)} ads updated" if args.apply else " would be merged (preview; nothing written)"))
    if args.apply and groups:
        store.refresh_posting_groups()
        store.refresh_company_stats()
        store.refresh_market_stats()
        print("Refreshed posting_groups, company_stats and market_stats")


if __name__ == "__main__":
    main()
