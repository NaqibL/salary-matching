---
id: SGSAL-022
project: salary-matching
title: Replace ML classifiers with Jev, switch cleaner model, repair LLM-field gap
status: in-progress
priority: high
type: feature
labels: [backend, pipeline, llm, ops]
created: 2026-11-01
updated: 2026-11-01
depends_on: []
blocks: []
---

## Plain-English to-do list (pick up from any machine)

Work through in order. Tick items as they finish. Details and numbers from
the 2026-11-01 spikes are at the bottom.

### A. Ops — do first (needs Luqman's logins)

- [x] A1. Push the new OpenRouter key into GitHub Actions secret `OPENROUTER_API_KEY`
      (Claude is blocked from reading the key; Luqman runs
      `gh secret set OPENROUTER_API_KEY --body <key>` himself or uses the GitHub web UI).
- [ ] A2. Check Railway variables for `OPENROUTER_API_KEY`; update if present.
- [ ] A3. `railway login` so Claude can read logs/metrics via the railway agent.
- [ ] A4. Add `DATABASE_URL` (Supabase session-pooler URI) to local `.env` so
      Claude can query the DB, run migrations and backfills.
- [ ] A5. Repair the gap: Gemini calls returned 401 in every daily embed from
      ~2026-10-22 to 2026-10-31 (2-4k failures per run, ~30k jobs embedded from
      raw text with no skills/years/seniority). Correct mechanism is
      `mcf re-embed --since-days 11` WITH `OPENROUTER_API_KEY` +
      `JOB_EXTRACTOR_LLM_ENABLED=1` (NOT `backfill-rich-fields`, which only
      refetches MCF metadata). Blockers: (1) `.github/workflows/re-embed.yml`
      re-embeds ALL jobs and passes no LLM env - add a `since_days` input and
      the two env vars; (2) the re-embed loop in `cli.py` (~line 778) calls the
      LLM serially, ~1 job/s, so 30k jobs = 8+ h > the 6 h workflow timeout.
      Do B2 (thread pool) first, then run the repair. Repo is public, so
      Actions minutes are free.
- [ ] A6. Confirm the next daily embed shows 0 `401 Unauthorized` lines.

### B. Cheaper cleaner model (one-line change)

- [ ] B1. Decide: switch `OPENROUTER_MODEL` from `google/gemini-2.5-flash-lite`
      to `openai/gpt-oss-120b` (half the cost, more fields found, but ~5x slower
      per call — see spike numbers).
- [ ] B2. CONFIRMED serial: `build_job_text_from_dict` is called once per job inside
      the re-embed loop (`cli.py` ~line 778) and in `incremental_crawl.py`, so
      each LLM call blocks. Add a thread pool (6-8 workers) around the LLM calls
      before switching models or running A5.
- [ ] B3. Update `OPENROUTER_MODEL` in `.env`, `.env.example`, GitHub secret, and
      the default in `src/mcf/lib/embeddings/llm_cleaner.py`. Rename
      `GeminiFlashCleaner` → `OpenRouterCleaner` (keep an alias).
- [ ] B4. Watch one daily embed run: failure count, runtime, cost.

### C. Jev replaces the KMeans/LR classifiers

- [ ] C1. Approve the role-family list (24 families drafted in the spike script,
      copy below). Trim/rename as Luqman prefers. ~15–24 is the target.
- [ ] C2. New module `src/mcf/lib/embeddings/jev_classifier.py`: calls
      `POST https://openrouter.ai/api/alpha/decisions`, model pinned to
      `typesafe/jev-1.14`, two questions (role_family choice, seniority score
      with 4 levels mapped to `T1_Entry..T4_Management`). Pass title,
      description, and MCF `position_levels` in `state`. Return
      (role_key, tier, role_conf, tier_conf). Graceful fallback to None on error.
- [ ] C3. Migration 019: `jobs.role_family TEXT`, `jobs.role_conf REAL`,
      `jobs.tier_conf REAL`. Keep `role_cluster INTEGER` + `predicted_tier` for
      now so the matches page keeps working; map role_family → a stable integer
      id in a new `role_families` lookup table (id, key, display_name, description).
- [ ] C4. Wire into the embed path (`incremental_crawl.py` and `re-embed` in
      `cli.py`): replace `classify_jobs` / `classify_jobs_multilabel` calls with
      the Jev call. Low confidence (<0.5) → role "other".
- [ ] C5. Backfill script for all active jobs (~25k, ≈ $2). Reuse the batch
      pattern from `scripts/finetune/import_embeddings.py`.
- [ ] C6. Frontend: `RoleClusterSelect` and the taxonomy API read from
      `role_families` instead of `role_taxonomy_v2.json`.
- [ ] C7. Delete `src/mcf/matching/classifiers.py`, `src/mcf/models/*.pkl`,
      `role_taxonomy_v2.json`, `scripts/train_classifiers.py`; `uv remove scikit-learn`.
      Rebuild Railway image, check startup.
- [ ] C8. Tests: parse/fallback unit test for the Jev client (no network),
      smoke test that backfilled jobs have `role_family` set.
- [ ] C9. Update CLAUDE.md design facts + `src/mcf/lib/embeddings/README.md`.

### D. Loose ends from the cleanup

- [ ] D1. Stray personal files parked (not deleted) in Claude's scratchpad
      `removed-files` folder on the desktop PC: take-home PDF, article.txt,
      section1 notes, errors.txt, jobdescription.txt, railway-config-pull. Delete
      or move them elsewhere.
- [ ] D2. Untracked `.claude/` marketing drafts: commit or delete.
- [ ] D3. CLAUDE.md still describes the lowball latency roadmap; rewrite that
      section once C ships.

## Spike results (2026-11-01)

**Jev, 50 jobs, `typesafe/jev-1.14`:** 0 errors, p50 0.45 s, $0.000072/job
(~1,700 input tokens because the role criteria ride along) → ≈ $9/month at
4k jobs/day, ≈ $2 for a full backfill. Role family: Jev clearly better than
KMeans (KMeans misfiled ~12/50, e.g. mechanical/process/traffic engineers →
"IT Infrastructure & DevOps", travel agency manager → "Creative, Media &
Design", recruiter → "Social Work"). Tier: 62% agreement with the LR model; on
disagreements Jev was right ~11 vs LR ~5. Jev leans low on MCF
"Professional" roles → feed `position_levels` into state (C2).

**Cleaner model comparison, 20 jobs, production prompt:**

| model | skills found | seniority found | failures | p50 latency | $/job |
|---|---|---|---|---|---|
| google/gemini-2.5-flash-lite (current) | 13 | 14 | 0 | 1.6 s | 0.000161 |
| openai/gpt-oss-120b | 18 | 20 | 0 | 8.4 s | 0.000084 |
| z-ai/glm-5.3-flash | 15 | 17 | 2 | 5.4 s | 0.000137 |
| qwen/qwen3.7-flash | 0 | 0 | 20 | – | – |

Spike scripts (throwaway, committed under `scripts/spikes/`): `jev_spike.py`,
`cleaner_model_compare.py`. Both read local parquet/jsonl (desktop PC only), no DB needed. `jev_results.csv` is the 50-job comparison.

## Draft role families (C1)

software_engineering · data_ai_analytics · it_infra_support_security ·
sales_business_dev · marketing_comms · finance_accounting ·
banking_financial_services · legal_compliance_cosec · human_resources ·
admin_office_support · customer_service · operations_strategy_pm ·
procurement_supply_chain_logistics · warehouse_drivers_delivery ·
engineering_manufacturing · trades_technicians ·
construction_architecture_property · healthcare_allied ·
education_social_services · fnb_hospitality · retail_beauty ·
cleaning_security_general_labour · creative_design · science_research_lab

## Jev API notes

- Endpoint `POST https://openrouter.ai/api/alpha/decisions`, normal OpenRouter key.
- Body: `{model, state: {...}, questions: {name: {type, instructions, criteria}}}`.
  `choice` → `criteria` is a dict of option → description; `score` → `criteria`
  is an ordered list. Answers carry `choice`/`score`, `confidence`, `probabilities`.
- Pricing: $0.042/M input tokens, output free. Each response has `usage.cost`.
- No free text output — Gemini/GPT-OSS cleaner stays for the rewrite + skills.
