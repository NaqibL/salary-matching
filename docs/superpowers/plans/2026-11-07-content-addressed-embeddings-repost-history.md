# Content-Addressed Embeddings + Repost History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store one vector per distinct posting text, skip the cleaner/embedder/Jev for reposts at crawl time, and show each posting's repost count and dated salary history on the salary checker and dashboard.

**Architecture:** Two pointer columns on `jobs` (`content_hash`, `canonical_job_uuid`); `job_embeddings` keeps its `job_uuid` key but only holds canonical rows. A materialised view `posting_groups` (one row per hash) is rebuilt at the end of every crawl and feeds the API. The checker's similarity queries still return canonical UUIDs; one join swaps each for its latest occurrence plus group facts.

**Tech Stack:** Python 3.13, FastAPI, psycopg2 + pgvector 0.8 on Supabase Postgres 17, pytest (real DB, no mocks), Next.js 15 + TypeScript + Tailwind + SWR + lucide-react.

**Spec:** `docs/superpowers/specs/2026-11-07-content-addressed-embeddings-repost-history-design.md`

## Global Constraints

- Never delete or modify `jobs` rows; only `job_embeddings` rows of non-canonical jobs are deleted, and only in Task 6 after a dry run and Luqman's go-ahead.
- All DB access goes through the `Storage` ABC (`src/mcf/lib/storage/base.py`) → `PostgresStore`. Routes call `get_store()`, never `PostgresStore` directly.
- All frontend API calls go through `frontend/lib/api.ts`. No `fetch` in components.
- Tests use the real Postgres via `DATABASE_URL` and skip when it is unset. Tests never write rows to the shared Supabase DB (it is also production). Pure logic gets unit tests; DB methods get read-only smoke tests.
- Run Python tests as: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['<path>','-v']))"` (pytest does not load `.env`; plain `pytest` silently skips DB tests). `uv run pytest` is broken on this Windows machine.
- Dev DB == prod DB (one Supabase project). Index creation on `jobs` is done manually with `CREATE INDEX CONCURRENTLY` **before** code that relies on it deploys; `ensure_schema()` only carries `IF NOT EXISTS` versions for fresh DBs.
- Grouping key = normalised **title + description**, company excluded. Hash computed in Python only (`posting_key`), never re-implemented in SQL.
- Copy rules: the word "scam" never appears in UI copy or API strings. Amber marker thresholds are constants `REPOST_AMBER_MIN = 6`, `REPOST_COMPANIES_AMBER_MIN = 3`.
- Occurrence date = `COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date)` (a bare `::date` on timestamptz is not IMMUTABLE and the UTC form matches migration 020).
- Commit after every task with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer. Do not push until Task 11 says so.

---

## File map

| File | Responsibility |
|---|---|
| `src/mcf/lib/pipeline/posting_key.py` (new) | the hash helper + the pure link-planning function |
| `scripts/migrations/022_posting_groups.sql` (new) | columns, indexes, materialised view (manual, CONCURRENTLY) |
| `src/mcf/lib/storage/base.py` | new abstract methods |
| `src/mcf/lib/storage/postgres_store.py` | implementations, `ensure_schema` additions, selection-query changes |
| `src/mcf/lib/pipeline/incremental_crawl.py` | Phase 1 linking + view refresh |
| `scripts/backfill_posting_keys.py` (new) | one-off resumable backfill |
| `src/mcf/api/routes/lowball.py` | representative rows + group fields + `total_listings` |
| `src/mcf/api/routes/jobs.py` | `GET /api/jobs/{job_uuid}/reposts` |
| `src/mcf/api/routes/dashboard.py` | `GET /api/dashboard/most-reposted-public` |
| `frontend/lib/types.ts`, `frontend/lib/api.ts`, `frontend/lib/repost.ts` (new) | types, client calls, badge helpers |
| `frontend/app/api/dashboard/most-reposted/route.ts` (new) | Next.js proxy route |
| `frontend/app/lowball/RepostBadge.tsx` (new), `frontend/app/lowball/PostingHistoryPanel.tsx` (new), `frontend/app/lowball/LowballContent.tsx` | badge, panel, card + summary line |
| `frontend/app/dashboard/MostRepostedTable.tsx` (new), `frontend/app/dashboard/DashboardContent.tsx` | dashboard card |
| `tests/test_posting_key.py` (new), `tests/test_smoke.py` | tests |
| `CLAUDE.md`, `tickets/SGSAL-024.md`, `src/mcf/lib/storage/README.md` | docs |

---

### Task 1: Posting key helper + pure link planner

**Files:**
- Create: `src/mcf/lib/pipeline/posting_key.py`
- Test: `tests/test_posting_key.py`

**Interfaces:**
- Produces: `posting_key(title: str | None, description: str | None) -> str | None` (32 hex chars or None); `plan_repost_links(keys: dict[str, str | None], canon: dict[str, str]) -> tuple[list[tuple[str, str]], set[str]]` returning `(pairs, reposts)` where `pairs` is `(job_uuid, canonical_job_uuid)` for every input job and `reposts` the subset linked to another job. `canon` is mutated in place (new canonicals added) so callers can inspect it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_posting_key.py
"""Posting key (content hash) and repost link planning (SGSAL-024). No network/DB."""

from mcf.lib.pipeline.posting_key import plan_repost_links, posting_key


def test_identical_inputs_give_identical_keys():
    assert posting_key("Data Analyst", "Build dashboards.") == posting_key("Data Analyst", "Build dashboards.")


def test_key_is_32_hex_chars():
    k = posting_key("Data Analyst", "Build dashboards.")
    assert k is not None and len(k) == 32 and int(k, 16) >= 0


def test_whitespace_and_case_in_title_do_not_matter():
    a = posting_key("  Data   Analyst ", "Build dashboards.")
    b = posting_key("data analyst", "Build dashboards.")
    assert a == b


def test_whitespace_runs_in_description_do_not_matter():
    a = posting_key("Data Analyst", "Build\n\n  dashboards.\r\n")
    b = posting_key("Data Analyst", "Build dashboards.")
    assert a == b


def test_description_case_matters():
    assert posting_key("x", "Build dashboards.") != posting_key("x", "build dashboards.")


def test_title_changes_key():
    assert posting_key("Data Analyst", "d") != posting_key("Senior Data Analyst", "d")


def test_company_is_not_part_of_key():
    # signature has no company parameter at all
    import inspect
    assert list(inspect.signature(posting_key).parameters) == ["title", "description"]


def test_blank_description_gives_none():
    assert posting_key("Data Analyst", None) is None
    assert posting_key("Data Analyst", "") is None
    assert posting_key("Data Analyst", "   \n ") is None


def test_emoji_title_is_stable():
    assert posting_key("🔥 Sales Crew", "d") == posting_key("🔥 sales crew", "d")


def test_plan_links_repost_to_existing_canonical():
    keys = {"new1": "h1"}
    canon = {"h1": "old1"}
    pairs, reposts = plan_repost_links(keys, canon)
    assert pairs == [("new1", "old1")]
    assert reposts == {"new1"}


def test_plan_first_of_a_new_key_becomes_canonical_for_the_rest_of_the_batch():
    keys = {"a": "h9", "b": "h9", "c": "h9"}
    pairs, reposts = plan_repost_links(keys, {})
    assert pairs == [("a", "a"), ("b", "a"), ("c", "a")]
    assert reposts == {"b", "c"}


def test_plan_none_key_is_self_canonical_and_never_a_repost():
    pairs, reposts = plan_repost_links({"a": None, "b": None}, {})
    assert pairs == [("a", "a"), ("b", "b")]
    assert reposts == set()


def test_plan_rerun_of_an_already_canonical_job_is_not_a_repost():
    pairs, reposts = plan_repost_links({"a": "h1"}, {"h1": "a"})
    assert pairs == [("a", "a")]
    assert reposts == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_posting_key.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcf.lib.pipeline.posting_key'`

- [ ] **Step 3: Write the implementation**

```python
# src/mcf/lib/pipeline/posting_key.py
"""Content-addressed posting key and repost link planning (SGSAL-024).

The key is a hash of the *text the embedder and LLM cleaner see*: title +
description. Company is deliberately excluded (it is not in the embedded text,
so agency reposts under different company names are byte-identical vectors).
This is the single implementation; the backfill and the crawl both import it.
Never re-implement it in SQL.
"""
from __future__ import annotations

import hashlib


def posting_key(title: str | None, description: str | None) -> str | None:
    """Return a 32-hex-char key for (title, description), or None when there is no description.

    Normalisation: whitespace runs collapsed to one space and trimmed in both
    fields; the title is additionally case-folded (titles vary in casing
    between reposts, descriptions do not).
    """
    if not description or not description.strip():
        return None
    t = " ".join((title or "").split()).casefold()
    d = " ".join(description.split())
    return hashlib.sha256(f"{t}\n{d}".encode("utf-8")).hexdigest()[:32]


def plan_repost_links(
    keys: dict[str, str | None],
    canon: dict[str, str],
) -> tuple[list[tuple[str, str]], set[str]]:
    """Decide, for each job, which job owns its vector.

    Args:
        keys: job_uuid -> posting key (None when the job has no description).
              Iteration order decides which of several new jobs with the same
              key becomes canonical (the first one).
        canon: posting key -> canonical job_uuid already in the DB. Mutated:
               keys that were unknown get the new canonical added.

    Returns:
        (pairs, reposts): ``pairs`` has one ``(job_uuid, canonical_job_uuid)``
        per input job (self-pairs for canonicals); ``reposts`` is the set of
        job_uuids that point at a *different* job and must skip
        cleaner/embed/Jev.
    """
    pairs: list[tuple[str, str]] = []
    reposts: set[str] = set()
    for job_uuid, key in keys.items():
        if key is None:
            pairs.append((job_uuid, job_uuid))
            continue
        owner = canon.get(key)
        if owner is None or owner == job_uuid:
            canon[key] = job_uuid
            pairs.append((job_uuid, job_uuid))
        else:
            pairs.append((job_uuid, owner))
            reposts.add(job_uuid)
    return pairs, reposts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_posting_key.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/mcf/lib/pipeline/posting_key.py tests/test_posting_key.py
git commit -m "feat(SGSAL-024): posting_key content hash + pure repost link planner

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Schema — columns, indexes, materialised view; apply to Supabase

**Files:**
- Create: `scripts/migrations/022_posting_groups.sql`
- Modify: `src/mcf/lib/storage/postgres_store.py` (`ensure_schema`, the `migrations` list ending at line 77)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: columns `jobs.content_hash TEXT`, `jobs.canonical_job_uuid TEXT`; indexes `idx_jobs_content_hash`, `idx_jobs_canonical`; materialised view `posting_groups` with columns `content_hash, canonical_job_uuid, latest_job_uuid, repost_count, active_count, first_posted, last_posted, reposts_90d, reposts_365d, distinct_companies, latest_salary_min, latest_salary_max, min_salary_seen, max_salary_seen, occurrences (jsonb)`; unique index `idx_posting_groups_hash`.

- [ ] **Step 1: Write the failing smoke test**

Append to `tests/test_smoke.py`:

```python
def test_posting_groups_schema_exists(client):
    """SGSAL-024: pointer columns + posting_groups view exist (migration 022)."""
    from mcf.api.deps import get_store

    store = get_store()
    cols = store.describe_columns("jobs")
    assert "content_hash" in cols and "canonical_job_uuid" in cols
    vcols = store.describe_columns("posting_groups")
    for c in ("content_hash", "canonical_job_uuid", "latest_job_uuid", "repost_count",
              "active_count", "first_posted", "last_posted", "reposts_90d", "reposts_365d",
              "distinct_companies", "latest_salary_min", "latest_salary_max",
              "min_salary_seen", "max_salary_seen", "occurrences"):
        assert c in vcols, c
```

`describe_columns` is a tiny new read-only helper; add it in Step 3 (it is also handy for `/schema-diff`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_posting_groups_schema_exists','-v']))"`
Expected: FAIL with `AttributeError: 'PostgresStore' object has no attribute 'describe_columns'`

- [ ] **Step 3: Write the migration file**

```sql
-- scripts/migrations/022_posting_groups.sql
-- SGSAL-024: content-addressed embeddings + repost history.
--
-- jobs.content_hash        = posting_key(title, description) computed in Python
--                            (src/mcf/lib/pipeline/posting_key.py). NULL when no description.
-- jobs.canonical_job_uuid  = the job in the same group that owns the job_embeddings
--                            row / LLM fields / Jev labels (= job_uuid for the canonical).
-- posting_groups           = one row per content_hash, rebuilt at the end of each crawl
--                            (Storage.refresh_posting_groups) and by the backfill.
--
-- Apply to Supabase BY HAND, in this order, outside a transaction (CONCURRENTLY):
--   1) the two ALTER TABLE statements
--   2) the two CREATE INDEX CONCURRENTLY statements
--   3) the CREATE MATERIALIZED VIEW (populates: ~30 s) and its indexes
-- ensure_schema() carries IF NOT EXISTS / non-concurrent copies for fresh DBs only.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_job_uuid TEXT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_content_hash
  ON jobs (content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_jobs_canonical
  ON jobs (canonical_job_uuid) WHERE canonical_job_uuid IS NOT NULL;

CREATE MATERIALIZED VIEW IF NOT EXISTS posting_groups AS
WITH occ AS (
    SELECT job_uuid, content_hash, canonical_job_uuid, is_active, first_seen_at,
           COALESCE(posted_date, (first_seen_at AT TIME ZONE 'UTC')::date) AS occurrence_date,
           lower(COALESCE(company_canonical, company_name)) AS company_key,
           COALESCE(company_canonical, company_name) AS company,
           salary_min, salary_max
      FROM jobs
     WHERE content_hash IS NOT NULL
), ranked AS (
    SELECT occ.*,
           row_number() OVER (PARTITION BY content_hash
                              ORDER BY is_active DESC, occurrence_date DESC, first_seen_at DESC) AS rn
      FROM occ
)
SELECT content_hash,
       min(canonical_job_uuid)                                           AS canonical_job_uuid,
       max(job_uuid)    FILTER (WHERE rn = 1)                            AS latest_job_uuid,
       count(*)::int                                                     AS repost_count,
       (count(*) FILTER (WHERE is_active))::int                          AS active_count,
       min(occurrence_date)                                              AS first_posted,
       max(occurrence_date)                                              AS last_posted,
       (count(*) FILTER (WHERE occurrence_date >= current_date - 90))::int  AS reposts_90d,
       (count(*) FILTER (WHERE occurrence_date >= current_date - 365))::int AS reposts_365d,
       count(DISTINCT company_key)::int                                  AS distinct_companies,
       max(salary_min)  FILTER (WHERE rn = 1)                            AS latest_salary_min,
       max(salary_max)  FILTER (WHERE rn = 1)                            AS latest_salary_max,
       min(salary_min)                                                   AS min_salary_seen,
       max(salary_max)                                                   AS max_salary_seen,
       jsonb_agg(jsonb_build_object(
           'job_uuid', job_uuid, 'date', occurrence_date, 'company', company,
           'salary_min', salary_min, 'salary_max', salary_max, 'is_active', is_active)
           ORDER BY occurrence_date DESC, first_seen_at DESC)            AS occurrences
  FROM ranked
 GROUP BY content_hash;

CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_groups_hash ON posting_groups (content_hash);
CREATE INDEX IF NOT EXISTS idx_posting_groups_canonical ON posting_groups (canonical_job_uuid);
CREATE INDEX IF NOT EXISTS idx_posting_groups_reposts_365d ON posting_groups (reposts_365d DESC);
```

- [ ] **Step 4: Add the `ensure_schema` copies and `describe_columns`**

In `postgres_store.py`, append to the `migrations` list (after the `idx_jobs_role_family_todo` entry, line 76):

```python
            # SGSAL-024 content-addressed embeddings (migration 022). Non-concurrent
            # IF NOT EXISTS copies for fresh DBs; production was migrated by hand.
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS content_hash TEXT",
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS canonical_job_uuid TEXT",
            "CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs (content_hash) WHERE content_hash IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_jobs_canonical ON jobs (canonical_job_uuid) WHERE canonical_job_uuid IS NOT NULL",
            _POSTING_GROUPS_VIEW_SQL,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_posting_groups_hash ON posting_groups (content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_posting_groups_canonical ON posting_groups (canonical_job_uuid)",
            "CREATE INDEX IF NOT EXISTS idx_posting_groups_reposts_365d ON posting_groups (reposts_365d DESC)",
```

Define `_POSTING_GROUPS_VIEW_SQL` as a module-level constant above the class, holding exactly the `CREATE MATERIALIZED VIEW IF NOT EXISTS posting_groups AS ... GROUP BY content_hash` statement from the migration file (copy it verbatim; the two must stay identical).

Add this method next to `get_role_families`:

```python
    def describe_columns(self, relation: str) -> set[str]:
        """Column names of a table or materialised view (read-only helper for tests/schema-diff)."""
        with self._cur() as cur:
            cur.execute(
                """
                SELECT a.attname FROM pg_attribute a
                  JOIN pg_class c ON c.oid = a.attrelid
                  JOIN pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public' AND c.relname = %s
                   AND a.attnum > 0 AND NOT a.attisdropped
                """,
                [relation],
            )
            return {r[0] for r in cur.fetchall()}
```

and in `base.py`, under the retention section, a non-abstract default:

```python
    def describe_columns(self, relation: str) -> set[str]:
        """Column names of a table/view. Used by tests and /schema-diff."""
        raise NotImplementedError
```

- [ ] **Step 5: Apply the migration to Supabase by hand**

Run from the repo root (each statement separately, autocommit; the view takes ~30 s on the Small instance):

```bash
uv run python - <<'EOF'
from dotenv import load_dotenv; load_dotenv('.env')
import os, re, time, psycopg2
sql = open('scripts/migrations/022_posting_groups.sql', encoding='utf-8').read()
stmts = [s.strip() for s in re.split(r';\s*\n', re.sub(r'--[^\n]*', '', sql)) if s.strip()]
c = psycopg2.connect(os.environ['DATABASE_URL']); c.autocommit = True; cur = c.cursor()
cur.execute("SET statement_timeout = 0")
for s in stmts:
    t = time.time(); cur.execute(s); print(f"{time.time()-t:5.1f}s  {s[:70]}...")
EOF
```

Expected: 9 statements succeed; the view statement prints ~30 s. Then verify:

```bash
uv run python - <<'EOF'
from dotenv import load_dotenv; load_dotenv('.env')
import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL']); cur = c.cursor()
cur.execute("select count(*) from posting_groups"); print("groups:", cur.fetchone())
cur.execute("select indexname from pg_indexes where tablename in ('jobs','posting_groups') and indexname like 'idx_%posting%' or indexname in ('idx_jobs_content_hash','idx_jobs_canonical')"); print(cur.fetchall())
EOF
```

Expected: `groups: (0,)` (no hashes yet) and the five index names.

- [ ] **Step 6: Run the smoke test to verify it passes**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_posting_groups_schema_exists','-v']))"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/migrations/022_posting_groups.sql src/mcf/lib/storage/postgres_store.py src/mcf/lib/storage/base.py tests/test_smoke.py
git commit -m "feat(SGSAL-024): migration 022 — content_hash/canonical_job_uuid columns + posting_groups view

Applied to Supabase by hand (CONCURRENTLY); ensure_schema carries IF NOT EXISTS copies.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Storage write methods for linking (`set_content_hashes`, `find_canonicals`, `link_reposts`, `refresh_posting_groups`)

**Files:**
- Modify: `src/mcf/lib/storage/base.py` (add abstract methods after `get_jobs_with_salary_by_uuids`, ~line 520)
- Modify: `src/mcf/lib/storage/postgres_store.py` (add after `update_llm_extracted_fields_batch`, ~line 312)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces:
  - `set_content_hashes(self, rows: list[tuple[str, str | None]]) -> None`
  - `find_canonicals(self, hashes: list[str]) -> dict[str, str]` — only rows with `canonical_job_uuid = job_uuid`
  - `link_reposts(self, pairs: list[tuple[str, str]]) -> int` — sets pointer, copies NULL fields from the canonical, returns rows updated
  - `refresh_posting_groups(self) -> None`

- [ ] **Step 1: Write the failing smoke test (read-only)**

Append to `tests/test_smoke.py`:

```python
def test_find_canonicals_is_read_only_and_shaped(client):
    """SGSAL-024: unknown hashes return {} and the method exists on the Storage ABC."""
    from mcf.api.deps import get_store
    from mcf.lib.storage.base import Storage

    store = get_store()
    assert callable(getattr(Storage, "find_canonicals"))
    assert callable(getattr(Storage, "link_reposts"))
    assert callable(getattr(Storage, "set_content_hashes"))
    assert callable(getattr(Storage, "refresh_posting_groups"))
    assert store.find_canonicals(["0" * 32, "f" * 32]) == {}
    assert store.find_canonicals([]) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_find_canonicals_is_read_only_and_shaped','-v']))"`
Expected: FAIL with `AttributeError: type object 'Storage' has no attribute 'find_canonicals'`

- [ ] **Step 3: Add the abstract methods to `base.py`**

Insert after the `get_jobs_with_salary_by_uuids` docstring block:

```python
    # === Posting groups / reposts (SGSAL-024) ===

    @abstractmethod
    def set_content_hashes(self, rows: list[tuple[str, str | None]]) -> None:
        """Write (job_uuid, content_hash) pairs. content_hash comes from
        ``mcf.lib.pipeline.posting_key.posting_key`` and is None for text-less jobs."""

    @abstractmethod
    def find_canonicals(self, hashes: list[str]) -> dict[str, str]:
        """Map content_hash -> canonical job_uuid for hashes that already have a
        canonical row (``canonical_job_uuid = job_uuid``). Unknown hashes are absent."""

    @abstractmethod
    def link_reposts(self, pairs: list[tuple[str, str]]) -> int:
        """Set ``canonical_job_uuid`` for each (job_uuid, canonical_job_uuid) pair and
        copy LLM fields + Jev labels from the canonical where the job's are NULL.
        Self-pairs are allowed (they only set the pointer). Returns rows updated."""

    @abstractmethod
    def refresh_posting_groups(self) -> None:
        """REFRESH MATERIALIZED VIEW CONCURRENTLY posting_groups. Call at crawl end."""
```

- [ ] **Step 4: Implement in `postgres_store.py`**

```python
    # === Posting groups / reposts (SGSAL-024) ===

    def set_content_hashes(self, rows: list[tuple[str, str | None]]) -> None:
        if not rows:
            return
        with self._cur() as cur:
            execute_values(
                cur,
                """
                UPDATE jobs AS j SET content_hash = v.content_hash
                FROM (VALUES %s) AS v(job_uuid, content_hash)
                WHERE j.job_uuid = v.job_uuid
                """,
                rows,
                template="(%s, %s::text)",
                page_size=500,
            )

    def find_canonicals(self, hashes: list[str]) -> dict[str, str]:
        if not hashes:
            return {}
        with self._cur() as cur:
            cur.execute(
                """
                SELECT content_hash, job_uuid FROM jobs
                 WHERE content_hash = ANY(%s) AND canonical_job_uuid = job_uuid
                """,
                [list(hashes)],
            )
            return {r[0]: r[1] for r in cur.fetchall()}

    def link_reposts(self, pairs: list[tuple[str, str]]) -> int:
        if not pairs:
            return 0
        updated = 0
        with self._cur() as cur:
            for i in range(0, len(pairs), 500):
                execute_values(
                    cur,
                    """
                    UPDATE jobs AS j
                       SET canonical_job_uuid   = v.canonical,
                           min_years_experience = COALESCE(j.min_years_experience, c.min_years_experience),
                           llm_fields_json      = COALESCE(j.llm_fields_json, c.llm_fields_json),
                           role_family          = COALESCE(j.role_family, c.role_family),
                           role_cluster         = COALESCE(j.role_cluster, c.role_cluster),
                           predicted_tier       = COALESCE(j.predicted_tier, c.predicted_tier),
                           role_conf            = COALESCE(j.role_conf, c.role_conf),
                           tier_conf            = COALESCE(j.tier_conf, c.tier_conf)
                      FROM (VALUES %s) AS v(job_uuid, canonical)
                      JOIN jobs c ON c.job_uuid = v.canonical
                     WHERE j.job_uuid = v.job_uuid
                    """,
                    pairs[i : i + 500],
                    template="(%s, %s)",
                    page_size=500,
                )
                updated += cur.rowcount or 0
        return updated

    def refresh_posting_groups(self) -> None:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY posting_groups")
```

Note on `execute_values` with a `JOIN` after the `VALUES` clause: the `%s` placeholder is substituted by the VALUES rows exactly as in `update_llm_extracted_fields_batch`; the `JOIN jobs c` works because `FROM (VALUES …) AS v JOIN jobs c` is a single FROM item.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_find_canonicals_is_read_only_and_shaped','-v']))"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/mcf/lib/storage/base.py src/mcf/lib/storage/postgres_store.py tests/test_smoke.py
git commit -m "feat(SGSAL-024): Storage methods to hash, find canonicals, link reposts, refresh posting_groups

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Storage read methods for groups + selection changes

**Files:**
- Modify: `src/mcf/lib/storage/base.py`
- Modify: `src/mcf/lib/storage/postgres_store.py` (`get_jobs_with_salary_by_uuids` ~line 2221, `get_active_jobs_without_embeddings` ~1075, `get_active_jobs_missing_role_family` ~895, `count_active_jobs_missing_role_family` ~919, `get_job_uuids_with_salary_filter` ~822, `get_company_jobs_ranked` ~2285, remove `delete_inactive_job_embeddings` ~1733)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces:
  - `get_jobs_with_salary_by_uuids(job_uuids, *, compliant_ranges_only=False, representative=False, company_name: str | None = None)`; when `representative=True` the input UUIDs are canonical UUIDs and each returned dict has the usual job columns **of the latest occurrence** plus `canonical_job_uuid, repost_count, active_count, first_posted, last_posted, reposts_365d, distinct_companies, min_salary_seen, max_salary_seen`. With `company_name`, the latest occurrence is chosen among members at that company.
  - `get_posting_history(job_uuid: str) -> dict | None` — the group row (incl. `occurrences`) for any member uuid.
  - `get_most_reposted(days: int = 365, limit: int = 20) -> list[dict]` — rows `{canonical_job_uuid, title, company, distinct_companies, repost_count, reposts_in_window, first_posted, last_posted, latest_salary_min, latest_salary_max}`; `days` must be 90 or 365.
  - `active_canonical_uuids() -> set[str]` — `COALESCE(canonical_job_uuid, job_uuid)` of active jobs.
  - `get_job_uuids_with_salary_filter` now returns canonical uuids.
  - `get_active_jobs_without_embeddings`, `get_active_jobs_missing_role_family`, `count_active_jobs_missing_role_family` exclude reposts.
  - `delete_inactive_job_embeddings` removed from ABC and store.

- [ ] **Step 1: Write the failing smoke tests**

Append to `tests/test_smoke.py`:

```python
def test_representative_lookup_falls_back_to_self_for_ungrouped_uuid(client):
    """SGSAL-024: a uuid with no posting group returns itself with repost_count 1."""
    from mcf.api.deps import get_store

    store = get_store()
    # any embedded job; before the backfill none are grouped, after it the
    # canonical returns itself or its latest occurrence — both satisfy the shape checks.
    uuids = [u for u, _, _ in store.get_all_embedded_job_ids_ranked([0.0] * 768, limit=5)][:1]
    if not uuids:
        pytest.skip("no embeddings")
    rows = store.get_jobs_with_salary_by_uuids(uuids, representative=True)
    assert len(rows) == 1
    r = rows[0]
    for k in ("job_uuid", "title", "salary_min", "salary_max", "is_active", "canonical_job_uuid",
              "repost_count", "active_count", "reposts_365d", "distinct_companies"):
        assert k in r, k
    assert r["canonical_job_uuid"] == uuids[0]
    assert r["repost_count"] >= 1


def test_posting_history_unknown_uuid_is_none(client):
    from mcf.api.deps import get_store

    assert get_store().get_posting_history("no-such-job") is None


def test_most_reposted_shape(client):
    from mcf.api.deps import get_store

    rows = get_store().get_most_reposted(days=365, limit=5)
    assert isinstance(rows, list)
    for r in rows:
        assert set(r) >= {"canonical_job_uuid", "title", "company", "repost_count",
                          "reposts_in_window", "first_posted", "last_posted"}


def test_legacy_delete_inactive_embeddings_is_gone(client):
    from mcf.lib.storage.base import Storage

    assert not hasattr(Storage, "delete_inactive_job_embeddings")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py','-k','representative or posting_history or most_reposted or legacy_delete','-v']))"`
Expected: 4 FAIL (`TypeError: ... unexpected keyword argument 'representative'`, `AttributeError`, `AttributeError`, `AssertionError`)

- [ ] **Step 3: Update the ABC**

In `base.py`: change the signature of `get_jobs_with_salary_by_uuids` to

```python
    @abstractmethod
    def get_jobs_with_salary_by_uuids(
        self,
        job_uuids: list[str],
        *,
        compliant_ranges_only: bool = False,
        representative: bool = False,
        company_name: str | None = None,
    ) -> list[dict]:
        """Return job rows (title, company_name, location, job_url, salary_min/max,
        last_seen_at, is_active, description, min_years_experience, llm_fields_json).

        Args:
            job_uuids: UUIDs to fetch. With ``representative=True`` these are
                *canonical* UUIDs (what the similarity queries return).
            compliant_ranges_only: drop rows where salary_max > 2 * salary_min
                (benchmark pools only, never display cards). NULL bounds are kept.
            representative: return the group's **latest occurrence** (active
                preferred) instead of the canonical row, plus the group facts
                ``canonical_job_uuid, repost_count, active_count, first_posted,
                last_posted, reposts_365d, distinct_companies, min_salary_seen,
                max_salary_seen``. UUIDs without a group return themselves with
                ``repost_count = 1``.
            company_name: with ``representative=True``, pick the latest occurrence
                among members at this company (company tab of the checker).
        """
```

Add after `refresh_posting_groups`:

```python
    @abstractmethod
    def get_posting_history(self, job_uuid: str) -> dict | None:
        """The posting group (incl. ``occurrences`` list) that ``job_uuid`` belongs to, or None."""

    @abstractmethod
    def get_most_reposted(self, days: int = 365, limit: int = 20) -> list[dict]:
        """Posting groups ordered by reposts in the window (``days`` is 90 or 365)."""

    @abstractmethod
    def active_canonical_uuids(self) -> set[str]:
        """``COALESCE(canonical_job_uuid, job_uuid)`` of every active job (checker gates)."""
```

Delete the `delete_inactive_job_embeddings` abstract method from `base.py`.

- [ ] **Step 4: Implement in `postgres_store.py`**

Replace `get_jobs_with_salary_by_uuids`:

```python
    _JOB_SALARY_COLS = (
        "job_uuid, title, company_name, location, job_url, salary_min, salary_max, "
        "last_seen_at, is_active, description, min_years_experience, llm_fields_json"
    )

    def get_jobs_with_salary_by_uuids(
        self,
        job_uuids: list[str],
        *,
        compliant_ranges_only: bool = False,
        representative: bool = False,
        company_name: str | None = None,
    ) -> list[dict]:
        if not job_uuids:
            return []
        # EP compliance filter: salary_max must be <= 2 * salary_min.
        # Rows where either bound is NULL are always kept (no salary info to disqualify).
        compliance_clause = (
            " AND (rep.salary_min IS NULL OR rep.salary_max IS NULL OR rep.salary_max <= 2 * rep.salary_min)"
            if compliant_ranges_only
            else ""
        )
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            if not representative:
                cols = ", ".join(f"rep.{c.strip()}" for c in self._JOB_SALARY_COLS.split(","))
                cur.execute(
                    f"SELECT {cols} FROM jobs rep WHERE rep.job_uuid = ANY(%s){compliance_clause}",
                    (job_uuids,),
                )
            else:
                cols = ", ".join(f"rep.{c.strip()}" for c in self._JOB_SALARY_COLS.split(","))
                if company_name is None:
                    rep_pick = "COALESCE(pg.latest_job_uuid, c.job_uuid)"
                    company_params: tuple = ()
                    company_lateral = ""
                else:
                    # Latest member *at this company*; falls back to the group's latest.
                    company_lateral = """
                      LEFT JOIN LATERAL (
                          SELECT m.job_uuid FROM jobs m
                           WHERE m.content_hash = c.content_hash
                             AND (m.company_canonical = %s
                                  OR (m.company_canonical IS NULL AND m.company_name = %s))
                           ORDER BY m.is_active DESC,
                                    COALESCE(m.posted_date, (m.first_seen_at AT TIME ZONE 'UTC')::date) DESC,
                                    m.first_seen_at DESC
                           LIMIT 1
                      ) cm ON TRUE
                    """
                    rep_pick = "COALESCE(cm.job_uuid, pg.latest_job_uuid, c.job_uuid)"
                    company_params = (company_name, company_name)
                cur.execute(
                    f"""
                    SELECT {cols},
                           c.job_uuid AS canonical_job_uuid,
                           COALESCE(pg.repost_count, 1) AS repost_count,
                           COALESCE(pg.active_count, CASE WHEN c.is_active THEN 1 ELSE 0 END) AS active_count,
                           pg.first_posted, pg.last_posted,
                           COALESCE(pg.reposts_365d, 1) AS reposts_365d,
                           COALESCE(pg.distinct_companies, 1) AS distinct_companies,
                           pg.min_salary_seen, pg.max_salary_seen
                      FROM jobs c
                      LEFT JOIN posting_groups pg ON pg.content_hash = c.content_hash
                      {company_lateral}
                      JOIN jobs rep ON rep.job_uuid = {rep_pick}
                     WHERE c.job_uuid = ANY(%s){compliance_clause}
                    """,
                    (*company_params, job_uuids),
                )
            cols_out = [d[0] for d in cur.description]
            return [dict(zip(cols_out, row)) for row in cur.fetchall()]
```

Add the group readers next to `find_canonicals`:

```python
    def get_posting_history(self, job_uuid: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT pg.content_hash, pg.canonical_job_uuid, pg.latest_job_uuid, pg.repost_count,
                       pg.active_count, pg.first_posted, pg.last_posted, pg.reposts_90d,
                       pg.reposts_365d, pg.distinct_companies, pg.latest_salary_min,
                       pg.latest_salary_max, pg.min_salary_seen, pg.max_salary_seen, pg.occurrences,
                       c.title
                  FROM jobs j
                  JOIN posting_groups pg ON pg.content_hash = j.content_hash
                  JOIN jobs c ON c.job_uuid = pg.latest_job_uuid
                 WHERE j.job_uuid = %s
                """,
                [job_uuid],
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def get_most_reposted(self, days: int = 365, limit: int = 20) -> list[dict]:
        col = "reposts_90d" if int(days) == 90 else "reposts_365d"
        with self._cur() as cur:
            cur.execute(
                f"""
                SELECT pg.canonical_job_uuid, c.title,
                       COALESCE(c.company_canonical, c.company_name) AS company,
                       pg.distinct_companies, pg.repost_count, pg.{col} AS reposts_in_window,
                       pg.first_posted, pg.last_posted, pg.latest_salary_min, pg.latest_salary_max
                  FROM posting_groups pg
                  JOIN jobs c ON c.job_uuid = pg.latest_job_uuid
                 WHERE pg.{col} >= 2
                 ORDER BY pg.{col} DESC, pg.repost_count DESC, pg.last_posted DESC
                 LIMIT %s
                """,
                [int(limit)],
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def active_canonical_uuids(self) -> set[str]:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute("SELECT DISTINCT COALESCE(canonical_job_uuid, job_uuid) FROM jobs WHERE is_active = TRUE")
            return {r[0] for r in cur.fetchall()}
```

Selection changes (exact edits):

1. `get_active_jobs_without_embeddings`: change the WHERE to
   `" WHERE j.is_active = TRUE AND e.job_uuid IS NULL AND (j.canonical_job_uuid IS NULL OR j.canonical_job_uuid = j.job_uuid)"`.
2. `get_active_jobs_missing_role_family` and `count_active_jobs_missing_role_family`: add
   `AND (canonical_job_uuid IS NULL OR canonical_job_uuid = job_uuid)` after the title/description predicate in both queries (keep them identical, the comment there explains why).
3. `get_job_uuids_with_salary_filter`: change the SELECT to
   `f"SELECT DISTINCT COALESCE(canonical_job_uuid, job_uuid) FROM jobs WHERE {' AND '.join(conditions)}"`.
4. `get_company_jobs_ranked`: replace the body's SQL so the company match is on **members** and the vector comes from the canonical:

```python
                """
                SELECT c.job_uuid, (e.embedding <=> %s::vector) AS distance, c.last_seen_at
                  FROM (
                      SELECT DISTINCT COALESCE(j.canonical_job_uuid, j.job_uuid) AS cu
                        FROM jobs j
                       WHERE j.company_canonical = %s
                          OR (j.company_canonical IS NULL AND j.company_name = %s)
                          OR j.company_canonical = (
                              SELECT canonical_name FROM company_aliases
                               WHERE raw_name = %s AND canonical_name IS NOT NULL
                               LIMIT 1
                          )
                  ) m
                  JOIN job_embeddings e ON e.job_uuid = m.cu AND e.embedding IS NOT NULL
                  JOIN jobs c ON c.job_uuid = m.cu
                 ORDER BY distance ASC
                 LIMIT %s
                """,
                [emb_str, company_name, company_name, company_name, limit],
```

5. Delete the whole `delete_inactive_job_embeddings` method.

- [ ] **Step 5: Run the tests**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py','-v']))"`
Expected: all pass (incl. the 4 new ones; `test_most_reposted_shape` passes with an empty list until the backfill runs).

- [ ] **Step 6: Commit**

```bash
git add src/mcf/lib/storage/base.py src/mcf/lib/storage/postgres_store.py tests/test_smoke.py
git commit -m "feat(SGSAL-024): representative lookup, posting history, most-reposted; canonical-only selections

Removes the uncalled delete_inactive_job_embeddings (contradicts keep-all-history policy).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Crawl Phase 1 — link reposts, skip cleaner/embed/Jev, refresh the view

**Files:**
- Modify: `src/mcf/lib/pipeline/incremental_crawl.py` (dataclass line 59-65; after the Phase 1 fetch loop ~line 186; finish block after `prune_job_run_status` ~line 290)
- Create: `src/mcf/lib/pipeline/reposts.py`
- Test: `tests/test_posting_key.py` (pure logic already covered) + a fake-store unit test in `tests/test_reposts_link.py`

**Interfaces:**
- Consumes: `posting_key`, `plan_repost_links` (Task 1); `set_content_hashes`, `find_canonicals`, `link_reposts`, `refresh_posting_groups` (Task 3).
- Produces: `link_reposts_for_batch(store, fetched: Sequence[NormalizedJob]) -> set[str]` (uuids to skip); `IncrementalCrawlResult.reposts_linked: int`.

- [ ] **Step 1: Write the failing unit test with a minimal fake store**

```python
# tests/test_reposts_link.py
"""Crawl-side repost linking (SGSAL-024). Uses an in-memory fake store — no DB, no network."""

from mcf.lib.pipeline.reposts import link_reposts_for_batch
from mcf.lib.sources.base import NormalizedJob


class FakeStore:
    def __init__(self, canonicals: dict[str, str]):
        self._canon = canonicals
        self.hashes: list[tuple[str, str | None]] = []
        self.pairs: list[tuple[str, str]] = []

    def set_content_hashes(self, rows):
        self.hashes.extend(rows)

    def find_canonicals(self, hashes):
        return {h: u for h, u in self._canon.items() if h in hashes}

    def link_reposts(self, pairs):
        self.pairs.extend(pairs)
        return len(pairs)


def _job(uuid: str, title: str, desc: str | None) -> NormalizedJob:
    return NormalizedJob(source_id="mcf", external_id=uuid, title=title, company_name="ACME",
                         location=None, job_url=None, skills=[], description=desc)


def test_repost_of_existing_posting_is_skipped_and_linked():
    from mcf.lib.pipeline.posting_key import posting_key
    old_key = posting_key("Data Analyst", "Build dashboards.")
    store = FakeStore({old_key: "old-1"})
    new = _job("new-1", "data analyst", "Build  dashboards.")
    skip = link_reposts_for_batch(store, [new])
    assert skip == {"new-1"}
    assert store.pairs == [("new-1", "old-1")]
    assert store.hashes == [("new-1", old_key)]


def test_two_new_copies_in_one_batch_share_the_first():
    store = FakeStore({})
    a, b = _job("a", "Chef", "Cook."), _job("b", "Chef", "Cook.")
    skip = link_reposts_for_batch(store, [a, b])
    assert skip == {"b"}
    assert store.pairs == [("a", "a"), ("b", "a")]


def test_textless_job_is_never_skipped():
    store = FakeStore({})
    skip = link_reposts_for_batch(store, [_job("x", "Chef", None)])
    assert skip == set()
    assert store.pairs == [("x", "x")]
    assert store.hashes == [("x", None)]


def test_store_failure_degrades_to_no_skips(capsys):
    class Broken(FakeStore):
        def find_canonicals(self, hashes):
            raise RuntimeError("db down")
    store = Broken({})
    skip = link_reposts_for_batch(store, [_job("a", "Chef", "Cook.")])
    assert skip == set()
    assert "repost linking failed" in capsys.readouterr().out
```

`NormalizedJob.job_uuid` (`src/mcf/lib/sources/base.py:109`) returns the bare `external_id` when `source_id == "mcf"`, which the fixture uses, so the literal uuids in the assertions are correct.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_reposts_link.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcf.lib.pipeline.reposts'`

- [ ] **Step 3: Implement `reposts.py`**

```python
# src/mcf/lib/pipeline/reposts.py
"""Crawl Phase 1 helper: link freshly fetched jobs to existing postings (SGSAL-024).

A repost (same title + description as a job we already hold) gets
``canonical_job_uuid`` pointed at that job, inherits its LLM fields and Jev
labels, and is dropped from the embed list so the crawl does not pay for the
cleaner, the embedder or Jev again. Any storage failure degrades to "nothing
skipped" — the crawl then behaves exactly as before this feature.
"""
from __future__ import annotations

from typing import Sequence

from mcf.lib.pipeline.posting_key import plan_repost_links, posting_key
from mcf.lib.sources.base import NormalizedJob
from mcf.lib.storage.base import Storage


def link_reposts_for_batch(store: Storage, fetched: Sequence[NormalizedJob]) -> set[str]:
    """Return the job_uuids that are reposts and must skip cleaner/embed/Jev."""
    if not fetched:
        return set()
    keys = {n.job_uuid: posting_key(n.title, n.description) for n in fetched}
    try:
        store.set_content_hashes(list(keys.items()))
        hashes = sorted({k for k in keys.values() if k})
        canon = store.find_canonicals(hashes) if hashes else {}
        pairs, reposts = plan_repost_links(keys, canon)
        store.link_reposts(pairs)
    except Exception as e:  # noqa: BLE001 — never let bookkeeping abort a crawl
        print(f"Warning: repost linking failed, embedding every job this run: {e}")
        return set()
    if reposts:
        print(f"{len(reposts)} reposts linked to existing postings (skipped cleaner/embed/Jev)")
    return reposts
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_reposts_link.py -v`
Expected: 4 passed

- [ ] **Step 5: Wire it into the crawl**

In `incremental_crawl.py`:

a) dataclass:

```python
@dataclass(frozen=True)
class IncrementalCrawlResult:
    run: RunStats
    total_seen: int
    added: list[str]
    maintained: list[str]
    removed: list[str]
    reposts_linked: int = 0
```

b) import, next to the other pipeline imports: `from mcf.lib.pipeline.reposts import link_reposts_for_batch`

c) right after the Phase 1 fetch loop (after the last `store.upsert_new_job_detail(...)` call, before the `# Phase 1b` comment), add:

```python
            # Phase 1a: reposts (same title + description as a posting we already
            # hold) link to the existing canonical and skip the expensive steps.
            repost_uuids = link_reposts_for_batch(store, fetched)
            fetched = [n for n in fetched if n.job_uuid not in repost_uuids]
```

`reposts_linked = len(repost_uuids)` must be defined even when `added` is empty: initialise `repost_uuids: set[str] = set()` just before `if added:`.

d) in the finish block, after the `prune_job_run_status` try/except:

```python
        # posting_groups feeds the repost badges / dashboard (SGSAL-024). Non-fatal.
        try:
            store.refresh_posting_groups()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: posting_groups refresh failed, skipping: {e}")
```

e) pass `reposts_linked=len(repost_uuids)` into the final `IncrementalCrawlResult(...)`.

- [ ] **Step 6: Lint + run the pipeline-adjacent tests**

Run: `uv run ruff check src/mcf/lib/pipeline tests/test_reposts_link.py tests/test_posting_key.py` → Expected: no new findings (E402/F841 pre-existing elsewhere are not in these files).
Run: `uv run python -m pytest tests/test_reposts_link.py tests/test_posting_key.py -v` → Expected: 17 passed.

- [ ] **Step 7: Commit**

```bash
git add src/mcf/lib/pipeline/reposts.py src/mcf/lib/pipeline/incremental_crawl.py tests/test_reposts_link.py
git commit -m "feat(SGSAL-024): crawl links reposts to existing postings and skips cleaner/embed/Jev for them

Refreshes posting_groups at crawl end (non-fatal).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Backfill script (hash → canonicals → copy fields → delete duplicate vectors → refresh)

**Files:**
- Create: `scripts/backfill_posting_keys.py`
- Modify: `src/mcf/lib/storage/base.py`, `src/mcf/lib/storage/postgres_store.py` (four backfill-only methods)
- Test: `tests/test_smoke.py` (ABC presence only; the script is exercised by its dry run)

**Interfaces:**
- Consumes: `posting_key`, `set_content_hashes`, `refresh_posting_groups`.
- Produces store methods:
  - `iter_jobs_needing_hash(after_uuid: str, limit: int) -> list[tuple[str, str | None, str]]` — `(job_uuid, title, description)` with `content_hash IS NULL AND btrim(description) <> ''`, keyset by `job_uuid`.
  - `assign_canonicals() -> int` — fills `canonical_job_uuid` for all rows where it is NULL.
  - `copy_fields_from_canonicals() -> int` — NULL-filling copy for non-canonical members.
  - `noncanonical_embedded_uuids() -> list[str]` and `delete_embeddings_by_uuids(uuids: list[str]) -> int`.
  - `posting_group_stats() -> dict` — `{groups, members, max_repost_count, p50_reposts_365d, p95_reposts_365d}`.

- [ ] **Step 1: Write the failing ABC-presence test**

Append to `tests/test_smoke.py`:

```python
def test_backfill_storage_methods_exist(client):
    from mcf.lib.storage.base import Storage

    for name in ("iter_jobs_needing_hash", "assign_canonicals", "copy_fields_from_canonicals",
                 "noncanonical_embedded_uuids", "delete_embeddings_by_uuids", "posting_group_stats"):
        assert callable(getattr(Storage, name)), name
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_backfill_storage_methods_exist','-v']))"`
Expected: FAIL `AttributeError ... iter_jobs_needing_hash`

- [ ] **Step 3: Add the abstract methods (`base.py`, after `active_canonical_uuids`)**

```python
    # --- SGSAL-024 backfill helpers (scripts/backfill_posting_keys.py) ---

    @abstractmethod
    def iter_jobs_needing_hash(self, after_uuid: str, limit: int) -> list[tuple[str, str | None, str]]:
        """(job_uuid, title, description) for jobs with a non-blank description and no
        content_hash yet, job_uuid > after_uuid, ordered by job_uuid."""

    @abstractmethod
    def assign_canonicals(self) -> int:
        """Set canonical_job_uuid where NULL: per hash prefer an existing canonical, then a
        v2-embedded row, then any embedded row, then the earliest seen. Text-less rows
        point at themselves. Returns rows updated."""

    @abstractmethod
    def copy_fields_from_canonicals(self) -> int:
        """For non-canonical members, fill NULL LLM fields / Jev labels from the canonical."""

    @abstractmethod
    def noncanonical_embedded_uuids(self) -> list[str]:
        """job_uuids that have an embedding but are not their group's canonical."""

    @abstractmethod
    def delete_embeddings_by_uuids(self, uuids: list[str]) -> int:
        """Delete job_embeddings rows for the given uuids (batched by caller). Returns rows deleted."""

    @abstractmethod
    def posting_group_stats(self) -> dict:
        """{groups, members, max_repost_count, p50_reposts_365d, p95_reposts_365d} from posting_groups."""
```

- [ ] **Step 4: Implement in `postgres_store.py` (after `active_canonical_uuids`)**

```python
    # --- SGSAL-024 backfill helpers ---

    def iter_jobs_needing_hash(self, after_uuid: str, limit: int) -> list[tuple[str, str | None, str]]:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(
                """
                SELECT job_uuid, title, description FROM jobs
                 WHERE job_uuid > %s AND content_hash IS NULL
                   AND description IS NOT NULL AND btrim(description) <> ''
                 ORDER BY job_uuid LIMIT %s
                """,
                [after_uuid, int(limit)],
            )
            return [(r[0], r[1], r[2]) for r in cur.fetchall()]

    def assign_canonicals(self) -> int:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(
                """
                WITH ranked AS (
                    SELECT j.job_uuid, j.content_hash,
                           row_number() OVER (
                               PARTITION BY j.content_hash
                               ORDER BY (j.canonical_job_uuid = j.job_uuid) DESC NULLS LAST,
                                        (e.model_name = 'NaqibL/bge-base-sgmarket-v2') DESC NULLS LAST,
                                        (e.job_uuid IS NOT NULL) DESC,
                                        j.first_seen_at ASC, j.job_uuid ASC) AS rn
                      FROM jobs j
                      LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                     WHERE j.content_hash IS NOT NULL
                ), canon AS (
                    SELECT content_hash, job_uuid AS canonical FROM ranked WHERE rn = 1
                )
                UPDATE jobs j SET canonical_job_uuid = canon.canonical
                  FROM canon
                 WHERE j.content_hash = canon.content_hash AND j.canonical_job_uuid IS NULL
                """
            )
            n = cur.rowcount or 0
            cur.execute(
                "UPDATE jobs SET canonical_job_uuid = job_uuid WHERE content_hash IS NULL AND canonical_job_uuid IS NULL"
            )
            return n + (cur.rowcount or 0)

    def copy_fields_from_canonicals(self) -> int:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(
                """
                UPDATE jobs j
                   SET min_years_experience = COALESCE(j.min_years_experience, c.min_years_experience),
                       llm_fields_json      = COALESCE(j.llm_fields_json, c.llm_fields_json),
                       role_family          = COALESCE(j.role_family, c.role_family),
                       role_cluster         = COALESCE(j.role_cluster, c.role_cluster),
                       predicted_tier       = COALESCE(j.predicted_tier, c.predicted_tier),
                       role_conf            = COALESCE(j.role_conf, c.role_conf),
                       tier_conf            = COALESCE(j.tier_conf, c.tier_conf)
                  FROM jobs c
                 WHERE c.job_uuid = j.canonical_job_uuid
                   AND j.canonical_job_uuid <> j.job_uuid
                   AND ((j.llm_fields_json IS NULL AND c.llm_fields_json IS NOT NULL)
                        OR (j.role_family IS NULL AND c.role_family IS NOT NULL))
                """
            )
            return cur.rowcount or 0

    def noncanonical_embedded_uuids(self) -> list[str]:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(
                """
                SELECT e.job_uuid FROM job_embeddings e
                  JOIN jobs j ON j.job_uuid = e.job_uuid
                 WHERE j.canonical_job_uuid IS NOT NULL AND j.canonical_job_uuid <> j.job_uuid
                """
            )
            return [r[0] for r in cur.fetchall()]

    def delete_embeddings_by_uuids(self, uuids: list[str]) -> int:
        if not uuids:
            return 0
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute("DELETE FROM job_embeddings WHERE job_uuid = ANY(%s)", [list(uuids)])
            return cur.rowcount or 0

    def posting_group_stats(self) -> dict:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT count(*), coalesce(sum(repost_count), 0), coalesce(max(repost_count), 0),
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY reposts_365d),
                       percentile_cont(0.95) WITHIN GROUP (ORDER BY reposts_365d)
                  FROM posting_groups
                """
            )
            g, m, mx, p50, p95 = cur.fetchone()
            return {"groups": int(g), "members": int(m), "max_repost_count": int(mx),
                    "p50_reposts_365d": float(p50 or 0), "p95_reposts_365d": float(p95 or 0)}
```

- [ ] **Step 5: Write the script**

```python
# scripts/backfill_posting_keys.py
"""One-off backfill for SGSAL-024: content hashes, canonical pointers, field copy,
duplicate-vector deletion, posting_groups refresh.

Resumable: hashing selects only rows without a content_hash; canonical
assignment only touches NULL pointers; deletion recomputes its list each run.

Usage (repo root, DATABASE_URL in .env):
  uv run python scripts/backfill_posting_keys.py --dry-run      # hashes + canonicals + stats, NO deletes
  uv run python scripts/backfill_posting_keys.py --apply        # also copies fields and deletes dup vectors
  uv run python scripts/backfill_posting_keys.py --hash-only    # just step 1 (safe to run anytime)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from mcf.lib.pipeline.posting_key import posting_key  # noqa: E402
from mcf.lib.storage.postgres_store import PostgresStore  # noqa: E402


def step_hash(store: PostgresStore, batch: int) -> int:
    done, after, t0 = 0, "", time.perf_counter()
    while True:
        rows = store.iter_jobs_needing_hash(after, batch)
        if not rows:
            break
        store.set_content_hashes([(u, posting_key(t, d)) for u, t, d in rows])
        done += len(rows)
        after = rows[-1][0]
        if done % (batch * 10) == 0:
            rate = done / (time.perf_counter() - t0)
            print(f"  hashed {done:,} ({rate:,.0f}/s)", flush=True)
    print(f"step 1: hashed {done:,} jobs in {time.perf_counter() - t0:,.0f}s")
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=5000)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="hash + assign canonicals + print stats; no field copy, no deletes")
    g.add_argument("--apply", action="store_true", help="everything incl. deleting non-canonical vectors")
    g.add_argument("--hash-only", action="store_true")
    a = ap.parse_args()

    store = PostgresStore(os.environ["DATABASE_URL"])
    store.ensure_schema()

    step_hash(store, a.batch)
    if a.hash_only:
        return

    t = time.perf_counter()
    n = store.assign_canonicals()
    print(f"step 2: assigned {n:,} canonical pointers in {time.perf_counter() - t:,.0f}s")

    dups = store.noncanonical_embedded_uuids()
    print(f"        {len(dups):,} non-canonical jobs still hold a vector")

    if a.dry_run:
        t = time.perf_counter(); store.refresh_posting_groups()
        print(f"step 5: posting_groups refreshed in {time.perf_counter() - t:,.0f}s")
        print("stats:", store.posting_group_stats())
        print("DRY RUN: no fields copied, no vectors deleted. Re-run with --apply.")
        return

    t = time.perf_counter()
    n = store.copy_fields_from_canonicals()
    print(f"step 3: copied LLM fields / Jev labels into {n:,} reposts in {time.perf_counter() - t:,.0f}s")

    t = time.perf_counter(); deleted = 0
    for i in range(0, len(dups), a.batch):
        deleted += store.delete_embeddings_by_uuids(dups[i : i + a.batch])
        if (i // a.batch) % 10 == 0:
            print(f"  deleted {deleted:,}/{len(dups):,}", flush=True)
    print(f"step 4: deleted {deleted:,} duplicate vectors in {time.perf_counter() - t:,.0f}s")

    t = time.perf_counter(); store.refresh_posting_groups()
    print(f"step 5: posting_groups refreshed in {time.perf_counter() - t:,.0f}s")
    print("stats:", store.posting_group_stats())
    print("Next: VACUUM (ANALYZE) job_embeddings; then SGSAL-025 step 1 (halfvec index) reclaims the HNSW space.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the ABC test, then the dry run against Supabase**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py::test_backfill_storage_methods_exist','-v']))"` → PASS.

Run: `uv run python scripts/backfill_posting_keys.py --dry-run` (background it; hashing streams ~1 GB of descriptions, expect 20–40 min; `assign_canonicals` is one statement, expect 1–3 min).
Expected output shape:

```
step 1: hashed ~714,000 jobs in …s
step 2: assigned ~716,000 canonical pointers in …s
        ~250,000–280,000 non-canonical jobs still hold a vector
step 5: posting_groups refreshed in …s
stats: {'groups': ~3xx,000, 'members': ~714,000, 'max_repost_count': …, 'p50_reposts_365d': …, 'p95_reposts_365d': …}
DRY RUN: …
```

Paste the stats into `tickets/SGSAL-024.md` under a "Backfill dry run" heading.

- [ ] **Step 7: STOP — get Luqman's go-ahead for `--apply`**

Deleting ~250k vectors is the one step that costs money and hours to undo (re-embedding). Report the dry-run numbers and wait for an explicit yes. Then:

Run: `uv run python scripts/backfill_posting_keys.py --apply` (background; deletion ~5–10 min in 5k batches), then
`uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import os,psycopg2; c=psycopg2.connect(os.environ['DATABASE_URL']); c.autocommit=True; cur=c.cursor(); cur.execute('SET statement_timeout=0'); cur.execute('VACUUM (ANALYZE) job_embeddings'); print('vacuumed')"`.

Verify the invariant:

```bash
uv run python - <<'EOF'
from dotenv import load_dotenv; load_dotenv('.env')
import os, psycopg2
c = psycopg2.connect(os.environ['DATABASE_URL']); cur = c.cursor(); cur.execute("SET statement_timeout='120s'")
cur.execute("""select count(*) from job_embeddings e join jobs j using(job_uuid) where j.canonical_job_uuid <> j.job_uuid"""); print("non-canonical vectors (must be 0):", cur.fetchone()[0])
cur.execute("""select count(*) from jobs where content_hash is not null and canonical_job_uuid is null"""); print("hashed rows without pointer (must be 0):", cur.fetchone()[0])
cur.execute("""select count(*) from jobs j where j.canonical_job_uuid = j.job_uuid and j.content_hash is not null and j.is_active and not exists (select 1 from job_embeddings e where e.job_uuid=j.job_uuid)"""); print("active canonicals without vector (should be ~today's unembedded only):", cur.fetchone()[0])
cur.execute("select count(*) from job_embeddings"); print("job_embeddings rows:", cur.fetchone()[0])
EOF
```

- [ ] **Step 8: Commit**

```bash
git add scripts/backfill_posting_keys.py src/mcf/lib/storage/base.py src/mcf/lib/storage/postgres_store.py tests/test_smoke.py tickets/SGSAL-024.md
git commit -m "feat(SGSAL-024): resumable backfill — hashes, canonicals, field copy, duplicate-vector delete

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: API — representative cards, group fields, timeline and dashboard endpoints

**Files:**
- Modify: `src/mcf/api/routes/lowball.py` (`LowballResult` line 38-48, `_build_similar_jobs` line 86-108, `_compute_lowball` line 189-263, `_compute_salary_search` ~line 296-330)
- Modify: `src/mcf/api/routes/jobs.py` (add after `get_job_taxonomy`)
- Modify: `src/mcf/api/routes/dashboard.py` (append)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: `get_jobs_with_salary_by_uuids(..., representative=True, company_name=…)`, `get_posting_history`, `get_most_reposted`, `active_canonical_uuids` (Task 4).
- Produces:
  - each similar job dict gains `canonical_job_uuid, repost_count, active_count, first_posted, last_posted, reposts_365d, distinct_companies, min_salary_seen, max_salary_seen`; `LowballResult.total_listings: int | None`.
  - `GET /api/jobs/{job_uuid}/reposts` → `{canonical_job_uuid, title, repost_count, active_count, first_posted, last_posted, reposts_90d, reposts_365d, distinct_companies, latest_salary_min, latest_salary_max, min_salary_seen, max_salary_seen, occurrences: [{job_uuid, date, company, salary_min, salary_max, is_active}]}`; 404 when unknown.
  - `GET /api/dashboard/most-reposted-public?days=365&limit=20` → list of `get_most_reposted` rows.

- [ ] **Step 1: Write the failing smoke tests**

Append to `tests/test_smoke.py`:

```python
def test_reposts_endpoint_404_for_unknown_job(client):
    r = client.get("/api/jobs/no-such-job/reposts")
    assert r.status_code == 404


def test_reposts_endpoint_shape_for_known_job(client):
    from mcf.api.deps import get_store

    store = get_store()
    uuids = [u for u, _, _ in store.get_all_embedded_job_ids_ranked([0.0] * 768, limit=1)]
    if not uuids:
        pytest.skip("no embeddings")
    r = client.get(f"/api/jobs/{uuids[0]}/reposts")
    assert r.status_code == 200
    data = r.json()
    assert data["repost_count"] >= 1
    assert isinstance(data["occurrences"], list) and len(data["occurrences"]) == data["repost_count"]
    assert {"job_uuid", "date", "company", "salary_min", "salary_max", "is_active"} <= set(data["occurrences"][0])


def test_most_reposted_public(client):
    r = client.get("/api/dashboard/most-reposted-public?days=365&limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/api/dashboard/most-reposted-public?days=7")
    assert r.status_code == 422


def test_lowball_cards_carry_group_fields(client):
    body = {"title": "Data Analyst", "description": "Build dashboards in Power BI and write SQL. " * 5, "top_k": 5}
    r = client.post("/api/lowball/check", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "total_listings" in data
    for j in data["similar_jobs"]:
        assert "repost_count" in j and j["repost_count"] >= 1
        assert "canonical_job_uuid" in j
    # one card per posting: canonical uuids are unique
    cu = [j["canonical_job_uuid"] for j in data["similar_jobs"]]
    assert len(cu) == len(set(cu))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py','-k','reposts_endpoint or most_reposted_public or group_fields','-v']))"`
Expected: 404 test may pass already (unknown route → 404); the other three FAIL.

- [ ] **Step 3: lowball.py changes**

a) `LowballResult`: add `total_listings: int | None = None` after `company_similar_jobs`.

b) `_build_similar_jobs`: score lookup by canonical uuid, pass group fields through:

```python
def _build_similar_jobs(jobs: list[dict], uuid_to_score: dict[str, float], top_k: int) -> list[dict]:
    result = []
    for j in jobs:
        raw_desc = j.get("description") or ""
        llm_raw = j.get("llm_fields_json")
        llm = _json.loads(llm_raw) if isinstance(llm_raw, str) else (llm_raw or {})
        score_key = j.get("canonical_job_uuid") or j["job_uuid"]
        result.append({
            "job_uuid": j["job_uuid"],
            "canonical_job_uuid": score_key,
            "title": j["title"],
            "company_name": j.get("company_name"),
            "location": j.get("location"),
            "job_url": j.get("job_url"),
            "salary_min": j.get("salary_min"),
            "salary_max": j.get("salary_max"),
            "is_active": j.get("is_active", True),
            "description": raw_desc or None,
            "similarity_score": round(uuid_to_score.get(score_key, 0.0), 4),
            "min_years_experience": j.get("min_years_experience"),
            "inferred_seniority": llm.get("inferred_seniority"),
            "canonical_skills": llm.get("canonical_skills"),
            "repost_count": int(j.get("repost_count") or 1),
            "active_count": int(j.get("active_count") or (1 if j.get("is_active", True) else 0)),
            "first_posted": _iso(j.get("first_posted")),
            "last_posted": _iso(j.get("last_posted")),
            "reposts_365d": int(j.get("reposts_365d") or 1),
            "distinct_companies": int(j.get("distinct_companies") or 1),
            "min_salary_seen": j.get("min_salary_seen"),
            "max_salary_seen": j.get("max_salary_seen"),
        })
    result.sort(key=lambda x: x["similarity_score"], reverse=True)
    return result[:top_k]


def _iso(d) -> str | None:
    return d.isoformat() if d is not None and hasattr(d, "isoformat") else d
```

c) `_compute_lowball`: every `get_jobs_with_salary_by_uuids(...)` call becomes representative:

```python
            c_jobs = store.get_jobs_with_salary_by_uuids(c_uuids, representative=True, company_name=body.company_name)
...
    jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()), representative=True)
    jobs = [j for j in jobs if _has_valid_salary(j)]
    salary_jobs = store.get_jobs_with_salary_by_uuids(
        list(uuid_to_score.keys()), compliant_ranges_only=True, representative=True
    )
```

and compute `total_listings = sum(int(j.get("repost_count") or 1) for j in jobs)` right after `similar = _build_similar_jobs(...)`; pass `total_listings=total_listings` into all three `LowballResult(...)` returns.

d) `_compute_salary_search`: replace `active_uuids = store.active_job_uuids()` with `active_uuids = store.active_canonical_uuids()` (the salary-filter set is already canonical after Task 4) and make both `get_jobs_with_salary_by_uuids` calls `representative=True`. In the `SalarySearchJob(...)` list comprehension (line ~336) the score must be looked up by the canonical key, because `job_uuid` is now the latest occurrence:

```python
            similarity_score=uuid_to_score.get(j.get("canonical_job_uuid") or j["job_uuid"], 0.0),
```

`SalarySearchJob` keeps its existing fields (extra dict keys are simply not passed).

- [ ] **Step 4: jobs.py — timeline endpoint**

Add after `get_job_taxonomy`:

```python
@router.get("/api/jobs/{job_uuid}/reposts")
def get_job_reposts(job_uuid: str, _: str | None = Depends(get_optional_user)):
    """Public: the posting group a job belongs to — repost count, dates, per-occurrence
    salary/company history (SGSAL-024). Cached 1 h per job."""
    from mcf.api.cache.response import cache_get, cache_set, make_cache_key

    key = make_cache_key("jobs:reposts", job_uuid=job_uuid)
    if settings.enable_response_cache:
        cached = cache_get(key)
        if cached is not None:
            return cached
    store = get_store()
    group = store.get_posting_history(job_uuid)
    if group is None:
        job = store.get_job(job_uuid)  # title, company_name, is_active, first_seen_at (no salary)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        salary_rows = store.get_jobs_with_salary_by_uuids([job_uuid])
        if salary_rows:
            job = {**job, "salary_min": salary_rows[0].get("salary_min"), "salary_max": salary_rows[0].get("salary_max")}
        group = _single_occurrence_group(job)
    out = {
        "canonical_job_uuid": group.get("canonical_job_uuid"),
        "title": group.get("title"),
        "repost_count": int(group.get("repost_count") or 1),
        "active_count": int(group.get("active_count") or 0),
        "first_posted": _d(group.get("first_posted")),
        "last_posted": _d(group.get("last_posted")),
        "reposts_90d": int(group.get("reposts_90d") or 0),
        "reposts_365d": int(group.get("reposts_365d") or 0),
        "distinct_companies": int(group.get("distinct_companies") or 1),
        "latest_salary_min": group.get("latest_salary_min"),
        "latest_salary_max": group.get("latest_salary_max"),
        "min_salary_seen": group.get("min_salary_seen"),
        "max_salary_seen": group.get("max_salary_seen"),
        "occurrences": group.get("occurrences") or [],
    }
    if settings.enable_response_cache:
        cache_set(key, TTL_JOB_DETAIL, out)
    return out


def _d(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _single_occurrence_group(job: dict) -> dict:
    # get_job() has no posted_date; first_seen_at is the crawl date, which is the
    # same fallback the posting_groups view uses.
    date = job["first_seen_at"].date() if job.get("first_seen_at") else None
    return {
        "canonical_job_uuid": job["job_uuid"], "title": job.get("title"), "repost_count": 1,
        "active_count": 1 if job.get("is_active") else 0, "first_posted": date, "last_posted": date,
        "reposts_90d": 0, "reposts_365d": 0, "distinct_companies": 1,
        "latest_salary_min": job.get("salary_min"), "latest_salary_max": job.get("salary_max"),
        "min_salary_seen": job.get("salary_min"), "max_salary_seen": job.get("salary_max"),
        "occurrences": [{
            "job_uuid": job["job_uuid"], "date": _d(date), "company": job.get("company_name"),
            "salary_min": job.get("salary_min"), "salary_max": job.get("salary_max"),
            "is_active": bool(job.get("is_active")),
        }],
    }
```

`store.get_job()` (`postgres_store.py:435`) returns `job_uuid, title, company_name, location, job_url, is_active, first_seen_at, last_seen_at, skills_json, description` — no salary, hence the second lookup above.

The `occurrences` jsonb comes back from psycopg2 as a Python list already; the `date` values inside are strings (jsonb serialised them), so no conversion is needed there.

- [ ] **Step 5: dashboard.py — most reposted**

```python
@router.get("/api/dashboard/most-reposted-public")
@cache_response(TTL_DASHBOARD, "dashboard:most-reposted-public")
def get_dashboard_most_reposted_public(
    days: int = Query(default=365, ge=90, le=365),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Public: posting groups with the most reposts in the window (SGSAL-024).
    ``days`` is snapped to 90 or 365 (the view keeps those two counters)."""
    if days not in (90, 365):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="days must be 90 or 365")
    store = get_store()
    rows = store.get_most_reposted(days=days, limit=limit)
    for r in rows:
        for k in ("first_posted", "last_posted"):
            if hasattr(r.get(k), "isoformat"):
                r[k] = r[k].isoformat()
    return rows
```

(`ge=90` makes `days=7` a 422 from validation before the body runs — the test expects 422 either way.)

- [ ] **Step 6: Run the smoke tests**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/test_smoke.py','-v']))"`
Expected: all pass. If `test_lowball_cards_carry_group_fields` returns `insufficient_data` with an empty `similar_jobs`, that is still a pass (the loop is empty); the uniqueness assertion is what matters when results exist.

- [ ] **Step 7: Commit**

```bash
git add src/mcf/api/routes/lowball.py src/mcf/api/routes/jobs.py src/mcf/api/routes/dashboard.py tests/test_smoke.py
git commit -m "feat(SGSAL-024): checker returns one card per posting with repost facts; reposts + most-reposted endpoints

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Frontend plumbing — types, API client, repost helpers, Next.js proxy route

**Files:**
- Modify: `frontend/lib/types.ts` (`SimilarJob` line 104-118, `LowballResult` line 162-173)
- Modify: `frontend/lib/api.ts` (`dashboardApi` object ending line 318; add `jobsApi`-style export)
- Create: `frontend/lib/repost.ts`
- Create: `frontend/app/api/dashboard/most-reposted/route.ts`

**Interfaces:**
- Produces: types `PostingOccurrence`, `PostingHistory`, `MostRepostedRow`; `SimilarJob` optional fields; `LowballResult.total_listings?`; `postingsApi.getHistory(jobUuid)`, `dashboardApi.getMostReposted(days?, limit?)`; helpers `REPOST_AMBER_MIN`, `REPOST_COMPANIES_AMBER_MIN`, `repostTone(j)`, `repostLabel(j)`, `monthYear(iso)`, `fullDate(iso)`, `salaryRangeText(min, max)`, `salaryMovement(occ)`.

- [ ] **Step 1: Types**

In `types.ts`, extend `SimilarJob` (after `canonical_skills`):

```ts
  // SGSAL-024 posting group facts (absent on older API responses)
  canonical_job_uuid?: string
  repost_count?: number
  active_count?: number
  first_posted?: string | null
  last_posted?: string | null
  reposts_365d?: number
  distinct_companies?: number
  min_salary_seen?: number | null
  max_salary_seen?: number | null
```

Add `total_listings?: number | null` to `LowballResult`. Add after `LowballResult`:

```ts
// --- Posting groups / reposts (SGSAL-024) ---

export interface PostingOccurrence {
  job_uuid: string
  date: string | null
  company: string | null
  salary_min: number | null
  salary_max: number | null
  is_active: boolean
}

export interface PostingHistory {
  canonical_job_uuid: string
  title: string | null
  repost_count: number
  active_count: number
  first_posted: string | null
  last_posted: string | null
  reposts_90d: number
  reposts_365d: number
  distinct_companies: number
  latest_salary_min: number | null
  latest_salary_max: number | null
  min_salary_seen: number | null
  max_salary_seen: number | null
  occurrences: PostingOccurrence[]
}

export interface MostRepostedRow {
  canonical_job_uuid: string
  title: string | null
  company: string | null
  distinct_companies: number
  repost_count: number
  reposts_in_window: number
  first_posted: string | null
  last_posted: string | null
  latest_salary_min: number | null
  latest_salary_max: number | null
}
```

- [ ] **Step 2: API client**

In `api.ts`, add `PostingHistory, MostRepostedRow` to the type import, then inside `dashboardApi` (before its closing `}`):

```ts
  getMostReposted: async (days: 90 | 365 = 365, limit = 20) => {
    const res = await fetch(`/api/dashboard/most-reposted?days=${days}&limit=${limit}`)
    if (!res.ok) throw new Error('Failed to fetch most reposted roles')
    return res.json() as Promise<MostRepostedRow[]>
  },
```

and a new export next to `lowballApi`:

```ts
export const postingsApi = {
  /** Repost history for any job in a posting group (public, cached 1 h server-side). */
  getHistory: (jobUuid: string) =>
    apiFetch<PostingHistory>(`/api/jobs/${encodeURIComponent(jobUuid)}/reposts`),
}
```

- [ ] **Step 3: Next.js proxy route** — `frontend/app/api/dashboard/most-reposted/route.ts`, copied from the role-families route with the query string passed through:

```ts
import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 3600

export const revalidate = REVALIDATE_SECONDS

export async function GET(req: NextRequest) {
  const days = req.nextUrl.searchParams.get('days') === '90' ? '90' : '365'
  const limitRaw = Number(req.nextUrl.searchParams.get('limit') ?? '20')
  const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(limitRaw, 1), 100) : 20
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/dashboard/most-reposted-public?days=${days}&limit=${limit}`,
          { headers: { 'Content-Type': 'application/json' }, next: { revalidate: REVALIDATE_SECONDS } }
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-most-reposted', days, String(limit)],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/most-reposted]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
```

- [ ] **Step 4: Helpers** — `frontend/lib/repost.ts`:

```ts
import type { PostingOccurrence, SimilarJob } from './types'

/** First guesses (SGSAL-024); tune from the backfill's reposts_365d distribution. */
export const REPOST_AMBER_MIN = 6
export const REPOST_COMPANIES_AMBER_MIN = 3

export type RepostTone = 'none' | 'slate' | 'amber'

type GroupFacts = Pick<SimilarJob, 'repost_count' | 'reposts_365d' | 'distinct_companies' | 'first_posted'>

export function repostTone(j: GroupFacts): RepostTone {
  const n = j.repost_count ?? 1
  if (n < 2) return 'none'
  if ((j.distinct_companies ?? 1) >= REPOST_COMPANIES_AMBER_MIN) return 'amber'
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return 'amber'
  return 'slate'
}

/** Badge copy. Names the fact; never a judgement. */
export function repostLabel(j: GroupFacts): string {
  const n = j.repost_count ?? 1
  const companies = j.distinct_companies ?? 1
  if (companies >= REPOST_COMPANIES_AMBER_MIN) return `Posted under ${companies} company names`
  if ((j.reposts_365d ?? 0) >= REPOST_AMBER_MIN) return `Reposted ${n}× in 12 months`
  const since = monthYear(j.first_posted)
  return since ? `Reposted ${n}× · since ${since}` : `Reposted ${n}×`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "Mar 2026" from an ISO date; '' when missing/invalid. */
export function monthYear(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`
}

/** "Mar 4, 2026" */
export function fullDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`
}

export function salaryRangeText(min: number | null | undefined, max: number | null | undefined): string | null {
  const fmt = (v: number) => `$${v.toLocaleString()}`
  if (min != null && max != null) return `${fmt(min)} – ${fmt(max)}/mo`
  if (min != null) return `From ${fmt(min)}/mo`
  if (max != null) return `Up to ${fmt(max)}/mo`
  return null
}

/** Oldest vs newest salaried occurrence. null when fewer than 2 have a salary. */
export function salaryMovement(occ: PostingOccurrence[]): string | null {
  const withSalary = occ.filter(o => o.salary_min != null || o.salary_max != null)
  if (withSalary.length < 2) return null
  // occurrences arrive newest-first
  const newest = withSalary[0]
  const oldest = withSalary[withSalary.length - 1]
  const a = salaryRangeText(oldest.salary_min, oldest.salary_max)
  const b = salaryRangeText(newest.salary_min, newest.salary_max)
  if (!a || !b) return null
  return a === b ? 'Same range every time' : `Range moved from ${a.replace('/mo', '')} to ${b}`
}
```

- [ ] **Step 5: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts frontend/lib/repost.ts frontend/app/api/dashboard/most-reposted/route.ts
git commit -m "feat(SGSAL-024): frontend types, API client, repost helpers, most-reposted proxy route

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Checker UI — repost badge, posting history panel, summary line

**Files:**
- Create: `frontend/app/lowball/RepostBadge.tsx`
- Create: `frontend/app/lowball/PostingHistoryPanel.tsx`
- Modify: `frontend/app/lowball/LowballContent.tsx` (`SimilarJobCard` line 120-331; summary text at lines 785 and 791; historical footer line 260-266; lucide import block ending line 32)

**Interfaces:**
- Consumes: `repostTone`, `repostLabel`, `monthYear`, `fullDate`, `salaryRangeText`, `salaryMovement` (Task 8); `postingsApi.getHistory`; `SimilarJob` fields.
- Produces: `<RepostBadge job={SimilarJob} expanded={boolean} onToggle={() => void} />` renders nothing when `repost_count < 2`; `<PostingHistoryPanel jobUuid={string} />`.

- [ ] **Step 1: RepostBadge**

```tsx
// frontend/app/lowball/RepostBadge.tsx
'use client'

import { ChevronDown, Repeat } from 'lucide-react'
import type { SimilarJob } from '@/lib/types'
import { repostLabel, repostTone } from '@/lib/repost'

interface Props {
  job: SimilarJob
  expanded: boolean
  onToggle: () => void
}

/** Chip-row button: "Reposted N× · since Mon YYYY". Hidden for single postings. */
export function RepostBadge({ job, expanded, onToggle }: Props) {
  const tone = repostTone(job)
  if (tone === 'none') return null
  const cls =
    tone === 'amber'
      ? 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800'
      : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:border-slate-600'
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className={`flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border transition-colors ${cls}`}
    >
      <Repeat className="w-3 h-3" />
      {repostLabel(job)}
      <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? 'rotate-180' : ''}`} />
    </button>
  )
}
```

- [ ] **Step 2: PostingHistoryPanel**

```tsx
// frontend/app/lowball/PostingHistoryPanel.tsx
'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { postingsApi } from '@/lib/api'
import type { PostingHistory } from '@/lib/types'
import { fullDate, monthYear, salaryMovement, salaryRangeText } from '@/lib/repost'

const ROWS_COLLAPSED = 8

export function PostingHistoryPanel({ jobUuid }: { jobUuid: string }) {
  const { data, error, isLoading } = useSWR<PostingHistory>(
    ['posting-history', jobUuid],
    () => postingsApi.getHistory(jobUuid),
    { revalidateOnFocus: false, dedupingInterval: 3600000 },
  )
  const [showAll, setShowAll] = useState(false)

  if (isLoading) {
    return (
      <div className="mt-3 space-y-2" aria-busy="true">
        <div className="h-3 w-2/3 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />
        <div className="h-3 w-1/2 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />
      </div>
    )
  }
  if (error || !data) {
    return <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">Couldn&apos;t load posting history.</p>
  }

  const occ = data.occurrences
  const rows = showAll ? occ : occ.slice(0, ROWS_COLLAPSED)
  const movement = salaryMovement(occ)
  const companies = data.distinct_companies >= 2 ? ` · ${data.distinct_companies} company names` : ''

  return (
    <div className="mt-3 rounded-lg border border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 p-3">
      <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
        First seen {monthYear(data.first_posted)} · last {monthYear(data.last_posted)} · {data.repost_count} postings{companies}
      </p>
      {movement && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{movement}</p>
      )}
      <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-700">
        {rows.map(o => (
          <li key={o.job_uuid} className="py-1.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="text-slate-600 dark:text-slate-300 tabular-nums">{fullDate(o.date) || '—'}</span>
              <span className={o.is_active ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}>
                {o.is_active ? 'Active' : 'Closed'}
              </span>
            </div>
            <div className="flex flex-wrap justify-between gap-x-2 text-slate-500 dark:text-slate-400">
              <span className="truncate">{o.company || 'Company not listed'}</span>
              <span>{salaryRangeText(o.salary_min, o.salary_max) ?? 'No salary listed'}</span>
            </div>
          </li>
        ))}
      </ul>
      {occ.length > ROWS_COLLAPSED && (
        <button
          type="button"
          onClick={() => setShowAll(v => !v)}
          className="mt-1 text-xs font-medium text-indigo-500 hover:text-indigo-700 dark:text-indigo-400"
        >
          {showAll ? 'Show fewer' : `Show all ${occ.length}`}
        </button>
      )}
      <p className="mt-2 text-[11px] leading-snug text-slate-400 dark:text-slate-500">
        Frequent reposting can mean ongoing hiring, high turnover or an agency listing. Treat it as a signal, not a verdict.
      </p>
    </div>
  )
}
```

- [ ] **Step 3: Wire into `SimilarJobCard`**

In `LowballContent.tsx`:

a) imports: `import { RepostBadge } from './RepostBadge'` and `import { PostingHistoryPanel } from './PostingHistoryPanel'`; add `monthYear` from `'@/lib/repost'`.

b) state, next to `descExpanded`: `const [historyOpen, setHistoryOpen] = useState(false)`.

c) in the chip row, after the `Position closed` chip block (still inside the `flex flex-wrap items-center gap-2 mt-2.5` div):

```tsx
              <RepostBadge job={job} expanded={historyOpen} onToggle={() => setHistoryOpen(v => !v)} />
```

d) directly after the chip-row `</div>` and before the skills block:

```tsx
            {historyOpen && <PostingHistoryPanel jobUuid={job.canonical_job_uuid ?? job.job_uuid} />}
```

e) historical footer text (line ~263) becomes:

```tsx
            Historical listing{job.last_posted ? ` · last posted ${monthYear(job.last_posted)}` : ''} · salary data still valid for benchmarking
```

- [ ] **Step 4: Summary line**

Lines 785 and 791 both render `{activeCount} active · {totalCount - activeCount} historical`. Replace both with a shared string computed next to `activeCount`:

```tsx
              const listingsTotal = result.total_listings ?? null
              const summaryText =
                `${totalCount} postings · ${activeCount} still open` +
                (listingsTotal != null && listingsTotal > totalCount ? ` · ${listingsTotal} listings including reposts` : '')
```

and use `{summaryText}` in both places.

- [ ] **Step 5: Build and eyeball**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean build.

Run the stack locally (backend `uv run python -m uvicorn mcf.api.server:app --reload --port 8000`, frontend `npm run dev`), open `/`, search "Customer Service Executive" with a few lines of description, and check:
- a card with a badge appears (post-backfill many will); click → panel shows summary, movement line, dated rows, footnote; click again closes.
- summary line reads "N postings · M still open · K listings including reposts".
- narrow the window to 390 px: badge wraps within the chip row, panel rows stack into two lines, no horizontal scroll.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/lowball/RepostBadge.tsx frontend/app/lowball/PostingHistoryPanel.tsx frontend/app/lowball/LowballContent.tsx
git commit -m "feat(SGSAL-024): repost badge + posting history panel on checker cards; postings summary line

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Dashboard — "Most reposted roles" card

**Files:**
- Create: `frontend/app/dashboard/MostRepostedTable.tsx`
- Modify: `frontend/app/dashboard/DashboardContent.tsx` (render after `<LazyMarketInsightsCharts />`, line ~261)

**Interfaces:**
- Consumes: `dashboardApi.getMostReposted`, `MostRepostedRow`, `monthYear`, `salaryRangeText`, `DASHBOARD_SWR_CONFIG`, `Card`/`CardBody`/`EmptyState` from `@/components/design` (same imports `MarketInsightsCharts.tsx` uses).

- [ ] **Step 1: Component**

```tsx
// frontend/app/dashboard/MostRepostedTable.tsx
'use client'

import useSWR from 'swr'
import { Repeat } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { MostRepostedRow } from '@/lib/types'
import { monthYear, salaryRangeText } from '@/lib/repost'
import { Card, CardBody, EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

export function MostRepostedTable() {
  const { data, error, isLoading } = useSWR<MostRepostedRow[]>(
    'dashboard-most-reposted-365',
    () => dashboardApi.getMostReposted(365, 20),
    DASHBOARD_SWR_CONFIG,
  )

  return (
    <Card className="border-slate-200 dark:border-slate-700">
      <CardBody>
        <div className="flex items-center gap-2 mb-1">
          <Repeat className="w-4 h-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Most reposted roles · last 12 months</h3>
        </div>
        <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
          Each distinct posting text counts once. Reposts are shown as that posting&apos;s history.
        </p>
        {isLoading && <div className="h-24 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />}
        {error && <EmptyState message="Couldn't load reposts" description="Try again later." />}
        {data && data.length === 0 && <EmptyState message="No reposted roles yet" description="Appears after the first crawl with posting groups." />}
        {data && data.length > 0 && (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs">
              <thead className="text-left text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="px-2 py-1 font-medium">Role</th>
                  <th className="px-2 py-1 font-medium">Company</th>
                  <th className="px-2 py-1 font-medium text-right">Postings</th>
                  <th className="px-2 py-1 font-medium">First</th>
                  <th className="px-2 py-1 font-medium">Last</th>
                  <th className="px-2 py-1 font-medium">Latest range</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {data.map(r => (
                  <tr key={r.canonical_job_uuid} className="text-slate-700 dark:text-slate-200">
                    <td className="px-2 py-1.5 max-w-[16rem] truncate" title={r.title ?? ''}>{r.title ?? '—'}</td>
                    <td className="px-2 py-1.5 max-w-[12rem] truncate" title={r.company ?? ''}>
                      {r.distinct_companies >= 2 ? `${r.distinct_companies} companies` : (r.company ?? '—')}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{r.reposts_in_window}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{monthYear(r.first_posted) || '—'}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{monthYear(r.last_posted) || '—'}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{salaryRangeText(r.latest_salary_min, r.latest_salary_max) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
```

`EmptyState` (`frontend/components/design/EmptyState.tsx:41`) takes `icon, message, description, action, className`; `message` is the heading.

- [ ] **Step 2: Render it**

In `DashboardContent.tsx`, import `import { MostRepostedTable } from './MostRepostedTable'` and add `<MostRepostedTable />` on the line after `<LazyMarketInsightsCharts />` (inside the same wrapper so it inherits spacing).

- [ ] **Step 3: Build and eyeball**

Run: `cd frontend && npx tsc --noEmit && npm run build` → clean. Open `/dashboard` locally: the card renders under the market insights; table scrolls horizontally on a phone width instead of overflowing the page.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/MostRepostedTable.tsx frontend/app/dashboard/DashboardContent.tsx
git commit -m "feat(SGSAL-024): dashboard card — most reposted roles (12 months) with methodology note

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Docs, full test run, deploy order, production verification

**Files:**
- Modify: `CLAUDE.md` (design fact 8 and the "Pipeline — Jev role families" roadmap paragraph), `src/mcf/lib/storage/README.md`, `tickets/SGSAL-024.md`, `TICKETS.md`

- [ ] **Step 1: Docs**

`CLAUDE.md` design facts — add fact 9:

```markdown
9. **Posting groups (SGSAL-024):** `jobs.content_hash` = `posting_key(title, description)` (company excluded); `jobs.canonical_job_uuid` points at the group member that owns the `job_embeddings` row, LLM fields and Jev labels. `job_embeddings` holds canonical rows only; the crawl links reposts in Phase 1 (`mcf.lib.pipeline.reposts`) and skips cleaner/embed/Jev for them. `posting_groups` (materialised view, refreshed at crawl end) feeds the repost badge, `/api/jobs/{uuid}/reposts` and the dashboard's most-reposted table. The checker shows one card per posting (latest occurrence) and counts one salary per posting. Never delete `jobs` rows; vectors are derived and deduplicated, not pruned (policy decided 2026-11-07).
```

Roadmap paragraph: replace "SGSAL-024 (content-addressed embeddings…)" wording with "SGSAL-024 shipped; next SGSAL-025 step 1 (halfvec index rebuild)".

`src/mcf/lib/storage/README.md`: add a "Posting groups" section listing the new Storage methods (names from Tasks 3, 4, 6) and the view columns.

`tickets/SGSAL-024.md`: status `in-progress` → `done` once Step 5 below passes; record backfill numbers, DB size before/after, and the first crawl's "reposts linked" count. `TICKETS.md` row status to `done`.

- [ ] **Step 2: Full test suite + lint**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest,sys; sys.exit(pytest.main(['tests/','-v']))"`
Expected: all pass (91 previously + 3 new files' tests; count them in the ticket).

Run: `uv run ruff check src scripts tests` → no findings in files touched by this plan.

- [ ] **Step 3: Push and watch CI/Railway**

```bash
git push origin master
gh run list --limit 3
```

Expected: lint workflow green; Railway redeploys (`railway status` or the dashboard). Then:

```bash
curl -s https://<railway-host>/api/health
curl -s "https://<railway-host>/api/dashboard/most-reposted-public?limit=3"
```

Expected: 200 and a JSON list.

- [ ] **Step 4: First production crawl check (next morning, after the 02:00 UTC crawl)**

```bash
gh run list --workflow daily-crawl-1.yml --limit 1
gh run view <id> --log | grep -E "reposts linked|posting_groups"
```

Expected: a line like `N reposts linked to existing postings (skipped cleaner/embed/Jev)` and no `posting_groups refresh failed`. Verify in SQL that no active repost got a vector:

```sql
select count(*) from job_embeddings e join jobs j using(job_uuid) where j.canonical_job_uuid <> j.job_uuid;  -- 0
```

- [ ] **Step 5: Hand over to SGSAL-025 step 1**

Record in `tickets/SGSAL-025.md` the post-backfill `job_embeddings` row count and `pg_total_relation_size('job_embeddings')`; the halfvec index build there is what reclaims the HNSW space freed by the deletes.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md src/mcf/lib/storage/README.md tickets/SGSAL-024.md tickets/SGSAL-025.md TICKETS.md
git commit -m "docs(SGSAL-024): posting groups design fact, storage README, ticket closed with production numbers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin master
```

---

## Self-review notes

- **Spec coverage:** §4.1 → Task 1; §4.2 → Task 2; §4.3 → Task 2 (view) + Task 3 (refresh) + Task 5 (crawl-end call); §4.4 → Tasks 3, 4, 6; §4.5 → Task 5; §4.6 → Task 6; §4.7 → Task 7; §5.1–5.2 → Task 8; §5.3–5.5 → Task 9; §5.6 → Task 10; §6 error handling → Tasks 5 (degrade to no skips), 7 (404 / single-occurrence fallback), 9 (hidden badge, error line); §7 tests → Tasks 1–7; §8 acceptance → Task 11.
- **Deviation from spec:** the spec mentions surfacing `reposts_linked` in the Telegram digest; the digest script does not read crawl results (it queries recent embedded jobs), so this plan logs the count in the crawl output only. Noted in the ticket.
- **Type consistency:** `get_jobs_with_salary_by_uuids(..., representative=True, company_name=...)` (Task 4) is what Task 7 calls; `posting_groups` column names in Task 2 match the SELECTs in Task 4 and the JSON keys in Tasks 7–8; `plan_repost_links` returns `(pairs, reposts)` in Task 1 and is consumed that way in Task 5; `reposts_in_window` is the API/DB name in Tasks 4, 7, 8, 10.
- **Shared-DB caution:** no test writes rows. The only writes are the migration (Task 2) and the backfill (Task 6, gated on Luqman's go-ahead before `--apply`).
