"""Hard negative mining for fine-tuning triplet construction.

For each role family, samples anchor jobs from the DB, runs similarity search,
and identifies high-scoring results from a DIFFERENT role family — these are
the pairs the model currently confuses and need targeted triplets.

Output: scripts/finetune/eval/hard_negatives.json
  [
    {
      "anchor_uuid": "...",
      "anchor_title": "...",
      "anchor_family": "bi_analyst",
      "confused_with_uuid": "...",
      "confused_with_title": "...",
      "confused_with_family": "data_engineer",
      "similarity": 0.94
    },
    ...
  ]

Usage:
    uv run python scripts/finetune/mine_hard_negatives.py
    uv run python scripts/finetune/mine_hard_negatives.py --samples 20 --threshold 0.88
    uv run python scripts/finetune/mine_hard_negatives.py --families bi_analyst data_engineer
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--samples", type=int, default=10, help="Anchor jobs to sample per family")
parser.add_argument("--topk", type=int, default=30, help="Top-K results to inspect per anchor")
parser.add_argument("--threshold", type=float, default=0.87, help="Min similarity to flag as confusing")
parser.add_argument("--families", nargs="*", default=None, help="Limit to specific families")
parser.add_argument("--db-url", default=None)
parser.add_argument("--output", default="scripts/finetune/eval/hard_negatives.json")
args = parser.parse_args()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

db_url = args.db_url or os.environ.get("DATABASE_URL")
if not db_url:
    sys.exit("DATABASE_URL required")

from mcf.lib.storage.postgres_store import PostgresStore
from mcf.lib.embeddings.embedder import Embedder

# ---------------------------------------------------------------------------
# Role family definitions
# Title fragment → family name. First match wins (order matters).
# ---------------------------------------------------------------------------
FAMILIES: list[tuple[str, list[str]]] = [
    ("bi_analyst",       ["business intelligence", "bi analyst", "data analytics analyst"]),
    ("data_scientist",   ["data scientist", "applied scientist", "research scientist"]),
    ("data_engineer",    ["data engineer", "analytics engineer", "etl engineer", "data pipeline"]),
    ("ml_engineer",      ["machine learning engineer", "ml engineer", "mlops", "ai engineer"]),
    ("data_analyst",     ["data analyst", "insights analyst", "reporting analyst"]),
    ("business_analyst", ["business analyst", "ba analyst", "functional analyst", "systems analyst"]),
    ("data_architect",   ["data architect", "solutions architect", "enterprise architect"]),
    ("software_engineer",["software engineer", "software developer", "backend engineer",
                          "frontend engineer", "fullstack engineer", "full stack"]),
    ("product_manager",  ["product manager", "product owner"]),
    ("ux_designer",      ["ux designer", "ui designer", "product designer", "ux researcher"]),
    ("interior_designer",["interior designer", "interior design"]),
    ("finance_analyst",  ["financial analyst", "finance analyst", "investment analyst",
                          "credit analyst", "risk analyst", "treasury analyst"]),
    ("compliance",       ["compliance officer", "compliance analyst", "compliance manager",
                          "aml analyst", "kyc analyst"]),
    ("hr",               ["hr business partner", "talent acquisition", "human resource",
                          "recruiter", "people operations"]),
    ("marketing",        ["marketing manager", "digital marketing", "brand manager",
                          "content marketing", "performance marketing"]),
    ("sales",            ["sales executive", "sales manager", "business development",
                          "account manager", "key account"]),
    ("operations",       ["operations manager", "operations executive", "supply chain",
                          "logistics", "procurement"]),
]


def classify_title(title: str) -> str | None:
    t = title.lower()
    for family, patterns in FAMILIES:
        for p in patterns:
            if p in t:
                return family
    return None


def sample_jobs_for_family(store: PostgresStore, family: str, patterns: list[str], n: int) -> list[dict]:
    """Pull up to n active+embedded jobs matching any of the family's title patterns."""
    conn = store._get_conn()  # type: ignore[attr-defined]
    results = []
    seen = set()
    try:
        for pattern in patterns:
            if len(results) >= n:
                break
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT j.job_uuid, j.title, j.description
                    FROM jobs j
                    JOIN job_embeddings je ON je.job_uuid = j.job_uuid
                    WHERE j.is_active = true
                      AND LOWER(j.title) LIKE %s
                    ORDER BY j.last_seen_at DESC
                    LIMIT %s
                """, (f"%{pattern}%", n - len(results)))
                for row in cur.fetchall():
                    if row[0] not in seen:
                        seen.add(row[0])
                        results.append({"job_uuid": row[0], "title": row[1], "description": row[2] or ""})
    finally:
        store._pool.putconn(conn)  # type: ignore[attr-defined]
    return results[:n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

store = PostgresStore(db_url)
embedder = Embedder()

target_families = args.families or [f for f, _ in FAMILIES]
families_dict = dict(FAMILIES)

all_confusions: list[dict] = []
family_stats: dict[str, dict] = defaultdict(lambda: {"anchors": 0, "confusions": 0})

print(f"Mining hard negatives (threshold={args.threshold}, samples={args.samples}/family)\n")

for family_name in target_families:
    if family_name not in families_dict:
        print(f"  Unknown family: {family_name}, skipping")
        continue

    patterns = families_dict[family_name]
    anchors = sample_jobs_for_family(store, family_name, patterns, args.samples)
    if not anchors:
        print(f"  {family_name:<25} no jobs found, skipping")
        continue

    family_stats[family_name]["anchors"] = len(anchors)
    confusions_this_family = 0

    for anchor in anchors:
        from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description
        desc_text, _ = extract_high_signal_description(anchor["description"], anchor["title"])
        job_text = f"Job Title: {anchor['title']}\nDescription: {desc_text}"
        vector = embedder.embed_text(job_text)

        ranked = store.get_all_embedded_job_ids_ranked(vector, limit=args.topk)
        if not ranked:
            continue

        uuids = [uuid for uuid, _, _ in ranked]
        scores = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in ranked}
        jobs = store.get_jobs_with_salary_by_uuids(uuids)
        jobs_by_uuid = {j["job_uuid"]: j for j in jobs}

        for uuid, dist, _ in ranked:
            sim = scores[uuid]
            if sim < args.threshold:
                break  # ranked in order, no point continuing
            if uuid == anchor["job_uuid"]:
                continue
            result_job = jobs_by_uuid.get(uuid)
            if not result_job:
                continue
            result_title = result_job.get("title") or ""
            result_family = classify_title(result_title)

            if result_family != family_name:
                all_confusions.append({
                    "anchor_uuid": anchor["job_uuid"],
                    "anchor_title": anchor["title"],
                    "anchor_family": family_name,
                    "confused_with_uuid": uuid,
                    "confused_with_title": result_title,
                    "confused_with_family": result_family or "unknown",
                    "similarity": sim,
                })
                confusions_this_family += 1

    family_stats[family_name]["confusions"] = confusions_this_family
    print(f"  {family_name:<25} {len(anchors):2} anchors  ->  {confusions_this_family:3} confusions")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\nTotal confusing pairs found: {len(all_confusions)}")

# Count confusion pairs by (anchor_family, confused_family)
pair_counts: dict[tuple, int] = defaultdict(int)
for c in all_confusions:
    pair_counts[(c["anchor_family"], c["confused_with_family"])] += 1

print("\nTop confusion pairs (anchor -> confused_with):  count")
for (a, b), count in sorted(pair_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {a:<25} -> {b:<25}  {count}")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

out_path = Path(args.output)
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(all_confusions, indent=2), encoding="utf-8")
print(f"\nSaved {len(all_confusions)} confusing pairs to {out_path}")

store.close()
