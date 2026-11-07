# Pre-Release Checklist

Generated 2026-05-31 via 4-agent parallel review. Fix blockers before making the repo/site public.

---

## BLOCKERS

- [ ] **B1 — Rotate Supabase DB password**
  Live password (`LuqmanNaqib01!`) was found in `.claude/settings.local.json` (gitignored, not committed). Rotate in Supabase dashboard > Settings > Database regardless.

- [ ] **B2 — Add `frontend/middleware.ts`**
  No server-side route guard exists. `/matches`, `/saved`, `/profile` page shells are served to unauthenticated visitors.
  Fix: create `frontend/middleware.ts` using `createMiddlewareClient`, check session, redirect to `/?redirect=...` for those three paths.

- [ ] **B3 — Guard `ALLOW_ANONYMOUS_LOCAL` in prod**
  If set on Railway alongside `SUPABASE_URL`, it silently disables all FastAPI auth.
  Fix: in `src/mcf/api/auth.py` or `lifespan`, assert/log loudly if `allow_anonymous_local=True` and `auth_enabled=True` simultaneously.

- [ ] **B4 — Fix global error handler leaking `str(exc)`**
  `src/mcf/api/server.py:71` — returns raw Python exception text to clients (can expose DB strings, table names, file paths).
  Fix: replace non-HTTPException branch with `"Internal server error"`.

- [ ] **B5 — Fix resume route raw exception exposure**
  `src/mcf/api/routes/profile.py:59,83,123` — three `raise HTTPException(500, detail=f"...: {e}")` patterns.
  Fix: log `exc_info=True`, return fixed string.

- [ ] **B6 — Add rate limiting to public endpoints**
  `/api/lowball/check` and `/api/salary/search` accept arbitrary text, trigger BGE embedding + KNN scan, zero throttle.
  Fix: add `slowapi`, ~10 req/min on `/api/lowball/check`, ~60 req/min on `/api/companies`.

---

## WARNINGS

- [ ] **W1 — Disable Supabase sign-ups**
  Any visitor can self-register and access `/matches`, `/saved`, `/profile`.
  Fix: Supabase dashboard > Auth > Settings > Disable sign-ups. One click.

- [ ] **W2 — Remove/gate `/api/cors-check`**
  Unauthenticated endpoint returns full `ALLOWED_ORIGINS` list to any caller.
  Fix: gate behind `_verify_admin_or_secret` or delete. `src/mcf/api/server.py:112–126`.

- [ ] **W3 — Remove debug `console.log` in salary checker**
  `frontend/app/lowball/LowballContent.tsx:382` — logs company list count on every load.
  Fix: delete the `console.log` line.

- [ ] **W4 — Harden JWT error message**
  `src/mcf/api/auth.py:77` — `f"Invalid token: {exc}"` can leak token structure hints.
  Fix: return fixed string `"Invalid token"`.

- [ ] **W5 — Gitignore gaps**
  Add to `.gitignore`:
  ```
  resume.txt
  agent-analysis-summary.txt
  scripts/interest_profile.txt
  scripts/train_output/
  scripts/similarity_*.txt
  scripts/cluster_analysis_output/
  frontend/node_modules/
  *.log
  ```

- [ ] **W6 — Delete sensitive untracked files**
  - `resume.txt` — contains phone number, email, full employment history (PII)
  - `scripts/interest_profile.txt` — personal job search goals and company exclusions
  - `agent-analysis-summary.txt` — internal architecture notes

- [ ] **W7 — Handle `scripts/cluster_analysis_output/` (already committed)**
  Contains scraped MCF job data as `.parquet` files. May violate MCF ToS to redistribute.
  Decision needed: remove from git history (`git filter-repo`) or leave it.

- [ ] **W8 — Remove hardcoded Algolia fallback**
  `src/mcf/lib/sources/cag_source.py:22,32` — real App ID + API key hardcoded as defaults.
  Fix: remove defaults, require env vars explicitly, add clear error message.

- [ ] **W9 — Remove dead dashboard auth endpoints**
  `src/mcf/api/routes/dashboard.py:14–59` — three auth-gated endpoints are duplicates of `-public` twins; `user_id` is accepted but ignored.
  Fix: delete the three auth-gated variants.

- [ ] **W10 — Silent localhost fallback in 15+ Next.js route handlers**
  `const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'` in every route handler.
  Fix: throw/warn at startup if env var unset in non-dev environments.

---

## MINORS

- [ ] **M1 — Remove `axios` from `frontend/package.json`** — dead dep or architecture violation
- [ ] **M2 — Upgrade Next.js 14 → 15** — 14 is unmaintained
- [ ] **M3 — `server-fetch.ts:12`** — silent `http://localhost:3000` fallback in SSR context; make it explicit
- [ ] **M4 — `GET /api/jobs/taxonomy`** — no auth, triggers model-load side effect on cold call
- [ ] **M5 — ESLint 8 EOL** — upgrade to ESLint 9

---

## Context for next session

- This is a Singapore salary benchmarking tool (MCF + CAG data, BGE embeddings, Next.js + FastAPI)
- Public pages: `/` (salary checker), `/dashboard`, `/companies`
- Owner-only pages: `/matches`, `/saved`, `/profile` (hidden from nav, auth-gated)
- Stack: FastAPI on Railway, Next.js on Vercel, Supabase (Postgres + Auth)
- Review was run before making the GitHub repo and Vercel site public
- Start the dev server with: `uv run python -m uvicorn mcf.api.server:app --reload --port 8000` (note: `uv run uvicorn` has a Windows script path bug)
