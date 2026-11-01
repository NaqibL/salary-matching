# BGE fine-tuning pipeline

Scripts used to build `NaqibL/bge-base-sgmarket-v2`. Run from the repo root.

| Step | Script | Output |
|---|---|---|
| 1. Sample jobs | `sample_jobs.py` | `data/finetune/jobs_sample.jsonl` |
| 2. LLM labels (Gemini via OpenRouter) | `label_jobs.py` | `data/finetune/labels.jsonl` |
| 3. Mine hard negatives | `mine_hard_negatives.py` | `eval/hard_negatives.json` (gitignored, ~20 MB) |
| 4. Build triplets | `build_triplets_v2.py` (`build_triplets.py` = v1) | `data/finetune/triplets_v2_*.jsonl` |
| 5. Train on Kaggle (T4) | `finetune_bge.py` | HF model repo |
| 6. Re-embed on Kaggle | `export_job_texts.py` → `reembed_kaggle.py` | `data/job_embeddings_v2.parquet` |
| 7. Import embeddings | `import_embeddings.py` | updates `job_embeddings` |
| 8. Evaluate | `eval_lowball.py`, `casestudy_debug.py` | `eval/results_*.json` |

`eval/gold_standard.json` is the hand-labelled eval set. See `.claude/fine-tuning-plan.md` for the v2 design notes.
