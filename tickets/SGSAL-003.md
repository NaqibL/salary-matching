---
id: SGSAL-003
project: salary-matching
title: BGE v2 — re-run eval + verify BI Analyst case study
status: done
priority: high
type: research
labels: [ml, embeddings, fine-tuning, bge, eval]
created: 2026-06-13
updated: 2026-06-14
depends_on: [SGSAL-002]
---

## Summary

After deploying v2 to production, re-run the pairwise eval and the Shopee BI Analyst case study to confirm the cross-function confusion is fixed.

## Context

- v1 baseline: 170/200 pairs correct (85%), all 30 failures are "pos not found in top-500" (not ranking errors)
- Shopee BI Analyst case study: global top-20 returns Data Analyst/Data Scientist/Data Engineer instead of BI Analyst roles
- Company-level match for "Business Intelligence Analyst, Regional BI" only scores 0.5216 — steep drop
- Root cause: model over-indexes on SQL/Python signals, under-weights BI-specific signals (Tableau, Power BI, dashboards, KPI reporting)
- Eval scripts: `scripts/eval_lowball.py`, `scripts/casestudy_debug.py`
- Gold standard: `scripts/eval/gold_standard.json` (100 test cases, 200 pairs)

## Acceptance Criteria

- [x] Deploy v2 model — update `src/mcf/lib/embeddings/embedder.py` with new HF model ID
- [x] Re-run `scripts/eval_lowball.py` — pairwise accuracy should improve over 85%
- [x] Re-run `scripts/casestudy_debug.py` for Shopee BI Analyst — BI Analyst roles should appear in top-20
- [x] Save results to `scripts/eval/results_v2.json`
- [x] Update memory with v2 eval results

## v2 Results (2026-06-14)

**Pairwise eval:** 175/200 pairs correct = **87.5%** (up from 85.0% v1, +2.5pp)

By category:
- Software Engineering: 30/30 (100%)
- Admin / Customer Service: 10/10 (100%)
- Marketing / Sales / BD: 16/16 (100%)
- Product / UX: 10/10 (100%)
- Data / ML / AI: 27/30 (90%) — 3 failures: "pos not found in top-500" (NLP Engineer, Data Engineer, Applied Scientist)
- Government / Education: 9/10 (90%)
- Finance / Banking: 21/24 (87.5%)
- Legal / Consulting: 10/12 (83.3%)
- Operations / Supply Chain: 13/16 (81.2%)
- HR: 7/10 (70%)
- Engineering (Non-Tech): 11/16 (68.8%)
- Healthcare: 11/16 (68.8%)

All 25 failures remain "pos not found in top-500" (DB coverage gaps), zero ranking inversions.

**Case study — Shopee BI Analyst (2026-06-14):**
- Company match: "Business Intelligence Analyst, Regional BI" now scores **0.6158** (up from 0.5216 v1, +0.09)
- Company #1 match is now the correct BI Analyst role
- Global top-20: BI-adjacent roles (Power BI, Tableau, reporting) now dominate — much less pure data engineering

## Notes

- Remember to restart the FastAPI server after changing model ID — BGE loads at startup
- First request after model change: 30–60s (downloads at runtime, not build time)
