# Changelog

## 2026-06-02

### Salary checker: EP compliance filter and UX polish

- **Monthly base label** — salary input and result band now explicitly labelled "Monthly Base (SGD)" to match EP/PEP framing
- **Recruiter caveat** — note beneath the salary bar flags that posted ranges tend to run 10–20% above actual offers
- **EP compliance filter** — ranges where `salary_max > 2× salary_min` (malformed outliers) are now excluded from the percentile pool before P25/P50/P75 are computed
- **P50 as headline** — "Typical salary" is now the primary figure; P25/P75 move to secondary context with sample size and methodology note
- **Mobile fix** — job description text on similar-roles cards no longer overflows on small screens (capped scroll height + preserved whitespace)

---

## 2026-05 — Performance and reliability

### Query performance
- Added HNSW index on `job_embeddings.embedding` (`vector_cosine_ops`) — cosine search drops from full table scan to ANN
- Rewrote HNSW query as a subquery to prevent nested-loop over-scan; capped ranked results at 500 to match `ef_search`
- Binary embedding transfer via pgvector psycopg2 adapter — reduces serialization overhead on every vector read
- Active-jobs pool cache (pre-stacked numpy matrix, 15-min TTL) now used by lowball routes, not only matches

### Connection pool and SSL resilience
- TCP keepalives + SELECT 1 probe on connection checkout to catch stale SSL sockets early
- Discard unrestorable connections instead of returning them dirty to the pool
- BaseException handling in `_transaction_cur` prevents pool corruption on KeyboardInterrupt / OOM
- `SET LOCAL statement_timeout` via `_transaction_cur` across all slow queries (PgBouncer-compatible)
- Pool size tuned to 50 (Supabase Pro direct limit: 60)
- Thundering-herd guard on active-jobs pool cache miss to prevent OOM under concurrent cold starts

### Other backend fixes
- `ensure_schema` timeout caught at startup so a slow DB doesn't crash the server on first request
- DB connections opened after MCF API fetch to avoid SSL expiry during long crawls

---

## 2026-04 — Company pages and public launch

### Company Explorer
- **Companies browse page** — list all hiring companies with popular filter; recruitment agencies excluded
- **Company profile page** — salary range, hiring patterns (monthly listings), top skills breakdown, latest openings
- **Company canonicalization** — LLM-assisted dedup merges variant spellings; `company_canonical` used throughout autocomplete and lookup
- **Custom CompanyCombobox** — replaces native `<datalist>` for reliable overflow behaviour; bloat/agency names filtered from suggestions

### Public launch hardening
- Removed Sign In nav link — public users no longer funnel into the auth gate
- Job detail page and endpoint made publicly accessible (no auth required)
- Rate limiter IP detection fixed; input validation hardened on lowball and companies routes
- Open Graph meta tags + static OG screenshot for link previews

### Rebrand
- Renamed from "SG Salary" to **Lowball** across the UI
- Consolidated `/` and `/lowball` — homepage is now the full salary checker; `/lowball` redirects

---

## 2026-03 — Salary checker core and LLM enrichment

### Salary Checker
- Launched `/lowball` salary checker — paste a job title + description, get a percentile band vs. live market data
- Company filter tab — narrow results to what a specific employer pays
- Salary midpoint used for percentile calculation when both min and max are present

### LLM enrichment
- `GeminiFlashCleaner` (Gemini 2.5 Flash Lite via OpenRouter) runs during embed to extract `min_years_experience`, inferred seniority, and canonical skills
- Enriched fields surface on similar-roles cards (experience badge, seniority tag, skill chips)
- LLM hints never override scraper-provided salary, position levels, or employment types

### Infrastructure
- Removed DuckDB — Postgres/Supabase is the only backend
- HNSW `ef_search = 100` set at query time via `SET LOCAL` (PgBouncer-compatible)
- Telegram job digest bot for personal use
