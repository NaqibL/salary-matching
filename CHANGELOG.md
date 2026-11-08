# Changelog

Technical record for Lowball (sglowball.vercel.app). Newest first. Public-facing notes live on
the site's [Findings](https://sglowball.vercel.app/findings) page, which links here per entry;
headings below are stable anchors, so keep them when editing. Tickets are under `tickets/`,
design notes under `docs/superpowers/specs/`.

---

## SGSAL-028 companies registry and agency label

**2026-11-08.** `companies` table (migration 025) stores each posting company's UEN and SSIC
codes, captured by the crawler from MCF job detail (`postedCompany.ssicCode2020`) and backfilled
by `scripts/backfill_companies.py` (~14.8k companies, ~2/s). `company_stats` v3 (migration 027)
derives `is_agency`: SSIC 78xxx, or a recruitment-style name (recruit, staffing, headhunt,
employment agency, personnel, human resource, HR, manpower) whose registration is known and is
not a public body (SSIC 72, 84, 85, 86, 91, 94 excluded; names containing "ministry" excluded).
Bare name keywords are never used; CAG companies are never tagged. The earlier heuristic (10+
role families) mislabelled NUS, NTU, A*STAR and Micron and was removed. The checker's card tag
reads the same set via `get_agency_company_keys`, which derives from the view. Companies page v2
(Company, Openings, Hires mainly, per-family median when a family is selected; agencies hidden by
default), profile v2 (registered industry, "1 in N" reposts with the typical-company figure,
repeat postings), dashboard tiles for visitors (Live jobs, New this week, Companies hiring,
Postings tracked) with pipeline counts moved to `/admin`. Reviews: a code-review agent (17
findings, high and medium fixed in 62f2d0c) and a job-seeker agent on production (fixes in
cb2efc1). Spec: `docs/superpowers/specs/2026-11-08-ux-v2-agencies-open-roles-design.md`.

## SGSAL-027 checker shows open roles first

**2026-11-08.** `check_lowball` ranks the 500 nearest postings, puts open ones first and fills with
closed; the percentile pool stays the closest `top_k*5` historical ads with compliant ranges.
Response carries `open_matched`. Verified on production: a Data Analyst check returned 20 closed
cards before, 59 open of 98 after. Copy: "{n} closest ads · {open} open now", "{pct}% match",
ordinal percentiles. Chips became sentences: "Posted N times since Mon YYYY", "Same ad under N
company names", "Also posted directly by X".

## SGSAL-026 companies explorer

**2026-11-08.** First version of the filterable Companies page on a `company_stats` materialised
view (migration 024, refreshed at crawl end after `posting_groups`). Superseded the same day by
SGSAL-028 after review: role-mix bar, repost-rate bar and "Tracked since" removed; the
family-spread agency heuristic replaced.

## SGSAL-025 halfvec index cut-over

**2026-11-08.** `idx_job_embeddings_halfvec`, a `halfvec(768)` HNSW expression index (migration
023), replaced the full-precision index: 719 MB vs 1,910 MB, `job_embeddings` 5.2 GB to 3.3 GB,
database 9.0 GB to 7.1 GB. The post-delete `VACUUM` that had run 9 hours against the old index
was cancelled; after the drop it took 1.5 minutes. Job-side similarity queries must keep the
exact `embedding::halfvec(768) <=> %s::halfvec(768)` expression. Remaining steps in the ticket:
re-embed old-model vectors with v2, role-family routed partitions, cold-tier quantisation.

## SGSAL-024 posting history and one vector per ad

**2026-11-07 to 08.** `jobs.content_hash = posting_key(title, description)` (company excluded)
and `canonical_job_uuid` make every repost share one embedding, one set of LLM fields and one Jev
label. `backfill_posting_keys.py --apply` deleted 255,252 duplicate vectors (627,040 to 371,788
rows). `posting_groups` (materialised view) feeds the repost chips, `/api/jobs/{uuid}/reposts`,
the dashboard's most-reposted table and the company pages. Findings at the time: 45% of all
vectors were exact reposts; 5,753 posting groups span two or more company names. Policy decided
2026-11-07: never prune job rows or expired postings; vectors are deduplicated and compressed
instead. Dashboard summary became canonical-aware (a job is searchable when a vector exists for
it or its canonical posting): 664,978 searchable of 716,225 seen, 371,788 vectors.

## SGSAL-022 Jev role families

**Oct to Nov 2026.** 24 role families and a seniority tier per job via a TypeSafe Jev classifier
through the OpenRouter decisions API, written to `jobs.role_family` / `role_conf` / `tier_conf`;
legacy KMeans/LR classifiers removed. Cleaner model switched to `google/gemma-4-26b-a4b-it` after
a shootout. Backfill is resumable and runs after the daily embed.

## SGSAL-019 hot jobs

**2026-07-01.** `/hot-jobs` surfaces live roles paying above the median of their peer group,
scored post-crawl against a separate `hot_jobs_cluster` (k=23). Salary-baseline and percentage
caps guard against outliers. Shipped the day of the Straits Times feature.

## June 2026 methodology and matching model

- Headline figure is the median (P50) of similar ads; P25/P75 shown for context (2026-05-26,
  2026-06-02).
- Each ad counts as the midpoint of its advertised range; ranges with `max > 2 × min` are excluded
  from the benchmark pool (EP compliance rule), validated against real postings with a recruiter
  contact.
- Salary figures labelled "Monthly base salary (SGD)"; recruiter caveat that posted ranges run
  10 to 20 percent above actual offers.
- Fine-tuned embedding models `NaqibL/bge-base-sgmarket-v1` (2026-06-09, 85% pairwise accuracy)
  and `v2` (2026-06-15, 87.5%, cross-function hard negatives); all embeddings re-indexed
  (2026-06-16). Seniority filter added to the checker.
- Reliability: connection-pool sizing, `SET LOCAL` for `hnsw.ef_search` behind PgBouncer,
  stale-SSL recovery, thundering-herd guard, cache sweeper for a memory leak.

## May 2026 public launch

**2026-05-31.** Rebranded from "SG Salary" to Lowball; `/` and `/lowball` consolidated; Open Graph
previews. A structured security review ran before the repo and site went public and every
blocker it raised was fixed. Companies browse and profile pages, company-name canonicalisation,
and public job-detail pages shipped in the weeks before launch (2026-05-10 to 05-29).

## April 2026 prototype

**2026-04-05.** First commit. Job-description ingestion, embedding pipeline, salary search, daily
crawl, LLM cleaning pass for `min_years_experience`, seniority and canonical skills. Pivoted to
the salary checker as the core surface on 2026-05-16.

---

# Earlier entries (detailed, as written at the time)

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
