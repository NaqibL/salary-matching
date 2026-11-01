---
id: SGSAL-001
project: salary-matching
title: BGE v2 — build v2 training dataset (re-mine + full LLM label + triplets)
status: done
priority: high
type: research
labels: [ml, embeddings, fine-tuning, bge]
created: 2026-06-13
updated: 2026-06-13
blocks: [SGSAL-002]
---

## Summary

Prepare the v2 training dataset for BGE fine-tuning. v1 only used same-function/different-seniority hard negatives, so the model never learned to separate cross-function roles (BI Analyst vs Data Engineer is the primary failure). v2 adds cross-function hard negatives by: (1) extending the role taxonomy, (2) LLM-labeling all 258k DB jobs, and (3) building augmented triplets.

## Context

- v1 triplets: `data/finetune/` (21,335 train / 2,166 eval)
- Current hard negatives: `scripts/eval/hard_negatives.json` (9,458 pairs, but 69% are "unknown" family)
- DB size: 258k jobs with title+description; 170k with embeddings; 65k active+embedded
- Key attractor: `data_engineer` confuses `bi_analyst`, `data_analyst`, `data_scientist`, `ml_engineer`
- Analysis of "unknown" pairs revealed most are same-family variants (harmless), not real confusions

## What "unknown" actually means

69% of mined pairs have `confused_with_family = "unknown"` because `classify_title()` misses title variants.
Analysis showed two distinct categories:

**Same-family variants — skip as hard negatives (model is correct to keep these close):**
- `finance_analyst` confused with Accountant, Finance Executive, Accounts Executive
- `hr` confused with HR Manager, HR Executive, HRBP
- `marketing` confused with Marketing Officer, Marcom Executive, Marketing Director
- `sales` confused with Sales Coordinator, Sales Representative
- `software_engineer` confused with Java Developer, Web Developer, Application Developer

**Genuine cross-family confusions from missing taxonomy — worth fixing:**
- `data_*` confused with Business Analyst, Data Architect (high frequency across all data roles)
- `ux_designer` / `product_manager` confused with Interior Designer, Graphic Designer
- `ml_engineer` confused with AI Research Engineer, AI Data Associate
- `compliance` confused with Legal Counsel, Corporate Secretarial

## Implementation Plan

### Phase 0 — Extend family taxonomy + re-mine hard negatives

**Script:** `scripts/mine_hard_negatives.py` (update FAMILIES list, re-run)

Add to FAMILIES in `mine_hard_negatives.py`:
```python
("business_analyst",  ["business analyst", "ba analyst", "functional analyst", "systems analyst"]),
("data_architect",    ["data architect", "solutions architect", "enterprise architect"]),
("interior_designer", ["interior designer", "interior design"]),
```

Re-run with more anchors for better coverage:
```
uv run python scripts/mine_hard_negatives.py --samples 50
```

Output: updated `scripts/eval/hard_negatives.json`

---

### Phase 1 — LLM-label all DB jobs with subfamily

**Scripts:** `scripts/sample_jobs.py` (add `--all` flag), `scripts/label_jobs.py` (add `subfamily` field)

**1a. Update `sample_jobs.py`:** add `--all` flag that removes the `LIMIT` clause and dumps all 258k jobs.

**1b. Update `label_jobs.py`:** add a `subfamily` field to the LLM prompt, only for Data & Analytics jobs. New output format:
```json
{"job_uuid": "...", "seniority": "Mid", "function": "Data & Analytics", "subfamily": "bi_analyst"}
```

Subfamily values (only relevant when `function == "Data & Analytics"`):
- `bi_analyst`, `data_analyst`, `data_engineer`, `data_scientist`, `ml_engineer`
- `business_analyst`, `data_architect`
- `null` for other Data & Analytics roles (e.g. BI Developer, Quant)

The existing `labels.jsonl` already has 50k entries — the script resumes automatically (skips done UUIDs). Re-run on all 258k jobs.

Estimated runtime: ~3-4 hours at 20 workers. Cost: ~$5-10 via Gemini Flash Lite.

---

### Phase 2 — Write `scripts/build_triplets_v2.py`

Builds cross-function hard negative triplets and merges with v1 dataset.

**Input:**
- `scripts/eval/hard_negatives.json` (updated from Phase 0)
- `data/finetune/labels.jsonl` (full labels from Phase 1, including `subfamily`)
- DB connection (to fetch job text by UUID)

**Logic:**
1. Load all labeled jobs, index by UUID → `{uuid: {seniority, function, subfamily}}`
2. Build family pools: for data roles use `subfamily`; for others use `function`
3. For each pair in `hard_negatives.json` where `confused_with_family != "unknown"`:
   - Look up anchor's family → find a same-family positive from the pool
   - Use `confused_with_uuid` as the hard negative
   - Skip if anchor and hard negative resolve to the same family (same-family variants)
4. Fetch job text (title + description) from DB for anchor + positive + hard_negative UUIDs
5. Write new triplets to `data/finetune/triplets_v2_train.jsonl` and `triplets_v2_eval.jsonl`
6. Print merge summary: v1 count + v2 additions + total

**Pairs to include:**
- All data-domain cross-family: data_analyst/data_scientist/data_engineer/ml_engineer/bi_analyst/business_analyst/data_architect
- ux_designer <-> interior_designer
- product_manager <-> interior_designer
- marketing <-> sales (384 pairs, significant signal)
- ux_designer <-> product_manager

**Pairs to skip:**
- Any pair where `anchor_family == confused_with_family` after re-mapping
- operations <-> project_manager (borderline, skip for now)
- compliance <-> legal (overlap is legitimate in SG context)

**Script uses `store._get_conn()` / `store._pool.putconn(conn)` not `store._conn`**

---

## Acceptance Criteria

- [ ] Phase 0: `business_analyst`, `data_architect`, `interior_designer` added to FAMILIES; `mine_hard_negatives.py` re-run with `--samples 50`; updated `hard_negatives.json` saved
- [ ] Phase 1a: `sample_jobs.py` has `--all` flag; dumps all 258k jobs without LIMIT
- [ ] Phase 1b: `label_jobs.py` outputs `subfamily` field for Data & Analytics jobs; full 258k-job label run complete
- [ ] Phase 2: `build_triplets_v2.py` written and run; outputs `triplets_v2_train.jsonl` + `triplets_v2_eval.jsonl`
- [ ] v2 triplets extend v1 (do not overwrite existing train/eval files)
- [ ] Script prints summary: new triplet count by family pair

## Notes

- Windows cp1252: use `->` not Unicode arrows in print statements
- `labels.jsonl` is resume-safe (already-done UUIDs skipped) — safe to re-run after crash
- Existing 50k labels in `labels.jsonl` don't have `subfamily` — re-running will backfill them
- Reference: `scripts/build_triplets.py` for v1 structure, `scripts/mine_hard_negatives.py` for DB access pattern
