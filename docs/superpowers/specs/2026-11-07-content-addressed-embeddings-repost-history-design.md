# Content-addressed embeddings + repost history — design

Ticket: SGSAL-024. Follow-on: SGSAL-025 (halfvec index rebuild runs right after
this ships). Decided with Luqman on 2026-11-07.

## 1. Goal

Store one vector per distinct posting text instead of one per job row, skip the
LLM cleaner / embedder / Jev for reposts at crawl time, and turn the repost
pattern into a user-visible feature: a repost count and dated history (with
salary) on every salary-checker card, plus a dashboard table.

Non-goals: deleting any job row or expired posting (policy: never); grouping
reposts whose title was changed (SGSAL-023); changes to Hot Jobs or the
owner-only matches page; charts or sparklines.

## 2. Decisions already made

| question | decision |
|---|---|
| retention | keep every job row and every expired posting; embeddings are derived and may be deduplicated |
| display unit in the checker | **one card per posting**, showing the latest occurrence, with a repost badge; percentile counts one salary per posting (the latest occurrence's) |
| grouping key | **exact**: normalised title + description. Company is *not* in the key (it is not in the embedded text, so agency reposts are byte-identical vectors). Title variants stay separate postings for now |
| storage model | pointer columns on `jobs` + a materialised view rebuilt at crawl end (Approach A); `job_embeddings` keeps its `job_uuid` key and holds canonical rows only |
| "repost" definition | a new `jobs` row whose key already exists. MCF never reuses an id (0 reactivations in 90 days of run history), so no reactivation log is needed |
| wording | neutral and factual; never "scam". Thresholds for the amber marker are constants to tune later |

## 3. Facts the design relies on (measured 2026-11-07)

- 616,208 jobs with embeddings; 339,129 distinct `(company, description)` texts;
  277,079 vectors (45%) are exact reposts. Dropping company from the key raises
  the dedup rate slightly (70 of 869 sampled identical-vector groups spanned
  company names).
- Identical vector ⇒ same posting in 939/952 sampled groups. Identical text ⇏
  identical vector today (LLM cleaner is non-deterministic; same-model reposts
  sit at median cosine 0.9865). Dedup at ingest therefore also removes
  near-copy padding from the checker's top-500.
- `posted_date` differs from `first_seen_at::date` for 47% of rows and is NULL
  for 1,962 text-less rows → occurrence date = `COALESCE(posted_date,
  (first_seen_at AT TIME ZONE 'UTC')::date)`.
- `company_canonical` is populated for 69k rows only → company grouping uses
  `COALESCE(company_canonical, company_name)`.
- Crawl never re-fetches a known id → a row's salary is "salary as posted that
  time"; edits to a live listing are not captured (accepted).

## 4. Backend

### 4.1 Key

`src/mcf/lib/pipeline/posting_key.py`:

```python
def posting_key(title: str | None, description: str | None) -> str | None:
    """sha256 hex (first 32 chars) of normalised title + description; None if no description."""
    if not description or not description.strip():
        return None
    t = " ".join((title or "").split()).casefold()
    d = " ".join(description.split())
    return hashlib.sha256(f"{t}\n{d}".encode("utf-8")).hexdigest()[:32]
```

Single implementation; the backfill and the crawl both import it. No SQL
re-implementation. Unit tests: whitespace runs, case, leading/trailing space,
emoji in title, NULL/blank description → None, identical inputs → identical key.

### 4.2 Schema (migration `022_posting_key.sql`, also in `ensure_schema()`)

```sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_job_uuid TEXT;
CREATE INDEX IF NOT EXISTS idx_jobs_content_hash
  ON jobs (content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_canonical
  ON jobs (canonical_job_uuid) WHERE canonical_job_uuid IS NOT NULL;
```

Invariants (checked by a smoke test):

- `content_hash IS NULL` ⇔ no description. Such rows are never grouped;
  `canonical_job_uuid = job_uuid` for them.
- Every row with a hash has `canonical_job_uuid` set; the canonical row has
  `canonical_job_uuid = job_uuid`.
- `job_embeddings` contains only rows whose job is canonical
  (`NOT EXISTS (SELECT 1 FROM jobs j WHERE j.job_uuid = e.job_uuid AND j.canonical_job_uuid <> j.job_uuid)`).

### 4.3 Materialised view `posting_groups`

One row per `content_hash` (so ≈ 340k rows now). Built from `jobs` only.

| column | definition |
|---|---|
| `content_hash` | key (unique index → `REFRESH … CONCURRENTLY`) |
| `canonical_job_uuid` | `min(canonical_job_uuid)` (all rows agree) |
| `latest_job_uuid` | the occurrence with the greatest `(is_active, occurrence_date, first_seen_at)` — active preferred |
| `repost_count` | `count(*)` |
| `active_count` | `count(*) FILTER (WHERE is_active)` |
| `first_posted`, `last_posted` | `min/max(occurrence_date)` |
| `reposts_90d`, `reposts_365d` | counts with `occurrence_date >= current_date - 90/365` |
| `distinct_companies` | `count(DISTINCT lower(COALESCE(company_canonical, company_name)))` |
| `latest_salary_min/max` | from the latest occurrence |
| `min_salary_seen`, `max_salary_seen` | `min(salary_min)`, `max(salary_max)` over occurrences with a salary |
| `occurrences` | `jsonb_agg(jsonb_build_object('job_uuid', …, 'date', occurrence_date, 'company', …, 'salary_min', …, 'salary_max', …, 'is_active', …) ORDER BY occurrence_date DESC, first_seen_at DESC)` |

`occurrence_date = COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date)`.

Refresh: `Storage.refresh_posting_groups()` → `REFRESH MATERIALIZED VIEW
CONCURRENTLY posting_groups`, called in `incremental_crawl.py` after
`finish_run`, next to `prune_job_run_status`, non-fatal. Expected 10–30 s now,
~1 min at 2× history. Not refreshed by `--no-embed` vs embed distinction — it
runs on every crawl because grouping happens in Phase 1 regardless.

Rows whose `content_hash IS NULL` are excluded from the view; the API treats a
missing group as `repost_count = 1`.

### 4.4 Storage interface (`base.py` abstract, `PostgresStore` impl)

```python
def find_canonicals(self, hashes: list[str]) -> dict[str, str]
    # hash -> canonical_job_uuid for hashes that already have a canonical row
def link_reposts(self, pairs: list[tuple[str, str]]) -> int
    # (job_uuid, canonical_job_uuid): set pointer + content_hash is already set;
    # copy min_years_experience, llm_fields_json, role_family, role_conf,
    # tier_conf, predicted_tier, role_cluster FROM the canonical WHERE the
    # repost's value IS NULL. One UPDATE ... FROM (VALUES ...) per 500 rows.
def set_content_hashes(self, rows: list[tuple[str, str | None]]) -> None
    # (job_uuid, content_hash) batch write (crawl Phase 1 + backfill)
def get_posting_groups(self, canonical_uuids: list[str]) -> dict[str, dict]
    # canonical_job_uuid -> group facts WITHOUT the occurrences array
def get_posting_history(self, job_uuid: str) -> dict | None
    # resolve any member uuid -> its group incl. occurrences
def get_most_reposted(self, days: int = 365, limit: int = 20) -> list[dict]
def refresh_posting_groups(self) -> None
```

Selection changes:

- `get_active_jobs_without_embeddings()` and the re-embed `--only-unembedded`
  path add `AND (j.canonical_job_uuid IS NULL OR j.canonical_job_uuid = j.job_uuid)`.
- `get_active_jobs_missing_role_family()` / its count add the same predicate
  (reposts receive labels by copy, not by Jev).
- `get_jobs_with_salary_by_uuids()` gains `representative: bool = False`: when
  true the given uuids are canonical uuids and the query joins
  `posting_groups` to return the **latest occurrence's** row plus the group
  facts (`repost_count`, `active_count`, `first_posted`, `last_posted`,
  `reposts_365d`, `distinct_companies`, `min/max_salary_seen`,
  `canonical_job_uuid`). Uuids with no group row fall back to themselves
  with `repost_count = 1`.
- `delete_inactive_job_embeddings()` (no callers, contradicts the policy) is
  removed from the ABC and the store.

### 4.5 Crawl changes (`incremental_crawl.py`, Phase 1)

After the fetch loop and before Phase 1b:

1. `keys = {uuid: posting_key(n.title, n.description)}` for the fetched jobs;
   `store.set_content_hashes(...)`.
2. `canon = store.find_canonicals([k for k in keys.values() if k])`.
3. Walk `fetched` in order. For a job whose key is in `canon` → repost of an
   existing canonical. For a key not in `canon` → this job becomes canonical;
   add it to `canon` so later jobs in the same crawl with the same key link to
   it. Jobs with `key is None` are canonical of themselves.
4. `store.link_reposts(pairs)` for all reposts; self-pointers for canonicals
   (one batch).
5. `fetched = [n for n in fetched if n.job_uuid not in reposts]` before
   `build_texts_parallel`, so reposts skip the cleaner, the embedder and Jev.
6. Log line: `"{n} reposts linked to existing postings (skipped cleaner/embed/Jev)"`;
   `CrawlResult` gains `reposts_linked: int`, surfaced in the Telegram digest.

Edge: the canonical may not have an embedding yet (`--no-embed` crawl, embed
later that day). The repost still points at it; the nightly re-embed embeds the
canonical only. Nothing in the checker breaks meanwhile because the repost
never had its own vector either.

### 4.6 Backfill (`scripts/backfill_posting_keys.py`, resumable, `--dry-run` / `--apply`)

1. Stream `jobs(job_uuid, title, description)` in 5k batches ordered by
   `job_uuid`, compute keys in Python, `set_content_hashes`. Resumable by
   `WHERE content_hash IS NULL AND description IS NOT NULL`.
2. Choose canonicals in SQL, per hash, ranking members by: has a
   `NaqibL/bge-base-sgmarket-v2` embedding → has any embedding → earliest
   `first_seen_at`. `UPDATE jobs SET canonical_job_uuid = …`. Rows with NULL
   hash get `canonical_job_uuid = job_uuid`.
3. Copy LLM fields and Jev labels from canonical to members where NULL
   (`link_reposts` logic, batched). Side effect: fills part of the 1,012
   empty-LLM gap and labels some of the 641k unlabelled expired jobs free.
4. `DELETE FROM job_embeddings` where the job is not canonical, 5k per
   statement with `statement_timeout = 0`, logging rows deleted. Expected
   ≈ 230–280k rows.
5. `CREATE MATERIALIZED VIEW posting_groups …` + unique index; first refresh.
6. Print: groups, members, vectors deleted, fields copied, max repost_count,
   p50/p95 of `reposts_365d` (input for the badge thresholds).
7. **Do not `REINDEX`** here. The HNSW index does not shrink on delete; the
   halfvec index build in SGSAL-025 step 1 replaces it and reclaims the space.
   `VACUUM (ANALYZE) job_embeddings` afterwards reclaims TOAST.

Run order: migration → backfill (dry-run, then apply; ~1 GB egress to stream
descriptions, well inside the plan) → deploy crawl change → SGSAL-025 step 1.
The crawl change must not deploy before the backfill has set canonicals, or
the first crawl would link reposts to nothing; the code treats a missing
canonical as "become canonical", so the failure mode is only a missed dedup,
not an error.

### 4.7 API

- `POST /api/lowball/check` and `/api/salary/search`: unchanged request.
  `_compute_lowball` calls `get_jobs_with_salary_by_uuids(..., representative=True)`
  for both the global and the company-scoped lists. `_build_similar_jobs`
  passes through the group facts. Percentile pool = one salary per returned
  row (already true once the ranked list is per canonical).
  Response adds to each similar job: `canonical_job_uuid`, `repost_count`,
  `active_count`, `first_posted`, `last_posted`, `reposts_365d`,
  `distinct_companies`, `min_salary_seen`, `max_salary_seen`. Also adds
  `total_listings` (sum of repost_count over returned postings) for the
  summary line.
- `GET /api/jobs/{job_uuid}/reposts` (public, response-cached 1 h): the
  group incl. `occurrences`; 404 if the job is unknown; a job with no group
  returns a single-occurrence group.
- `GET /api/dashboard/most-reposted-public?days=365&limit=20` (public,
  cached with the other dashboard endpoints): rows from `get_most_reposted`.
- Cache keys for the two lowball endpoints are unchanged (same inputs); the
  response cache TTL (15 min) already bounds staleness after a refresh.

## 5. Frontend

All calls via `frontend/lib/api.ts`. Types in `frontend/lib/types.ts`.

### 5.1 Types

`SimilarJob` gains: `canonical_job_uuid?: string; repost_count?: number;
active_count?: number; first_posted?: string | null; last_posted?: string |
null; reposts_365d?: number; distinct_companies?: number; min_salary_seen?:
number | null; max_salary_seen?: number | null`. New `PostingOccurrence`
(`job_uuid, date, company, salary_min, salary_max, is_active`) and
`PostingHistory` (group facts + `occurrences: PostingOccurrence[]`).
`LowballResult` gains `total_listings?: number`.

`api.ts`: `getPostingHistory(jobUuid: string): Promise<PostingHistory>` and
`getMostReposted(days = 365, limit = 20)`.

### 5.2 Repost badge (`SimilarJobCard`, chip row after the salary pill)

- Render when `repost_count >= 2`. A `<button aria-expanded>` pill with the
  `Repeat` lucide icon and a chevron.
- Copy: `Reposted {n}× · since {Mon YYYY}` (from `first_posted`).
- Tone: slate by default. **Amber** when `reposts_365d >= REPOST_AMBER_MIN
  (6)` or `distinct_companies >= REPOST_COMPANIES_AMBER_MIN (3)`; copy then
  names the fact: `Reposted {n}× in 12 months` or `Posted under {k} company
  names` (companies takes precedence if both). Constants live in
  `frontend/lib/repost.ts` with the formatting helpers.
- The word "scam" never appears. No red tone.

### 5.3 Posting history panel (inside the card, below the chips)

Opens on badge click; closes on second click. Lazy-loads via SWR with key
`['posting-history', canonical_job_uuid]`; shows a 2-line skeleton while
loading and a one-line "Couldn't load history" on error.

Content, top to bottom:

1. Summary line: `First seen {Mon YYYY} · last {Mon YYYY} · {n} postings ·
   {k} company name(s)` (companies part only when k ≥ 2).
2. Salary movement line (only if ≥ 2 occurrences have a salary):
   `Range moved from {min–max of oldest salaried} to {min–max of newest
   salaried}` when they differ, else `Same range every time`.
3. Occurrence list, newest first: `{Mon D, YYYY} · {company} · {$a – $b/mo |
   No salary listed} · {Active|Closed}`. Rows capped at 8 with a `Show all
   {n}` toggle. Mobile: date and status on line one, company and salary on
   line two.
4. Footnote (muted, text-xs): `Frequent reposting can mean ongoing hiring,
   high turnover or an agency listing. Treat it as a signal, not a verdict.`

### 5.4 Card represents the latest occurrence

No component change needed beyond the badge: the API already returns the
latest occurrence's fields. Historical footer copy becomes
`Historical listing · last posted {Mon YYYY} · salary data still valid for
benchmarking`.

### 5.5 Results summary line

The existing line that counts active roles (`activeCount`) becomes:
`{postings} postings · {active} still open · {total_listings} listings
including reposts` — the third segment only when `total_listings > postings`.

### 5.6 Dashboard

New card "Most reposted roles · last 12 months": table with Title, Company
(or `{k} companies`), Postings, First, Last, Latest range. Fetched via
`getMostReposted`. Below it, one sentence in muted text (the dashboard has no
methodology section today, so this is the first such note): `Each distinct
posting text counts once. Reposts are shown as that posting's history.`

### 5.7 Out of scope (v1)

Hot Jobs cards, matches page, sparkline/chart, title-variant grouping,
per-company repost pages.

## 6. Error handling

- Hash helper never raises; a `None` key simply means "no grouping".
- Crawl: `find_canonicals` / `link_reposts` failures are logged and the batch
  proceeds as if every job were canonical (worst case: one crawl's reposts
  get their own vectors; the next backfill run would fold them). The refresh
  is non-fatal like the prune.
- API: missing group → `repost_count = 1`, no badge. Timeline 404 for unknown
  uuid. Dashboard endpoint returns `[]` if the view does not exist yet
  (pre-migration deploy safety).
- Frontend: badge hidden when fields are absent (older API), so the UI can
  deploy before or after the backend.

## 7. Testing

- `tests/test_posting_key.py`: fixtures listed in 4.1.
- `tests/test_smoke.py` (real Postgres): the three invariants in 4.2; a known
  canonical returns a group from `get_posting_history`;
  `get_jobs_with_salary_by_uuids(representative=True)` returns the latest
  occurrence for a group with ≥ 2 members and `repost_count = 1` for an
  ungrouped uuid.
- `tests/test_crawl_reposts.py` (real Postgres, no external calls): insert a
  canonical job with an embedding and LLM fields via the store, run the Phase
  1 linking function on a `NormalizedJob` with the same text → pointer set,
  fields copied, job excluded from the embed list, no new `job_embeddings`
  row. Clean up in a fixture.
- API: `/api/jobs/{uuid}/reposts` 200 + 404 paths; lowball response carries
  the new fields.
- Frontend: `npm run build` + a manual check of badge, panel, summary line and
  dashboard card on desktop and a phone-width viewport.

## 8. Acceptance (copied to SGSAL-024)

- Invariants in 4.2 hold on production after the backfill.
- Daily crawl log shows `N reposts linked…`; cleaner/embed/Jev counts drop
  accordingly.
- Checker: each posting appears once; badge + panel work; the summary line
  shows the three counts; no "scam" wording anywhere.
- Dashboard: most-reposted table renders; note present.
- `job_embeddings` ≈ 340–400k rows; the halfvec rebuild (SGSAL-025) then
  reports the reclaimed size.

## 9. Open items for later

- Normalised-title grouping (title variants) — measure how much it recovers.
- Threshold tuning from the backfill's `reposts_365d` distribution.
- Whether Hot Jobs should carry the badge.
