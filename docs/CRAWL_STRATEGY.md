# MCF Category Segments (5 Runs)

The MyCareersFuture dataset has **42 job categories**. To avoid timeouts or rate limits, you can crawl them in 5 separate runs. Each run covers roughly 1/5 of the categories.

---

## How to Run

### Option A: GitHub Actions (manual trigger)

1. Go to your repo → **Actions** → **Daily Job Crawl**
2. Click **Run workflow**
3. Set **run** to `1`, `2`, `3`, `4`, or `5` (leave empty for all categories)
4. Set **source** to `mcf` (default)
5. Click **Run workflow**

Run each number (1–5) once to get the full MCF dataset.

### Option B: Local / CLI

```bash
# Run 1 of 5
uv run mcf crawl-incremental --source mcf --categories "Accounting / Auditing / Taxation,Admin / Secretarial,Advertising / Media,Architecture / Interior Design,Banking and Finance,Building and Construction,Consulting,Customer Service"

# Run 2 of 5
uv run mcf crawl-incremental --source mcf --categories "Design,Education and Training,Engineering,Entertainment,Environment / Health,Events / Promotions,F&B,General Management,General Work"

# Run 3 of 5
uv run mcf crawl-incremental --source mcf --categories "Healthcare / Pharmaceutical,Hospitality,Human Resources,Information Technology,Insurance,Legal,Logistics / Supply Chain,Manufacturing"

# Run 4 of 5
uv run mcf crawl-incremental --source mcf --categories "Marketing / Public Relations,Medical / Therapy Services,Others,Personal Care / Beauty,Precision Engineering,Professional Services,Public / Civil Service,Purchasing / Merchandising,Real Estate / Property Management"

# Run 5 of 5
uv run mcf crawl-incremental --source mcf --categories "Repair and Maintenance,Risk Management,Sales / Retail,Sciences / Laboratory / R&D,Security and Investigation,Social Services,Telecommunications,Travel / Tourism,Wholesale Trade"
```

---

## Category Breakdown

| Run | Categories | Count |
|-----|------------|-------|
| **1** | Accounting / Auditing / Taxation, Admin / Secretarial, Advertising / Media, Architecture / Interior Design, Banking and Finance, Building and Construction, Consulting, Customer Service | 8 |
| **2** | Design, Education and Training, Engineering, Entertainment, Environment / Health, Events / Promotions, F&B, General Management, General Work | 9 |
| **3** | Healthcare / Pharmaceutical, Hospitality, Human Resources, Information Technology, Insurance, Legal, Logistics / Supply Chain, Manufacturing | 8 |
| **4** | Marketing / Public Relations, Medical / Therapy Services, Others, Personal Care / Beauty, Precision Engineering, Professional Services, Public / Civil Service, Purchasing / Merchandising, Real Estate / Property Management | 9 |
| **5** | Repair and Maintenance, Risk Management, Sales / Retail, Sciences / Laboratory / R&D, Security and Investigation, Social Services, Telecommunications, Travel / Tourism, Wholesale Trade | 9 |

---

## Full Dataset

- The workflow runs without a job limit by default, so each run fetches all jobs in its category segment.
- **Careers@Gov** uses `--source cag` and has no categories; run it separately.
- **All MCF + CAG:** Use `--source all` with no run number (or run 1–5 for MCF only, then run `cag` separately).
