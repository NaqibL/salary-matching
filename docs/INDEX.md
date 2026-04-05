# Documentation index

---

## Start here

| Doc | Purpose |
|-----|---------|
| [HANDOVER.md](../HANDOVER.md) | Onboarding, reading order, operational notes |
| [docs/NEXT_STEPS.md](NEXT_STEPS.md) | Living to-do list — pending work with exact steps |
| [docs/TECH_STACK.md](TECH_STACK.md) | Versions, env vars, Docker vs `uv` |
| [docs/REPOSITORY_MAP.md](REPOSITORY_MAP.md) | Modules, routes, CLI, migrations |
| [docs/RUNTIME_FLOWS.md](RUNTIME_FLOWS.md) | Auth layers, matches path, webhooks, caches |

---

## Root (`/`)

| File | Notes |
|------|-------|
| [README.md](../README.md) | Quick start + CLI reference |
| [PROJECT_STATUS.md](../PROJECT_STATUS.md) | Feature matrix, bugs, backlog |
| [DEPLOYMENT.md](../DEPLOYMENT.md) | Supabase, Railway, Vercel, GitHub Actions |

---

## `docs/`

| File | Notes |
|------|-------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | High-level flow + mermaid diagram |
| [TECH_STACK.md](TECH_STACK.md) | Canonical stack + env var table |
| [REPOSITORY_MAP.md](REPOSITORY_MAP.md) | File and route inventory |
| [RUNTIME_FLOWS.md](RUNTIME_FLOWS.md) | JWT layers, caching, taste profile |
| [CACHING_STRATEGIES.md](CACHING_STRATEGIES.md) | All cache layers, TTLs, invalidation |
| [CRAWL_STRATEGY.md](CRAWL_STRATEGY.md) | MCF 5-run category segmentation |
| [SUPABASE_RPC.md](SUPABASE_RPC.md) | Optional RPC functions + `rpc_result_cache` |

---

## `scripts/`

| File | Notes |
|------|-------|
| [BACKFILL_README.md](../scripts/BACKFILL_README.md) | Rich fields backfill |
| [LOCAL_CRAWL_WORKFLOW.md](../scripts/LOCAL_CRAWL_WORKFLOW.md) | DuckDB crawl → export to Postgres |
| [schema.sql](../scripts/schema.sql) | Base schema |
| [migrations/*.sql](../scripts/migrations/) | Apply in numeric order `001`–`008` |
| [clear_database.sql](../scripts/clear_database.sql) | **Destructive** — wipes all data |
| [clear_cag_data.sql](../scripts/clear_cag_data.sql) | **Destructive** — CAG rows only |

---

## Ops

| File | Notes |
|------|-------|
| [.github/workflows/daily-crawl.yml](../.github/workflows/daily-crawl.yml) | Scheduled crawl (02:00 UTC) |
| [.github/workflows/backfill-rich-fields.yml](../.github/workflows/backfill-rich-fields.yml) | Manual backfill trigger |
| [.github/workflows/lint.yml](../.github/workflows/lint.yml) | Smoke tests on every PR/push |
| [Dockerfile.api](../Dockerfile.api) | API image (uses `requirements.txt`) |

---

## Dependency files

| File | Notes |
|------|-------|
| [pyproject.toml](../pyproject.toml) | **Source of truth** for Python deps |
| [uv.lock](../uv.lock) | Locked versions |
| [requirements.txt](../requirements.txt) | **Generated**: `uv pip compile pyproject.toml -o requirements.txt`. Used by `Dockerfile.api`. |
| [frontend/package.json](../frontend/package.json) | Node / Next.js dependencies |
