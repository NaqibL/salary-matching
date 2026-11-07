# DB performance fixes — from Supabase slow-query log (errors.txt, 2026-07-01)

## Source

`errors.txt` — Supabase Postgres slow-query log (`log_min_duration` / auto_explain output), plus an
earlier FastAPI traceback for `/api/lowball/check` timing out in `get_all_embedded_job_ids_ranked`
(`src/mcf/lib/storage/postgres_store.py:716-741`).

## Findings

1. **Missing index on company lookup filter.** Queries of the shape
   `WHERE company_canonical = 'X' OR (company_canonical IS NULL AND company_name = 'X')`
   (used by the company-tab / distinct-companies-for-autocomplete queries) do a
   **Parallel Seq Scan on jobs** and take **200–454 seconds** each. No index currently covers
   `company_canonical` or `company_name`. This is the same gap already scoped in
   `CLAUDE.md` under "Company dropdown canonicalization."

2. **Dashboard salary-bucket query is slow despite using an index.** The `is_active = TRUE` bucket
   query uses `Index Scan using idx_jobs_active` and still takes **542 seconds** for ~72k rows.
   An index scan at that row count should be milliseconds — this points to the Postgres instance
   being CPU/IO-starved, not a missing-index problem.

3. **Supabase's own internal queries are slow too.** Dashboard/advisor queries (extension list,
   database linter — pure `pg_catalog` metadata lookups) take **36–40 seconds**. Since these
   should return near-instantly regardless of table size, this confirms the whole instance is
   resource-starved, not any specific table/query.

4. **`idle_session_timeout='58s'` is set by Supabase's pooler.** Our app pool
   (`PostgresStore.__init__`, `postgres_store.py:39-47`) keeps `minconn=2` idle connections open
   indefinitely. If the pooler kills an idle connection at 58s and the app hands it out before
   the existing stale-connection probe catches it, the result is
   `psycopg2.OperationalError: SSL connection has been closed unexpectedly` — this matches the
   SSL errors seen on Railway.

5. **Two independent connection pools hit the same DB concurrently.** The API (Railway) and the
   crawl (GitHub Actions, `incremental_crawl.py`) each instantiate their own `PostgresStore`,
   each opening a `ThreadedConnectionPool(maxconn=50)`. Under simultaneous load this can approach
   ~100 connections against Supabase, and the crawl's embedding writes (`upsert_embedding`,
   `postgres_store.py:602-618`) compete with concurrent HNSW ANN reads
   (`get_all_embedded_job_ids_ranked`) for CPU on the same index.

## Candidate fixes

### Code-only (no infra dependency)

- **Add index for company lookups:**
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_company_canonical
    ON jobs (company_canonical);
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_company_name
    ON jobs (company_name) WHERE company_canonical IS NULL;
  ```
  Partial index on `company_name` matches the `OR (company_canonical IS NULL AND ...)` branch
  exactly, keeping it small.

- **Retry once on mid-query connection loss.** `_get_conn()` (`postgres_store.py:76-98`) only
  probes for staleness at checkout. If the pooler kills a connection *during* a query, the error
  propagates straight to a 500 with no retry. Wrap `_cur()` / `_transaction_cur()` to catch a
  connection-closed `OperationalError` once and retry on a fresh connection.

- **Lower pool `minconn` or add a keepalive ping** so idle connections aren't held open past
  Supabase's 58s `idle_session_timeout` — currently `minconn=2` guarantees idle connections that
  are likely already dead from the pooler's side.

### Infra decision (needs Luqman's call, not a code change)

- **Upgrade Supabase compute tier.** The 542s index-scan and 36-40s catalog-query lines are not
  explained by missing indexes — they show the instance itself is CPU/IO starved. This needs a
  paid compute add-on (Supabase Pro + compute size), not code.

- **Consider staggering/throttling crawl writes** relative to API traffic, since the crawl cron
  (02:00 UTC / 10:00 SGT) overlaps with likely daytime SG user traffic, and crawl embedding writes
  contend with API HNSW reads on the same table/index.

## Open questions for the backend agent

- Should the two `PostgresStore` instances (API vs crawl) share a lower `maxconn` ceiling, or
  should the crawl process throttle its own concurrency during known traffic hours?
- Is a response cache on `/api/lowball/check` (already on roadmap in CLAUDE.md) enough to reduce
  read pressure, or does the write-side (embedding upserts during crawl) need its own fix
  (e.g. larger batch size to reduce index-maintenance overhead, or building embeddings on a
  reduced-priority schedule)?
