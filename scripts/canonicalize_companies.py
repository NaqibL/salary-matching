"""LLM canonicalization of company names using Gemini 2.5 Flash via OpenRouter.

Pass 1 — batch all distinct raw company names not yet in company_aliases
          through the LLM; store {raw_name → canonical_name} in company_aliases.

Pass 2 — detect cross-batch duplicates among canonical names using prefix
          adjacency; LLM arbitrates each candidate pair; merges them in
          company_aliases.

Final   — UPDATE jobs SET company_canonical from company_aliases.

Re-running the script is safe and handles new companies: only raw names
absent from company_aliases are sent to the LLM.

Usage:
    uv run python scripts/canonicalize_companies.py
    uv run python scripts/canonicalize_companies.py --dry-run
    uv run python scripts/canonicalize_companies.py --batch 150 --skip-second-pass
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

_CANONICALIZE_SYSTEM = """\
You are cleaning company names scraped from Singapore job listings.

For each name in the input JSON array, return the clean canonical name:
- Strip legal suffixes: "Pte Ltd", "Pte. Ltd.", "Pte. Limited", "Ltd", "Limited", \
"Sdn Bhd", "Sdn. Bhd.", "Inc", "Corp", "Co.", "(S)", "(Singapore)", "Pte"
- Fix capitalisation: "GOOGLE" → "Google", "dbs bank" → "DBS Bank"
- Well-known abbreviations stay abbreviated: "NUS", "NTU", "DBS", "OCBC", "UOB", \
"CPF", "HDB", "MAS", "SIA", "SGH", "TTSH", "A*STAR"
- Regional subsidiaries collapse to their parent brand: \
"Google Asia Pacific" → "Google", "Meta Platforms Singapore" → "Meta", \
"Amazon Web Services" → "AWS"
- Data artifacts (names made of only symbols like ?, *, =, $, #) → return null

Return ONLY a JSON object mapping each input name to its canonical string (or null).
No explanation, no markdown fences. Example:
{"GOOGLE ASIA PACIFIC PTE. LTD.": "Google", "ABC TRADING PTE LTD": "ABC Trading", "???": null}
"""

_DEDUP_SYSTEM = """\
You are deduplicating canonical company names from Singapore job listings.

You will receive a JSON array of all distinct canonical names.
Find groups of names that refer to the same real-world company.

Rules:
- Only group names you are confident refer to the same company.
- The FIRST name in each group should be the best form: shortest and most widely recognised.
  e.g. prefer "Google" over "Google Asia Pacific", "DBS Bank" over "DBS Bank Limited".
- Include parent/subsidiary collapses: "Google Asia Pacific" belongs under "Google".
- Do NOT merge genuinely distinct companies (e.g. "Grab" and "Gojek" are different).

Return ONLY a JSON array of groups. Each group is a list of names (best form first).
If there are no duplicates at all, return [].
No explanation, no markdown fences.

Example output:
[["Google", "Google Asia Pacific", "Google Singapore"], ["DBS Bank", "DBS"]]
"""


def _parse_json(text: str) -> dict | list | None:
    """Extract the first JSON object or array from an LLM response."""
    text = text.strip()
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _call_llm(
    client: httpx.Client,
    api_key: str,
    system: str,
    user_content: str,
    retries: int = 3,
) -> str | None:
    for attempt in range(retries):
        try:
            resp = client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            wait = 2 ** attempt
            print(f"    [retry {attempt+1}/{retries}] {exc} — waiting {wait}s")
            time.sleep(wait)
    return None


def pass1_canonicalize(
    cur,
    client: httpx.Client,
    api_key: str,
    raw_names: list[str],
    batch_size: int,
    dry_run: bool,
) -> dict[str, str]:
    """Send raw names to LLM in batches; upsert results into company_aliases."""
    total = len(raw_names)
    print(f"\n=== Pass 1: canonicalizing {total} raw names (batch={batch_size}) ===")

    mapping: dict[str, str] = {}
    errors = 0

    for i in range(0, total, batch_size):
        batch = raw_names[i : i + batch_size]
        user_msg = json.dumps(batch, ensure_ascii=False)

        raw_output = _call_llm(client, api_key, _CANONICALIZE_SYSTEM, user_msg)
        if raw_output is None:
            print(f"  batch {i//batch_size+1}: LLM call failed, skipping")
            errors += len(batch)
            continue

        parsed = _parse_json(raw_output)
        if not isinstance(parsed, dict):
            print(f"  batch {i//batch_size+1}: unexpected output format, skipping")
            errors += len(batch)
            continue

        batch_mapping: dict[str, str] = {}
        for raw, canonical in parsed.items():
            if isinstance(canonical, str) and canonical.strip():
                batch_mapping[raw] = canonical.strip()
            else:
                batch_mapping[raw] = raw  # fallback: keep raw name if LLM returns null/garbage

        mapping.update(batch_mapping)

        if not dry_run:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO company_aliases (raw_name, canonical_name)
                VALUES %s
                ON CONFLICT (raw_name) DO UPDATE SET canonical_name = EXCLUDED.canonical_name
                """,
                [(k, v) for k, v in batch_mapping.items()],
            )

        done = min(i + batch_size, total)
        print(f"  {done}/{total} — batch ok ({len(batch_mapping)} mapped, {errors} errors so far)")

    print(f"Pass 1 done. mapped={len(mapping)} errors={errors}")
    return mapping


def pass2_dedup(
    cur,
    client: httpx.Client,
    api_key: str,
    dry_run: bool,
    batch_size: int = 600,
) -> int:
    """Send all canonical names to LLM; it returns duplicate groups to merge."""
    print("\n=== Pass 2: full-list deduplication ===")

    cur.execute("SELECT DISTINCT canonical_name FROM company_aliases ORDER BY canonical_name")
    canonicals = [r[0] for r in cur.fetchall()]
    print(f"  {len(canonicals)} distinct canonical names")

    if not canonicals:
        print("  Nothing to deduplicate.")
        return 0

    # Split into alphabetical batches with a one-letter overlap at boundaries so
    # names near a split point appear in both adjacent batches.
    # For most SG job boards this fits in one batch (~few hundred canonical names).
    merges: dict[str, str] = {}  # loser → winner

    batches: list[list[str]] = []
    for i in range(0, len(canonicals), batch_size):
        chunk = canonicals[i : i + batch_size]
        # Include last 10 names of previous batch as overlap to catch boundary duplicates
        if i > 0:
            chunk = canonicals[max(0, i - 10) : i + batch_size]
        batches.append(chunk)

    print(f"  Sending {len(batches)} batch(es) to LLM")

    for b_idx, batch in enumerate(batches):
        user_msg = json.dumps(batch, ensure_ascii=False)
        raw_output = _call_llm(client, api_key, _DEDUP_SYSTEM, user_msg)
        if raw_output is None:
            print(f"  batch {b_idx + 1}: LLM call failed, skipping")
            continue

        groups = _parse_json(raw_output)
        if not isinstance(groups, list):
            print(f"  batch {b_idx + 1}: unexpected output format, skipping")
            continue

        if not groups:
            print(f"  batch {b_idx + 1}: no duplicates found")
            continue

        for group in groups:
            if not isinstance(group, list) or len(group) < 2:
                continue
            # Validate all names are known canonicals (guards against LLM hallucination)
            valid = [n for n in group if isinstance(n, str) and n.strip() in canonicals]
            if len(valid) < 2:
                continue
            winner = valid[0].strip()
            for loser in valid[1:]:
                loser = loser.strip()
                if loser != winner:
                    merges[loser] = winner
                    print(f"    MERGE: '{loser}' → '{winner}'")

    print(f"  {len(merges)} merge(s) identified")

    if not merges:
        print("  No duplicates to merge.")
        return 0

    if dry_run:
        print(f"  [dry-run] would apply {len(merges)} merge(s)")
        return len(merges)

    for loser, winner in merges.items():
        cur.execute(
            "UPDATE company_aliases SET canonical_name = %s WHERE canonical_name = %s",
            (winner, loser),
        )

    print(f"Pass 2 done. merged={len(merges)}")
    return len(merges)


def apply_to_jobs(cur, dry_run: bool) -> int:
    """Update jobs.company_canonical from company_aliases."""
    print("\n=== Final: updating jobs.company_canonical ===")
    if dry_run:
        cur.execute(
            """
            SELECT COUNT(*) FROM jobs j
            JOIN company_aliases a ON j.company_name = a.raw_name
            WHERE j.company_canonical IS DISTINCT FROM a.canonical_name
            """
        )
        count = cur.fetchone()[0]
        print(f"  [dry-run] would update {count} job rows")
        return count

    cur.execute("SET statement_timeout = 0")
    cur.execute(
        """
        UPDATE jobs
        SET company_canonical = a.canonical_name
        FROM company_aliases a
        WHERE jobs.company_name = a.raw_name
          AND jobs.company_canonical IS DISTINCT FROM a.canonical_name
        """
    )
    updated = cur.rowcount
    print(f"  Updated {updated} job rows")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Canonicalize company names via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to DB")
    parser.add_argument("--batch", type=int, default=200, help="Names per LLM call (default 200)")
    parser.add_argument("--skip-second-pass", action="store_true", help="Skip cross-batch duplicate merge")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        sys.exit("OPENROUTER_API_KEY is not set")

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        sys.exit("DATABASE_URL is not set")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    # Ensure schema exists
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_aliases (
            raw_name TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS company_aliases_canonical_idx ON company_aliases(canonical_name)")
    cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS company_canonical TEXT")

    # Only process raw names not already in company_aliases
    cur.execute(
        """
        SELECT DISTINCT company_name FROM jobs
        WHERE company_name IS NOT NULL AND company_name != ''
          AND company_name NOT IN (SELECT raw_name FROM company_aliases)
        ORDER BY company_name
        """
    )
    raw_names = [r[0] for r in cur.fetchall()]
    print(f"Raw company names to process: {len(raw_names)}")

    with httpx.Client() as http:
        if not raw_names:
            print("Nothing new to canonicalize in Pass 1.")
        else:
            pass1_canonicalize(cur, http, api_key, raw_names, args.batch, args.dry_run)

        if not args.skip_second_pass:
            pass2_dedup(cur, http, api_key, args.dry_run)

    apply_to_jobs(cur, args.dry_run)

    cur.close()
    conn.close()
    print("\nDone.")
    if args.dry_run:
        print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
