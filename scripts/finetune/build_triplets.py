"""Step 3 of the fine-tuning pipeline: build training triplets.

Reads:
    data/finetune/jobs_sample.jsonl  — {job_uuid, title, description}
    data/finetune/labels.jsonl       — {job_uuid, seniority, function}

Writes:
    data/finetune/triplets_train.jsonl  — {anchor, positive, hard_negative}
    data/finetune/triplets_eval.jsonl   — same format (10% holdout per bucket)

Triplet construction:
    positive      = same (function, seniority) bucket, different job
    hard_negative = same function, adjacent seniority (±1 step, fallback ±2)

Batches are clustered by function (sorted) so shuffle=False in the trainer
gives the model dense same-function contrasts every step.

Usage:
    uv run python scripts/finetune/build_triplets.py [--max-per-bucket 500] [--min-bucket-size 5]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

_SENIORITY_ORDER = ["Intern", "Entry", "Mid", "Senior", "Lead", "Manager"]
_SENIORITY_RANK = {s: i for i, s in enumerate(_SENIORITY_ORDER)}

# Ambiguous jobs can still appear as positives/negatives but not as anchors
# (we can't reliably define their adjacent seniority)


def adjacent_seniorities(seniority: str, max_distance: int = 2) -> list[str]:
    """Return seniority labels within max_distance steps, closest first."""
    if seniority not in _SENIORITY_RANK:
        return []
    idx = _SENIORITY_RANK[seniority]
    result = []
    for dist in range(1, max_distance + 1):
        if idx - dist >= 0:
            result.append(_SENIORITY_ORDER[idx - dist])
        if idx + dist < len(_SENIORITY_ORDER):
            result.append(_SENIORITY_ORDER[idx + dist])
    return result


def format_text(title: str, description: str) -> str:
    return f"{title}\n\n{description}"


def load_jobs(path: Path) -> dict[str, dict]:
    """Returns {job_uuid: {title, description}}."""
    jobs = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if row.get("job_uuid") and row.get("title") and row.get("description"):
                    jobs[row["job_uuid"]] = {"title": row["title"], "description": row["description"]}
            except Exception:
                pass
    return jobs


def load_labels(path: Path) -> dict[str, dict]:
    """Returns {job_uuid: {seniority, function}}."""
    labels = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                if row.get("job_uuid") and row.get("seniority") and row.get("function"):
                    labels[row["job_uuid"]] = {"seniority": row["seniority"], "function": row["function"]}
            except Exception:
                pass
    return labels


def build_triplets(
    bucket: list[str],  # job_uuids in this (function, seniority) bucket
    hard_neg_pool: list[str],  # job_uuids eligible as hard negatives
    job_texts: dict[str, str],  # job_uuid -> formatted text
    max_pairs: int,
    rng: random.Random,
) -> list[dict]:
    if len(bucket) < 2 or not hard_neg_pool:
        return []

    anchors = bucket[:]
    rng.shuffle(anchors)
    anchors = anchors[:max_pairs]

    triplets = []
    for anchor_uuid in anchors:
        # positive: any other job in same bucket
        pos_candidates = [u for u in bucket if u != anchor_uuid]
        if not pos_candidates:
            continue
        positive_uuid = rng.choice(pos_candidates)

        # hard negative: closest adjacent seniority, same function
        neg_candidates = [u for u in hard_neg_pool if u != anchor_uuid]
        if not neg_candidates:
            continue
        hard_neg_uuid = rng.choice(neg_candidates)

        triplets.append({
            "anchor": job_texts[anchor_uuid],
            "positive": job_texts[positive_uuid],
            "hard_negative": job_texts[hard_neg_uuid],
        })

    return triplets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", default="data/finetune/jobs_sample.jsonl")
    parser.add_argument("--labels", default="data/finetune/labels.jsonl")
    parser.add_argument("--train-out", default="data/finetune/triplets_train.jsonl")
    parser.add_argument("--eval-out", default="data/finetune/triplets_eval.jsonl")
    parser.add_argument("--max-per-bucket", type=int, default=500)
    parser.add_argument("--min-bucket-size", type=int, default=5)
    parser.add_argument("--eval-frac", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print("Loading jobs and labels...")
    jobs = load_jobs(Path(args.jobs))
    labels = load_labels(Path(args.labels))

    # Join: only keep jobs that have both text and a label
    merged = {}
    for uuid, label in labels.items():
        if uuid in jobs:
            merged[uuid] = {**jobs[uuid], **label}

    print(f"Merged: {len(merged):,} jobs with text + label")

    # Pre-format job texts
    job_texts = {
        uuid: format_text(d["title"], d["description"])
        for uuid, d in merged.items()
    }

    # Group by (function, seniority)
    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for uuid, d in merged.items():
        buckets[(d["function"], d["seniority"])].append(uuid)

    print(f"Buckets: {len(buckets)} (function, seniority) combinations")
    for (fn, sn), uuids in sorted(buckets.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {fn} / {sn}: {len(uuids):,}")
    print("  ...")

    # Split each bucket into train/eval
    train_buckets: dict[tuple[str, str], list[str]] = {}
    eval_buckets: dict[tuple[str, str], list[str]] = {}
    for key, uuids in buckets.items():
        shuffled = uuids[:]
        rng.shuffle(shuffled)
        n_eval = max(1, int(len(shuffled) * args.eval_frac))
        eval_buckets[key] = shuffled[:n_eval]
        train_buckets[key] = shuffled[n_eval:]

    # Group train jobs by function for hard negative lookups
    # hard_neg_pool[(function, seniority)] = list of uuids with that (fn, sn) from train set
    train_by_fn_sn: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (fn, sn), uuids in train_buckets.items():
        train_by_fn_sn[(fn, sn)].extend(uuids)

    # Build training triplets
    all_train_triplets: list[tuple[str, list[dict]]] = []  # (function, triplets)

    skipped_no_hardneg = 0
    skipped_too_small = 0

    for (fn, sn), bucket in train_buckets.items():
        if len(bucket) < args.min_bucket_size:
            skipped_too_small += 1
            continue

        # Find hard negative pool: same function, adjacent seniority, closest first
        hard_neg_pool: list[str] = []
        for adj_sn in adjacent_seniorities(sn):
            candidates = train_by_fn_sn.get((fn, adj_sn), [])
            hard_neg_pool.extend(candidates)
            if hard_neg_pool:
                break  # use closest distance that has candidates

        if not hard_neg_pool:
            skipped_no_hardneg += 1
            continue

        triplets = build_triplets(bucket, hard_neg_pool, job_texts, args.max_per_bucket, rng)
        if triplets:
            all_train_triplets.append((fn, triplets))

    # Sort by function to cluster batches — same function stays together
    all_train_triplets.sort(key=lambda x: x[0])
    flat_train = [t for _, triplets in all_train_triplets for t in triplets]

    # Build eval triplets (same logic, from held-out jobs)
    eval_by_fn_sn: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (fn, sn), uuids in eval_buckets.items():
        eval_by_fn_sn[(fn, sn)].extend(uuids)

    flat_eval = []
    for (fn, sn), bucket in eval_buckets.items():
        if len(bucket) < 2:
            continue
        hard_neg_pool = []
        for adj_sn in adjacent_seniorities(sn):
            candidates = eval_by_fn_sn.get((fn, adj_sn), [])
            hard_neg_pool.extend(candidates)
            if hard_neg_pool:
                break
        if not hard_neg_pool:
            continue
        triplets = build_triplets(bucket, hard_neg_pool, job_texts, max_pairs=50, rng=rng)
        flat_eval.extend(triplets)

    # Write outputs
    out_train = Path(args.train_out)
    out_eval = Path(args.eval_out)
    out_train.parent.mkdir(parents=True, exist_ok=True)

    with out_train.open("w", encoding="utf-8") as f:
        for row in flat_train:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with out_eval.open("w", encoding="utf-8") as f:
        for row in flat_eval:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nTraining triplets : {len(flat_train):,} → {out_train}")
    print(f"Eval triplets     : {len(flat_eval):,} → {out_eval}")
    print(f"Skipped (too small bucket): {skipped_too_small}")
    print(f"Skipped (no adjacent seniority in sample): {skipped_no_hardneg}")


if __name__ == "__main__":
    main()
