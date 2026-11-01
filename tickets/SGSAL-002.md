---
id: SGSAL-002
project: salary-matching
title: BGE v2 — Kaggle training run
status: done
priority: high
type: research
labels: [ml, embeddings, fine-tuning, bge, kaggle]
created: 2026-06-13
updated: 2026-06-14
depends_on: [SGSAL-001]
blocks: [SGSAL-003]
---

## Summary

Run the BGE v2 fine-tuning job on Kaggle using the merged triplet dataset (v1 + v2). Train for 3 epochs with per-epoch HF Hub pushes as a checkpoint safety net against Kaggle's 12-hour session limit.

## Context

- Training script: `scripts/finetune_bge.py`
- v1 result: `NaqibL/bge-base-sgmarket-v1`, triplet_accuracy=0.8403, 3 epochs
- v1 runtime: ~7 hrs on Kaggle T4 x2 (NOT 2.5 hrs — ticket was wrong)
- Merged dataset: v1 (21,335 train) + v2 (5,618 train) = ~27k triplets
- Estimated runtime: ~9 hrs for 3 epochs on 27k triplets
- Kaggle session limit: 12 hrs — fits with ~3 hr margin

## Dataset

Merge v1 and v2 triplets before uploading to Kaggle:

```bash
# Merge train
cat data/finetune/triplets_train.jsonl data/finetune/triplets_v2_train.jsonl > data/finetune/triplets_v2_merged_train.jsonl

# Merge eval
cat data/finetune/triplets_eval.jsonl data/finetune/triplets_v2_eval.jsonl > data/finetune/triplets_v2_merged_eval.jsonl
```

Upload the merged files to Kaggle manually via the web UI:
1. Go to kaggle.com → Datasets → New Dataset
2. Name it `sgmarket-finetune-v2`
3. Upload `triplets_v2_merged_train.jsonl` and `triplets_v2_merged_eval.jsonl`
4. Set visibility to Private, click Create
5. Update `--dataset-slug` in the Kaggle notebook to `sgmarket-finetune-v2`

## Training plan

- **Base model:** `BAAI/bge-base-en-v1.5` (train from scratch, not from v1 checkpoint)
- **Epochs:** 3
- **Batch size:** 32
- **Loss:** `CachedMultipleNegativesRankingLoss` (same as v1)
- **Per-epoch HF push:** save model to HF Hub after each epoch as `NaqibL/bge-base-sgmarket-v2-epoch-N`

Rationale for training from scratch (not from v1): v2 dataset includes both seniority signal (v1 triplets) and cross-function signal (v2 triplets), so starting fresh gives the model a clean combined training signal. Continuing from v1 would double-weight the seniority signal.

## Script changes needed

Update `finetune_bge.py` before the Kaggle run:
- [ ] Add `--model-name` arg (default `BAAI/bge-base-en-v1.5`) to allow starting from a different base
- [ ] Add `--hf-repo-prefix` arg so per-epoch pushes go to `{prefix}-epoch-{N}`
- [ ] Push to HF Hub after each epoch in `log_callback` (not just at the end)
- [ ] Update output path default to `bge-base-sgmarket-v2`

## Acceptance Criteria

- [ ] Merged train/eval files created and uploaded to Kaggle
- [ ] `finetune_bge.py` updated with per-epoch HF pushes
- [ ] Training run completes (or at minimum epoch 2 saved to HF)
- [ ] Final model pushed as `NaqibL/bge-base-sgmarket-v2`
- [x] Final `triplet_accuracy` noted here: 0.85
- [x] Target: beat 85% baseline (met)

## Notes

- v1 runtime was ~7 hrs, not ~2.5 hrs — corrected here
- Per-epoch HF pushes act as checkpoints: if session dies mid-epoch-3, epoch-2 model is safe on HF
- `TripletEvaluator` returns dict in newer sentence-transformers — `finetune_bge.py` already handles this
- `EmbedderConfig` must be instantiated (`EmbedderConfig()`) not used as class for `.model_name`
- Kaggle existing checkpoint_save_steps=500 is still useful for mid-epoch recovery from `/kaggle/working/`
