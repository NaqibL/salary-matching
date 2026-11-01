"""Evaluate lowball matching quality against a curated gold standard.

Mirrors the production code path in /api/lowball/check:
  - same embedder (EmbedderConfig default = fine-tuned model)
  - same extract_high_signal_description pre-processing
  - same get_all_embedded_job_ids_ranked query (top 500)

For each test case the script checks pairwise ordering:
  does the highest-ranking title containing `pos` appear above the
  highest-ranking title containing `neg`?

Usage:
    uv run python scripts/finetune/eval_lowball.py
    uv run python scripts/finetune/eval_lowball.py --limit 20
    uv run python scripts/finetune/eval_lowball.py --gold scripts/finetune/eval/gold_standard.json
    uv run python scripts/finetune/eval_lowball.py --baseline BAAI/bge-base-en-v1.5

Exit code: 0 always — results are printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Evaluate lowball match quality")
parser.add_argument(
    "--gold",
    default=str(Path(__file__).parent / "eval" / "gold_standard.json"),
    help="Path to gold standard JSON file",
)
parser.add_argument(
    "--limit",
    type=int,
    default=None,
    help="Evaluate only the first N test cases",
)
parser.add_argument(
    "--pool",
    type=int,
    default=500,
    help="Number of ranked jobs to retrieve per query (default: 500)",
)
parser.add_argument(
    "--baseline",
    default=None,
    help="Optional second model name to run as a baseline for comparison",
)
parser.add_argument(
    "--db-url",
    default=None,
    help="PostgreSQL connection URL (falls back to DATABASE_URL env var)",
)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Imports (after arg parse so --help is fast)
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    pass

db_url = args.db_url or os.environ.get("DATABASE_URL")
if not db_url:
    sys.exit("DATABASE_URL is required — set it in .env or pass --db-url")

from mcf.lib.storage.postgres_store import PostgresStore
from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rank_of(fragment: str, ranked_titles: list[str]) -> int | None:
    """Return the 0-based rank of the first title containing `fragment` (case-insensitive).
    Returns None if not found."""
    frag = fragment.lower()
    for i, title in enumerate(ranked_titles):
        if frag in title.lower():
            return i
    return None


def _eval_case(
    case: dict,
    embedder: Embedder,
    store: PostgresStore,
    pool: int,
) -> dict:
    """Run one test case. Returns a result dict."""
    title = case["title"]
    description = case["description"]

    desc_text, _ = extract_high_signal_description(description, title)
    job_text = f"Job Title: {title}\nDescription: {desc_text}"
    vector = embedder.embed_text(job_text)

    ranked = store.get_all_embedded_job_ids_ranked(vector, limit=pool)

    # Fetch titles in rank order
    uuids_in_order = [uuid for uuid, _, _ in ranked]
    if not uuids_in_order:
        return {
            "id": case["id"],
            "category": case["category"],
            "title": title,
            "pairs_total": len(case["pairs"]),
            "pairs_pass": 0,
            "results": [],
            "error": "no ranked jobs returned",
        }

    jobs_by_uuid = {
        j["job_uuid"]: j.get("title") or ""
        for j in store.get_jobs_with_salary_by_uuids(uuids_in_order)
    }
    ranked_titles = [jobs_by_uuid.get(uuid, "") for uuid in uuids_in_order]

    pair_results = []
    for pair in case["pairs"]:
        pos_frag = pair["pos"]
        neg_frag = pair["neg"]
        pos_rank = _rank_of(pos_frag, ranked_titles)
        neg_rank = _rank_of(neg_frag, ranked_titles)

        # Pass when: pos found and appears above neg (or neg not found at all)
        if pos_rank is None:
            passed = False
            reason = f"pos '{pos_frag}' not found in top-{pool}"
        elif neg_rank is None:
            passed = True
            reason = f"neg '{neg_frag}' not in top-{pool} (pos rank {pos_rank})"
        elif pos_rank < neg_rank:
            passed = True
            reason = f"pos rank {pos_rank} < neg rank {neg_rank}"
        else:
            passed = False
            reason = f"pos rank {pos_rank} >= neg rank {neg_rank}"

        pair_results.append({
            "pos": pos_frag,
            "neg": neg_frag,
            "pos_rank": pos_rank,
            "neg_rank": neg_rank,
            "pass": passed,
            "reason": reason,
        })

    return {
        "id": case["id"],
        "category": case["category"],
        "title": title,
        "pairs_total": len(pair_results),
        "pairs_pass": sum(1 for r in pair_results if r["pass"]),
        "results": pair_results,
    }


def _run_eval(
    cases: list[dict],
    embedder: Embedder,
    store: PostgresStore,
    pool: int,
    label: str,
) -> tuple[list[dict], dict]:
    """Run evaluation and print results. Returns (per-case results, summary dict)."""
    all_results = []
    total_pairs = 0
    total_pass = 0
    by_category: dict[str, list] = defaultdict(lambda: [0, 0])

    print(f"\n{'='*60}")
    print(f"Model: {label}")
    print(f"Pool:  top-{pool} per query")
    print(f"Cases: {len(cases)}")
    print(f"{'='*60}\n")

    for i, case in enumerate(cases):
        result = _eval_case(case, embedder, store, pool)
        all_results.append(result)

        p = result["pairs_pass"]
        t = result["pairs_total"]
        total_pairs += t
        total_pass += p
        by_category[result["category"]][0] += p
        by_category[result["category"]][1] += t

        status = "PASS" if p == t else ("WARN" if p > 0 else "FAIL")
        print(f"[{i+1:3}/{len(cases)}] {status} {p}/{t}  {result['title']}")

        for r in result["results"]:
            if not r["pass"]:
                print(f"          FAIL  pos='{r['pos']}' (rank {r['pos_rank']})  "
                      f"neg='{r['neg']}' (rank {r['neg_rank']})")

    pct = total_pass / total_pairs * 100 if total_pairs else 0
    print(f"\n{'='*60}")
    print(f"OVERALL: {total_pass}/{total_pairs} pairs correct ({pct:.1f}%)")
    print(f"{'='*60}")
    print(f"\nBy category:")

    category_summary = {}
    for cat in sorted(by_category):
        p, t = by_category[cat]
        cat_pct = p / t * 100 if t else 0
        bar = "#" * round(cat_pct / 5)
        print(f"  {cat:<30} {p:3}/{t:3} ({cat_pct:5.1f}%)  {bar}")
        category_summary[cat] = {"pass": p, "total": t, "pct": round(cat_pct, 1)}

    summary = {
        "model": label,
        "pool": pool,
        "cases": len(cases),
        "pairs_pass": total_pass,
        "pairs_total": total_pairs,
        "pct": round(pct, 1),
        "by_category": category_summary,
    }
    return all_results, summary


def _save_results(path: Path, runs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(runs, indent=2), encoding="utf-8")
    print(f"\nResults saved to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

gold_path = Path(args.gold)
if not gold_path.exists():
    sys.exit(f"Gold standard file not found: {gold_path}")

cases: list[dict] = json.loads(gold_path.read_text(encoding="utf-8"))
if args.limit:
    cases = cases[: args.limit]

print(f"Loaded {len(cases)} test cases from {gold_path}")
print("Connecting to database...")
store = PostgresStore(db_url)

print(f"Loading model: {EmbedderConfig().model_name} (default fine-tuned)...")
embedder = Embedder()

case_results, summary = _run_eval(cases, embedder, store, args.pool, label=embedder.model_name)

runs = [{"summary": summary, "cases": case_results}]

if args.baseline:
    print(f"\nLoading baseline model: {args.baseline}...")
    baseline_config = EmbedderConfig(model_name=args.baseline, use_query_prefix=True)
    baseline_embedder = Embedder(config=baseline_config)
    b_results, b_summary = _run_eval(cases, baseline_embedder, store, args.pool, label=args.baseline)
    runs.append({"summary": b_summary, "cases": b_results})

store.close()

out_path = Path(args.gold).parent / "results_latest.json"
_save_results(out_path, runs)
print("Done.")
