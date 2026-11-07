# Fine-Tuning the BGE Embedding Model

## Goal

Fine-tune `BAAI/bge-base-en-v1.5` to improve salary checker (`/lowball`) retrieval quality.

**Problem:** The model struggles to differentiate seniority levels — a Mid-level Data Analyst query can return Senior or Junior results because the JD content overlaps heavily in embedding space.

**Target:** Salary checker only. Resume matching is not a goal.

---

## Model Facts

| Property | Value |
|---|---|
| Model | `BAAI/bge-base-en-v1.5` |
| Parameters | ~109M (BERT-base) |
| Dimensions | 768 |
| Token limit | 512 |

---

## Approach

**Job-to-job contrastive learning with LLM-extracted labels.** Not synthetic query generation, not query-document pairs.

The LLM reads each job description and assigns two labels. Those labels define which jobs are positives and which are hard negatives for training.

- Same function + same seniority → **positive**
- Same function + adjacent seniority → **hard negative** (primary fix)
- Different function → easy negative (in-batch automatically)

**Query format at inference:** title + description concatenated. No explicit seniority input from users — they naturally embed seniority signals in their description. Zero UX friction.

---

## Extraction Schema

Two fields extracted per job via LLM:

**Seniority**
`Intern` | `Entry` | `Mid` | `Senior` | `Lead` | `Manager` | `Ambiguous`

Intern is a special case outside the main ladder. Junior absorbed into Entry; Director absorbed into Manager.

**Function** (17 broad buckets — intentionally coarse for LLM determinism)
`Engineering & Technology` | `Data & Analytics` | `Product & Design` | `Sales & Marketing` | `Finance & Accounting` | `Legal & Compliance` | `People & HR` | `Operations & Admin` | `Supply Chain & Logistics` | `Healthcare & Allied Health` | `Science & Research` | `Customer Service & Support` | `F&B & Hospitality` | `Trades & Technical` | `Education & Training` | `Retail` | `Other`

`Other` is a valid label — do not force a bad fit.

**Ruled out:** IC vs manager (redundant with seniority), industry/sector (determined by company not JD), years of experience as a required field (nullable explicit only), scraper `position_levels_json` (inconsistent and untrustworthy).

---

## Training Pipeline

### Step 1 — Sample
Pull 50k jobs (title + description) at random from the DB.

```sql
SELECT job_uuid, title, description
FROM jobs
ORDER BY RANDOM()
LIMIT 50000;
```

Export to `data/jobs_sample.jsonl`.

### Step 2 — LLM Labeling
Run `scripts/label_jobs.py` — async Python, ~20 concurrent workers, Gemini Flash Lite via OpenRouter.

- Structured output: `{"seniority": "...", "function": "..."}`
- Low temperature for determinism
- Checkpoint to `data/labels.jsonl` every 100 jobs (crash safety)
- Estimated time: 1.5–3 hours. Estimated cost: ~$2–3 total.
- Run locally before the Kaggle notebook.

### Step 3 — Build Training Triplets
Run `scripts/build_triplets.py`:

1. Group labeled jobs by `(function, seniority)` bucket
2. For each anchor: sample a positive from the same bucket, sample a hard negative from the same function + adjacent seniority level
3. **Stratify:** oversample rare `(function, seniority)` combos — do not sample proportionally to DB frequency or Director/Intern will be underrepresented
4. **Cluster batches:** arrange triplets so each batch is predominantly jobs from the same function bucket — this ensures every gradient step is dense with same-function, different-seniority contrasts
5. Hold out 10% of labeled jobs before building triplets (eval set — never seen during training)

Output: `data/triplets_train.jsonl`, `data/triplets_eval.jsonl`
Format per row: `{"anchor": "...", "positive": "...", "hard_negative": "..."}`

### Step 4 — Fine-Tune (Kaggle T4)
Run `scripts/finetune_bge.py`:

```python
from sentence_transformers import SentenceTransformer, losses
from sentence_transformers.readers import TripletReader
from torch.utils.data import DataLoader

model = SentenceTransformer("BAAI/bge-base-en-v1.5")

# Load triplets → list[InputExample(texts=[anchor, positive, hard_negative])]
train_dataloader = DataLoader(examples, shuffle=False, batch_size=32)  # shuffle=False — batches are pre-clustered

loss = losses.CachedMultipleNegativesRankingLoss(model)

model.fit(
    train_objectives=[(train_dataloader, loss)],
    epochs=3,
    warmup_steps=100,
    output_path="models/bge-base-sgmarket-v1",
    checkpoint_save_steps=500,
)
```

Estimated time: 2–3 hours on T4. Well within Kaggle's 12-hour session limit.
Save model to Kaggle output or mount Google Drive.

### Step 5 — Evaluate
Using the held-out eval set:
- Compute cosine similarity within `(function, seniority)` buckets — should be tighter than base model
- Compute cosine similarity across seniority levels within same function — should be larger than base model
- Manual spot-checks: run salary checker queries, compare top results side by side

Only proceed to Step 6 if eval shows clear improvement.

### Step 6 — Deploy
1. Upload fine-tuned model to Hugging Face Hub (free, private repo)
2. Update `DEFAULT_MODEL` in `src/mcf/lib/embeddings/embedder.py`
3. Re-embed all jobs: `uv run mcf embed --all`
4. Verify salary checker results in production

---

## Compute Plan

| Task | Where | Est. Time | Est. Cost |
|---|---|---|---|
| LLM labeling (50k jobs) | Local, async 20 workers | 1.5–3 hours | ~$2–3 |
| Fine-tuning | Kaggle T4 (free) | 2–3 hours | Free |
| Re-embedding all jobs | Railway (post-deploy) | 30–60 min | Included |

---

## What This Will and Won't Fix

**Likely to improve:**
- Seniority separation — Mid vs Senior vs Junior retrieval
- Function separation — Data roles vs Engineering vs Finance
- Salary checker "similar roles" coherence

**Will not fix:**
- Inference speed (same architecture, same size)
- Queries on roles not represented in the 50k sample
