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
- [x] A2. Railway HAS `OPENROUTER_API_KEY` (old, dead) and `OPENROUTER_MODEL`. Update the
      key: `railway variables --set "OPENROUTER_API_KEY=<key>"` (Luqman runs it; Claude
      is blocked from reading the key). Only owner-only resume cleaning uses it.
- [x] A3. `railway login` so Claude can read logs/metrics via the railway agent.
- [x] A4. Add `DATABASE_URL` (Supabase session-pooler URI) to local `.env` so
      Claude can query the DB, run migrations and backfills.
- [ ] A5. IN PROGRESS. Run 5 started 11:55 UTC 2026-11-01:
      https://github.com/NaqibL/salary-matching/actions/runs/41304064764
      (~4,400 jobs left at 12:00 UTC, ~1.1 jobs/s, expected done ~13:05 UTC).
      HOW TO CHECK: `gh run view 41304064764 --json status,conclusion`, then count
      active jobs embedded in the last 13 days whose skills AND seniority are
      empty (SQL in `scripts/backfill_role_families.py` style; see
      `get_active_jobs_embedded_since(..., missing_llm_only=True)`). A small
      residual (jobs whose text has no skills) is normal. If the run failed or
      timed out, re-trigger — it resumes:
      `gh workflow run re-embed.yml -f since_days=13 -f missing_llm_only=true -f llm_workers=12`
      History: runs 1-2 cancelled (per-job DB UPDATE was the bottleneck → batched,
      commit 04893b8); run 3 reached 23,296 then FAILED 11:17 UTC when Supabase put
      the project into read-only mode; run 4 failed instantly for the same reason.
      Root cause: disk had auto-grown to 18 GB while the Pro spend cap allows 8 GB
      → Supabase restricts the project. Fixed by Luqman disabling the spend cap
      (≈ $1.25/month extra for 10 GB); writes back 11:55 UTC. Also truncated
      `embeddings_cache` (3.9 GB duplicate of job_embeddings, nothing read it);
      DB is 7 GB on an 18 GB disk.
      Original notes: Verified in the DB on 2026-11-01: every job embedded
      from 2026-10-22 to 10-31 has EMPTY LLM fields (`llm_fields_json` is present
      but all-null because the cleaner's failure fallback still writes the row);
      10-20 and 10-21 were ~65% empty (partial failure). That is 25,020 active
      jobs. Normal days run ~30% empty (no skills in the text), so target the
      outage window, not "all empty".
      Mechanism: `mcf re-embed` with LLM on (`OPENROUTER_API_KEY` +
      `JOB_EXTRACTOR_LLM_ENABLED=1`), selecting active jobs whose
      `job_embeddings.embedded_at >= 2026-10-20` AND skills/seniority are null.
      `--since-days 13` is the nearest existing flag (re-embeds ~35k); a targeted
      `--missing-llm-since <date>` flag would be cleaner. NOT `backfill-rich-fields`
      (that only refetches MCF metadata).
      Blockers: (1) `.github/workflows/re-embed.yml` re-embeds ALL jobs and
      passes no LLM env - add inputs + env; (2) the re-embed loop in `cli.py`
      (~line 778) calls the LLM serially (~1 job/s) so 25k jobs = 7 h > the 6 h
      workflow timeout. Do B2 (thread pool) first. Repo is public, so Actions
      minutes are free. Cost ≈ $4 on Gemini, ≈ $2 on GPT-OSS.
- [ ] A6. Confirm the next daily embed shows 0 `401 Unauthorized` lines.

### B. Cheaper cleaner model (one-line change)

- [x] B1. Decided 2026-11-01: `google/gemma-4-26b-a4b-it` (30-job shootout below:
      same quality as gpt-oss-120b, 0 failures, 2x faster, ~$0.10/1k jobs vs
      $0.15 on Gemini). gpt-oss-120b was the runner-up but at 9 s/call the 25k
      repair would not fit the 6 h workflow limit.
- [x] B2. Done 2026-11-01: `build_texts_parallel()` in `job_text.py` runs the
      text/LLM step on a thread pool (env `LLM_CLEAN_WORKERS`, default 8;
      `mcf re-embed --llm-workers N`). Used by the re-embed loop and
      `incremental_crawl.py`. Runs inline when the LLM is off. DB batch writes
      unchanged. Unit test: `tests/test_job_text_parallel.py`.
- [x] B3. Done 2026-11-01 in code: default in `llm_cleaner.py` + `config.py`,
      `.env`, `.env.example`, CLAUDE.md; `GeminiFlashCleaner` → `OpenRouterCleaner`
      (alias kept). Luqman still needs to set the GitHub secret `OPENROUTER_MODEL`
      and Railway: DONE 2026-11-01 — Railway `OPENROUTER_MODEL` set to
      `google/gemma-4-26b-a4b-it` (also used by the owner-only resume cleaner);
      the unused GitHub secret `OPENROUTER_MODEL` should be deleted by Luqman
      (`gh secret delete OPENROUTER_MODEL`; Claude is blocked from secret writes;
      workflows use the code default so it is harmless meanwhile). Daily embed now runs with `ENABLE_EMBEDDINGS_CACHE=0`.
- [ ] B4. Watch one daily embed run: failure count, runtime, cost.

### C. Jev replaces the KMeans/LR classifiers

- [x] C1. Approved 2026-11-01 (Luqman delegated the call): keep all 24 families
      as drafted below, no renames.
- [x] C2. Done 2026-11-01. New module `src/mcf/lib/embeddings/jev_classifier.py`: calls
      `POST https://openrouter.ai/api/alpha/decisions`, model pinned to
      `typesafe/jev-1.14`, two questions (role_family choice, seniority score
      with 4 levels mapped to `T1_Entry..T4_Management`). Pass title,
      description, and MCF `position_levels` in `state`. Return
      (role_key, tier, role_conf, tier_conf). Graceful fallback to None on error.
- [x] C3. Done 2026-11-01 (applied to Supabase; also in `ensure_schema`). Migration 019: `jobs.role_family TEXT`, `jobs.role_conf REAL`,
      `jobs.tier_conf REAL`. Keep `role_cluster INTEGER` + `predicted_tier` for
      now so the matches page keeps working; map role_family → a stable integer
      id in a new `role_families` lookup table (id, key, display_name, description).
- [x] C4. Done 2026-11-01 for `incremental_crawl.py` (Phase 3 uses Jev when the
      key is set, legacy KMeans/LR otherwise; low confidence → "other", id 0).
      `re-embed` never classified, so the backfill script covers existing jobs.
- [ ] C5. IN PROGRESS. `scripts/backfill_role_families.py` (resumable: selects
      active jobs with `role_family IS NULL`). Restarted 11:56 UTC on the desktop
      PC, 8 workers, ~9 jobs/s, 0 failures, ≈ $0.07 per 1k jobs; 68,924 to go at
      start → expected done ~14:00 UTC. It dies if the Claude session that
      started it is closed. HOW TO CHECK: `SELECT count(*) FROM jobs WHERE is_active
      AND role_family IS NULL` (target: 0). TO RESUME:
      `uv run python scripts/backfill_role_families.py --workers 8`
- [x] C6. Done 2026-11-01 backend-side: `/api/jobs/taxonomy` serves
      `role_families` (ids = `jobs.role_cluster`), so `RoleClusterSelect` needs
      no change. `ROLE_TAXONOMY_SOURCE=kmeans` reverts.
- [ ] C7. Delete `src/mcf/matching/classifiers.py`, `src/mcf/models/*.pkl`,
      `role_taxonomy_v2.json`, `scripts/train_classifiers.py`; `uv remove scikit-learn`.
      Rebuild Railway image, check startup.
- [ ] C8. Unit tests done (`tests/test_jev_classifier.py`, mock transport).
      Smoke test for backfilled jobs still to add after C5.
- [x] C9. Done 2026-11-01 (CLAUDE.md design fact 8, embeddings README).

### E. Found on 2026-11-01 while repairing (not yet done)

- [ ] E1. Railway var `ALLOW_ANONYMOUS_LOCAL=true` is set in PRODUCTION: it disables
      all API auth (owner-only endpoints are open). Public routes use
      `get_optional_user`, so removing it is safe. Luqman runs
      `railway variables --delete ALLOW_ANONYMOUS_LOCAL` (Claude is blocked).
- [ ] E2. Delete the unused GitHub secret `OPENROUTER_MODEL`
      (`gh secret delete OPENROUTER_MODEL`; workflows use the code default).
- [ ] E3. Watch the next daily embed (15:40 UTC): 0 `401` lines, runtime, cost
      (= A6/B4). First run with gemma-4, the thread pool, batched writes and
      `ENABLE_EMBEDDINGS_CACHE=0`.
- [ ] E4. Apply `scripts/migrations/020_llm_fields_dashboard_index.sql` manually
      (CONCURRENTLY, Supabase SQL editor) — speeds the skills-trend dashboard query.
- [ ] E5. Disk hygiene (no feature impact): drop the duplicate index
      `idx_job_embeddings_job_uuid` (same columns as the PK, 41 MB) at a quiet
      moment — NOT while a VACUUM or backfill holds `job_embeddings`, it queues
      behind them and blocks the live checker (happened today, terminated);
      add a crawl step that keeps only 90 days of `job_run_status`
      (920k of 1.5M rows are older; only the current run's rows are ever read).
- [ ] E6. Decide a retention rule for expired jobs' embeddings (538k of 606k
      vectors belong to expired postings; 246k are 90-180 days old). Deleting
      embeddings (not job rows) older than 90 days would free ~1 GB and cap
      growth; the checker's "historical" matches would reach back 3 months.
      Luqman has not decided; not needed now that the spend cap is off.
- [ ] E7. Dedup near-identical postings (recruiter reposts, same company).
      Product change (affects dashboard counts + benchmarks) → own ticket.
- [x] E8. Jobs pool never warmed in production (pgvector 0.4 `Vector` TypeError
      on every startup). Fixed + pool TTL 15 min → 24 h (each load is ~650 MB of
      Supabase egress; commit 2b048db).
- [x] E9. Shipped today beyond this ticket: lowball/salary-search response cache
      (cd7a30c), similar-roles client filters (16c7bb5), dashboard seniority /
      top-skills / skills-trend / role-family analytics (6082f2d).

### D. Loose ends from the cleanup

- [x] D0. Incident 2026-11-01: the Railway redeploy after the key change CRASHED on
      startup (torch mixed-version import error, ~20 min of 502s). Fixed by
      pinning `torch==2.10.0` in `Dockerfile.api` so the pip pre-install matches
      uv.lock. Any future Railway rebuild would have hit this; now deterministic.

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
4k jobs/day, ≈ $5 for a full backfill (72.9k active jobs). Role family: Jev clearly better than
KMeans (KMeans misfiled ~12/50, e.g. mechanical/process/traffic engineers →
"IT Infrastructure & DevOps", travel agency manager → "Creative, Media &
Design", recruiter → "Social Work"). Tier: 62% agreement with the LR model; on
disagreements Jev was right ~11 vs LR ~5. Jev leans low on MCF
"Professional" roles → feed `position_levels` into state (C2).

**Cleaner model shootout, 30 random active DB jobs, production prompt, 6 workers (2026-11-01, run 2):**

| model | failed | skills | years | seniority | p50 / p90 latency | wall (30 jobs) | $/1k jobs |
|---|---|---|---|---|---|---|---|
| google/gemini-2.5-flash-lite (current) | 0 | 22 | 7 | 21 | 1.4 s / 1.8 s | 14 s | 0.147 |
| openai/gpt-oss-120b | 0 | 29 | 12 | 30 | 8.9 s / 17.9 s | 54 s | 0.065 |
| google/gemma-4-26b-a4b-it | 0 | 30 | 11 | 29 | 4.3 s / 6.6 s | 25 s | 0.095 |
| z-ai/glm-5.3-flash | 1 | 27 | 11 | 28 | 4.3 s / 7.9 s | 30 s | 0.128 |
| mistralai/mistral-small-24b-instruct-2501 | 0 | 20 | 11 | 30 | 3.4 s / 11.2 s | 26 s | 0.046 |
| meta-llama/llama-3.1-8b-instruct | 0 | 26 | 16* | 30 | 5.2 s / 7.8 s | 30 s | 0.049 |
| openai/gpt-oss-20b | 4 (DQ) | 26 | 10 | 26 | 4.8 s | 40 s | 0.096 |
| google/gemma-3-12b-it | 6 (DQ) | 0 | 0 | 0 | 3.9 s | 358 s | 0.064 |
| nvidia/nemotron-3-nano-30b-a3b | 27 (DQ) | 3 | 1 | 3 | – | – | – |
| openai/gpt-5-nano | 30 (DQ) | 0 | 0 | 0 | – | – | – |

\* Llama's extra "years" hits are hallucinated (it invents 2–3 years on jobs where
no other model and the JD itself state none) → not trusted. gpt-5-nano and
gpt-oss-20b fail because reasoning eats the 1200 max_tokens and the reply comes
back empty; gemma-3 ignores the ===FIELDS=== marker. Total spend ≈ $0.02.
Script now samples from `DATABASE_URL` and pulls pricing live from OpenRouter.

**Earlier run — 20 jobs, local jsonl:**

| model | skills found | seniority found | failures | p50 latency | $/job |
|---|---|---|---|---|---|
| google/gemini-2.5-flash-lite (current) | 13 | 14 | 0 | 1.6 s | 0.000161 |
| openai/gpt-oss-120b | 18 | 20 | 0 | 8.4 s | 0.000084 |
| z-ai/glm-5.3-flash | 15 | 17 | 2 | 5.4 s | 0.000137 |
| qwen/qwen3.7-flash | 0 | 0 | 20 | – | – |

Spike scripts (throwaway, committed under `scripts/spikes/`): `jev_spike.py`,
`cleaner_model_compare.py`. `jev_spike.py` reads local parquet (desktop PC only); `cleaner_model_compare.py` reads from `DATABASE_URL`. `jev_results.csv` is the 50-job comparison.

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
