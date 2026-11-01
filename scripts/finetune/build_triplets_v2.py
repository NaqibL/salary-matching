"""Build cross-function hard negative triplets (v2 dataset).

Uses mined confusion pairs from hard_negatives.json plus LLM-derived subfamily
labels from labels.jsonl to construct triplets where the hard negative is a
cross-function role the model currently confuses with the anchor.

v1 hard negatives were same-function/different-seniority only.
v2 adds cross-function pairs (e.g. bi_analyst vs data_engineer) to fix the
primary failure mode from the case study eval.

Inputs:
    scripts/finetune/eval/hard_negatives.json  -- mined confusion pairs
    data/finetune/labels.jsonl        -- LLM labels incl. subfamily field
    DATABASE_URL env var              -- job text fetch

Outputs:
    data/finetune/triplets_v2_train.jsonl
    data/finetune/triplets_v2_eval.jsonl

Usage:
    uv run python scripts/finetune/build_triplets_v2.py
    uv run python scripts/finetune/build_triplets_v2.py --hard-negatives scripts/finetune/eval/hard_negatives.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--hard-negatives", default="scripts/finetune/eval/hard_negatives.json")
parser.add_argument("--labels", default="data/finetune/labels.jsonl")
parser.add_argument("--train-out", default="data/finetune/triplets_v2_train.jsonl")
parser.add_argument("--eval-out", default="data/finetune/triplets_v2_eval.jsonl")
parser.add_argument("--max-per-pair", type=int, default=200, help="Max triplets per (anchor_family, confused_family) pair")
parser.add_argument("--pool-size", type=int, default=500, help="Max jobs to sample per non-D&A family from DB")
parser.add_argument("--eval-frac", type=float, default=0.1)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--db-url", default=None)
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

# ---------------------------------------------------------------------------
# Family definitions (mirrors mine_hard_negatives.py — keep in sync)
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
FAMILIES_DICT = dict(FAMILIES)

# D&A subfamilies — for these we use labels.jsonl subfamily pools
DATA_SUBFAMILIES = {
    "bi_analyst", "data_analyst", "data_engineer", "data_scientist",
    "ml_engineer", "business_analyst", "data_architect",
}

# Non-D&A cross-family pairs to include (frozensets)
NON_DATA_INCLUDE_PAIRS: set[frozenset] = {
    frozenset({"ux_designer", "interior_designer"}),
    frozenset({"product_manager", "interior_designer"}),
    frozenset({"marketing", "sales"}),
    frozenset({"ux_designer", "product_manager"}),
}

# Pairs to skip even if mined
SKIP_PAIRS: set[frozenset] = {
    frozenset({"operations", "project_manager"}),  # borderline overlap
}


def should_include(fam_a: str, fam_b: str) -> bool:
    if fam_a == fam_b:
        return False
    pair = frozenset({fam_a, fam_b})
    if pair in SKIP_PAIRS:
        return False
    if fam_a in DATA_SUBFAMILIES and fam_b in DATA_SUBFAMILIES:
        return True
    return pair in NON_DATA_INCLUDE_PAIRS


# ---------------------------------------------------------------------------
# Load labels (last-entry-wins to handle subfamily backfill duplicates)
# ---------------------------------------------------------------------------
print("Loading labels...")
labels: dict[str, dict] = {}
with Path(args.labels).open(encoding="utf-8") as f:
    for line in f:
        try:
            row = json.loads(line)
            if row.get("job_uuid"):
                labels[row["job_uuid"]] = row
        except Exception:
            pass
print(f"  {len(labels):,} labeled jobs")

# Build D&A subfamily pools: {subfamily: [uuid, ...]}
da_pools: dict[str, list[str]] = defaultdict(list)
for uuid, lbl in labels.items():
    sf = lbl.get("subfamily")
    if sf and sf in DATA_SUBFAMILIES:
        da_pools[sf].append(uuid)
print(f"  D&A subfamily pool sizes: { {k: len(v) for k, v in sorted(da_pools.items())} }")

# ---------------------------------------------------------------------------
# Load hard negatives
# ---------------------------------------------------------------------------
print("Loading hard negatives...")
with Path(args.hard_negatives).open(encoding="utf-8") as f:
    hard_negatives: list[dict] = json.load(f)
print(f"  {len(hard_negatives):,} pairs")

# ---------------------------------------------------------------------------
# Identify which non-D&A families we need pools for
# ---------------------------------------------------------------------------
needed_nonda: set[str] = set()
for pair in hard_negatives:
    af = pair.get("anchor_family", "unknown")
    cf = pair.get("confused_with_family", "unknown")
    if af == "unknown" or cf == "unknown":
        continue
    if not should_include(af, cf):
        continue
    if af not in DATA_SUBFAMILIES:
        needed_nonda.add(af)
    if cf not in DATA_SUBFAMILIES:
        needed_nonda.add(cf)

# ---------------------------------------------------------------------------
# Build non-D&A pools from DB (title pattern queries)
# ---------------------------------------------------------------------------
store = PostgresStore(db_url)

nonda_pools: dict[str, list[str]] = {}

def fetch_family_uuids(family: str, n: int) -> list[str]:
    patterns = FAMILIES_DICT.get(family, [])
    uuids: list[str] = []
    seen: set[str] = set()
    conn = store._get_conn()  # type: ignore[attr-defined]
    try:
        for pattern in patterns:
            if len(uuids) >= n:
                break
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT j.job_uuid
                    FROM jobs j
                    JOIN job_embeddings je ON je.job_uuid = j.job_uuid
                    WHERE j.is_active = true AND LOWER(j.title) LIKE %s
                    ORDER BY j.last_seen_at DESC
                    LIMIT %s
                    """,
                    (f"%{pattern}%", n - len(uuids)),
                )
                for (uuid,) in cur.fetchall():
                    if uuid not in seen:
                        seen.add(uuid)
                        uuids.append(uuid)
    finally:
        store._pool.putconn(conn)  # type: ignore[attr-defined]
    return uuids


if needed_nonda:
    print(f"Fetching non-D&A family pools from DB: {sorted(needed_nonda)}")
    for fam in sorted(needed_nonda):
        pool = fetch_family_uuids(fam, args.pool_size)
        nonda_pools[fam] = pool
        print(f"  {fam:<25} {len(pool):,} jobs")


def get_pool(family: str) -> list[str]:
    if family in DATA_SUBFAMILIES:
        return da_pools.get(family, [])
    return nonda_pools.get(family, [])


# ---------------------------------------------------------------------------
# Batch-fetch job texts from DB
# ---------------------------------------------------------------------------
def fetch_job_texts(uuids: list[str], chunk: int = 500) -> dict[str, str]:
    texts: dict[str, str] = {}
    conn = store._get_conn()  # type: ignore[attr-defined]
    try:
        for i in range(0, len(uuids), chunk):
            batch = uuids[i:i + chunk]
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT job_uuid, title, description FROM jobs WHERE job_uuid = ANY(%s)",
                    (batch,),
                )
                for uuid, title, desc in cur.fetchall():
                    texts[uuid] = f"{title}\n\n{desc or ''}"
    finally:
        store._pool.putconn(conn)  # type: ignore[attr-defined]
    return texts


# ---------------------------------------------------------------------------
# Build raw triplet records (uuid triples before text fetch)
# ---------------------------------------------------------------------------
rng = random.Random(args.seed)

# Track per-pair counts to cap at max_per_pair
pair_counts: dict[tuple[str, str], int] = defaultdict(int)
uuid_triples: list[tuple[str, str, str, str, str]] = []  # (anchor_uuid, pos_uuid, neg_uuid, af, cf)

skipped_unknown = 0
skipped_no_include = 0
skipped_no_pool = 0
skipped_cap = 0

for pair in hard_negatives:
    af = pair.get("anchor_family", "unknown")
    cf = pair.get("confused_with_family", "unknown")
    anchor_uuid = pair["anchor_uuid"]
    confused_uuid = pair["confused_with_uuid"]

    if af == "unknown" or cf == "unknown":
        skipped_unknown += 1
        continue
    if not should_include(af, cf):
        skipped_no_include += 1
        continue

    pair_key = (af, cf)
    if pair_counts[pair_key] >= args.max_per_pair:
        skipped_cap += 1
        continue

    pool = get_pool(af)
    candidates = [u for u in pool if u != anchor_uuid and u != confused_uuid]
    if not candidates:
        skipped_no_pool += 1
        continue

    positive_uuid = rng.choice(candidates)
    uuid_triples.append((anchor_uuid, positive_uuid, confused_uuid, af, cf))
    pair_counts[pair_key] += 1

print(f"\nPairs kept: {len(uuid_triples):,}")
print(f"Skipped (unknown family): {skipped_unknown:,}")
print(f"Skipped (not in include list): {skipped_no_include:,}")
print(f"Skipped (empty pool): {skipped_no_pool:,}")
print(f"Skipped (cap reached): {skipped_cap:,}")

if not uuid_triples:
    store.close()
    sys.exit("No triplets produced — check hard_negatives.json and labels.jsonl")

# ---------------------------------------------------------------------------
# Fetch all job texts in one pass
# ---------------------------------------------------------------------------
all_uuids = list({u for triple in uuid_triples for u in triple[:3]})
print(f"\nFetching text for {len(all_uuids):,} unique jobs from DB...")
job_texts = fetch_job_texts(all_uuids)
print(f"  Retrieved {len(job_texts):,} texts")

store.close()

# ---------------------------------------------------------------------------
# Build final triplets (skip any with missing text)
# ---------------------------------------------------------------------------
triplets: list[dict] = []
missing_text = 0
for anchor_uuid, pos_uuid, neg_uuid, af, cf in uuid_triples:
    a_text = job_texts.get(anchor_uuid)
    p_text = job_texts.get(pos_uuid)
    n_text = job_texts.get(neg_uuid)
    if not (a_text and p_text and n_text):
        missing_text += 1
        continue
    triplets.append({
        "anchor": a_text,
        "positive": p_text,
        "hard_negative": n_text,
    })
if missing_text:
    print(f"  Dropped {missing_text} triplets with missing text")

# ---------------------------------------------------------------------------
# Split and write
# ---------------------------------------------------------------------------
rng.shuffle(triplets)
n_eval = max(1, int(len(triplets) * args.eval_frac))
eval_triplets = triplets[:n_eval]
train_triplets = triplets[n_eval:]

out_train = Path(args.train_out)
out_eval = Path(args.eval_out)
out_train.parent.mkdir(parents=True, exist_ok=True)

with out_train.open("w", encoding="utf-8") as f:
    for row in train_triplets:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

with out_eval.open("w", encoding="utf-8") as f:
    for row in eval_triplets:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\nTraining triplets : {len(train_triplets):,} -> {out_train}")
print(f"Eval triplets     : {len(eval_triplets):,} -> {out_eval}")
print("\nTriplets by (anchor_family, confused_family):")
for (af, cf), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
    if count > 0:
        print(f"  {af:<25} vs {cf:<25}  {count:,}")
