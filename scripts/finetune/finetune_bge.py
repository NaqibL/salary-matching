"""Step 4 of the fine-tuning pipeline: fine-tune BGE on Kaggle T4.

Run this notebook on Kaggle with a T4 GPU.
Upload data/finetune/triplets_v2_merged_train.jsonl and triplets_v2_merged_eval.jsonl
as a Kaggle dataset (sgmarket-finetune-v2) first.

Paths auto-detect Kaggle vs local:
  Kaggle:  /kaggle/input/<DATASET_SLUG>/triplets_v2_merged_train.jsonl
  Local:   data/finetune/triplets_v2_merged_train.jsonl

Output is saved to:
  Kaggle:  /kaggle/working/bge-base-sgmarket-v2
  Local:   models/bge-base-sgmarket-v2

Per-epoch HF pushes: set HF_TOKEN + HF_REPO env vars. After each epoch the model is
pushed as {HF_REPO}-epoch-{N} so a killed Kaggle session never loses more than one epoch.

Usage (local):
    pip install sentence-transformers
    python scripts/finetune/finetune_bge.py [--dataset-slug sgmarket-finetune-v2] [--epochs 3] [--batch-size 32]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

ON_KAGGLE = Path("/kaggle/input").exists()


def resolve_paths(dataset_slug: str, model_name_out: str) -> tuple[Path, Path, Path]:
    if ON_KAGGLE:
        base = Path(f"/kaggle/input/{dataset_slug}")
        out = Path(f"/kaggle/working/{model_name_out}")
    else:
        base = Path("data/finetune")
        out = Path(f"models/{model_name_out}")
    return base / "triplets_v2_merged_train.jsonl", base / "triplets_v2_merged_eval.jsonl", out


# ── Data loading ───────────────────────────────────────────────────────────────

def load_triplets(path: Path) -> list[tuple[str, str, str]]:
    triplets = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
                triplets.append((row["anchor"], row["positive"], row["hard_negative"]))
            except Exception:
                pass
    return triplets


# ── Training ───────────────────────────────────────────────────────────────────

def train(
    train_path: Path,
    eval_path: Path,
    output_path: Path,
    epochs: int,
    batch_size: int,
    base_model: str = "BAAI/bge-base-en-v1.5",
    hf_repo_prefix: str = "",
) -> None:
    from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
    from torch.utils.data import DataLoader

    print(f"Loading triplets from {train_path} ...")
    train_triplets = load_triplets(train_path)
    eval_triplets = load_triplets(eval_path)
    print(f"  Train: {len(train_triplets):,}  Eval: {len(eval_triplets):,}")

    print(f"Loading base model: {base_model}")
    model = SentenceTransformer(base_model)

    # Build InputExamples — shuffle=False to preserve function-clustered order
    train_examples = [
        InputExample(texts=[a, p, n]) for a, p, n in train_triplets
    ]
    train_dataloader = DataLoader(train_examples, shuffle=False, batch_size=batch_size)

    loss = losses.CachedMultipleNegativesRankingLoss(model)

    # Evaluator: triplet accuracy on held-out set (anchor closer to positive than hard_negative)
    eval_anchors   = [a for a, _, _ in eval_triplets]
    eval_positives = [p for _, p, _ in eval_triplets]
    eval_negatives = [n for _, _, n in eval_triplets]
    evaluator = evaluation.TripletEvaluator(
        anchors=eval_anchors,
        positives=eval_positives,
        negatives=eval_negatives,
        name="eval",
    )

    warmup_steps = max(100, len(train_dataloader) // 10)
    total_steps = len(train_dataloader) * epochs
    print(f"\nStarting training: {epochs} epochs, batch_size={batch_size}, warmup={warmup_steps}")
    print(f"Steps per epoch: {len(train_dataloader)}  |  Total steps: {total_steps}")

    import time
    _start = time.monotonic()
    _last_log = [0]  # mutable for closure

    hf_token = os.environ.get("HF_TOKEN", "").strip()

    def log_callback(score: float, epoch: int, steps: int) -> None:
        elapsed = time.monotonic() - _start
        steps_done = (epoch + 1) * len(train_dataloader)
        eta = (elapsed / steps_done) * (total_steps - steps_done) if steps_done else 0
        print(
            f"Epoch {epoch + 1}/{epochs} complete | "
            f"triplet_accuracy={score:.4f} | "
            f"{elapsed/60:.1f} min elapsed | "
            f"ETA {eta/60:.1f} min",
            flush=True,
        )
        if hf_token and hf_repo_prefix:
            epoch_repo = f"{hf_repo_prefix}-epoch-{int(epoch + 1)}"
            print(f"Pushing epoch checkpoint to HF Hub: {epoch_repo} ...", flush=True)
            model.push_to_hub(epoch_repo, token=hf_token, private=True, exist_ok=True)
            print("Checkpoint pushed.", flush=True)

    output_path.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_objectives=[(train_dataloader, loss)],
        evaluator=evaluator,
        epochs=epochs,
        warmup_steps=warmup_steps,
        output_path=str(output_path),
        checkpoint_path=str(output_path / "checkpoints"),
        checkpoint_save_steps=500,
        show_progress_bar=True,
        callback=log_callback,
    )

    print(f"\nModel saved to {output_path}")

    # Final eval score
    score = evaluator(model)
    if isinstance(score, dict):
        print(f"Final eval: {score}")
        score = next(iter(score.values()))
    else:
        print(f"Final triplet accuracy: {score:.4f}")

    # Push final model to HF Hub
    final_repo = os.environ.get("HF_REPO", "").strip() or hf_repo_prefix
    if hf_token and final_repo:
        print(f"\nPushing final model to Hugging Face Hub: {final_repo} ...")
        model.push_to_hub(final_repo, token=hf_token, private=True)
        print("Done.")
    else:
        print("\nSkipping final HF Hub push (set HF_TOKEN and HF_REPO env vars to enable).")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-slug", default="sgmarket-finetune-v2", help="Kaggle dataset slug (ignored locally)")
    parser.add_argument("--model-name", default="BAAI/bge-base-en-v1.5", help="Base model to fine-tune from")
    parser.add_argument("--model-out", default="bge-base-sgmarket-v2", help="Output directory / model name")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--hf-repo", default="", help="Final HF repo id, e.g. NaqibL/bge-base-sgmarket-v2")
    parser.add_argument("--hf-repo-prefix", default="", help="Per-epoch HF push prefix, e.g. NaqibL/bge-base-sgmarket-v2 -> pushes NaqibL/bge-base-sgmarket-v2-epoch-1 etc.")
    args = parser.parse_args()

    if args.hf_repo:
        os.environ["HF_REPO"] = args.hf_repo

    train_path, eval_path, output_path = resolve_paths(args.dataset_slug, args.model_out)

    if not train_path.exists():
        raise SystemExit(f"Train file not found: {train_path}")
    if not eval_path.exists():
        raise SystemExit(f"Eval file not found: {eval_path}")

    train(
        train_path, eval_path, output_path,
        args.epochs, args.batch_size,
        base_model=args.model_name,
        hf_repo_prefix=args.hf_repo_prefix or args.hf_repo,
    )


if __name__ == "__main__":
    import sys
    if not any("jupyter" in a or "kernel" in a for a in sys.argv):
        main()
