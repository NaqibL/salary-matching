# Companies Page Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/companies` into a filterable ranking by role family / industry with per-company repost facts, and add repost + role-family sections to `/company/[name]`, all read from one `company_stats` materialised view refreshed at crawl end.

**Architecture:** A new materialised view `company_stats` (one row per company, ~15k rows) aggregates active jobs, `posting_groups` and role families; it is refreshed right after `posting_groups` at crawl end. Four new `Storage` methods read it; two FastAPI routes expose it (new `/api/companies/stats`, extended profile); Next.js route handlers proxy with `unstable_cache`; the `/companies` page and `CompanyContent` render it.

**Tech Stack:** Postgres 17 (Supabase) materialised view + jsonb, psycopg2, FastAPI + pydantic, Next.js app router (client components, SWR), Recharts, Tailwind.

**Spec:** `docs/superpowers/specs/2026-11-08-companies-page-rework-design.md`

## Global Constraints

- All DB access through the `Storage` ABC (`src/mcf/lib/storage/base.py`); routes never import `PostgresStore`.
- All browser API calls through `frontend/lib/api.ts`; components never call `fetch` directly.
- Tests hit the real Postgres via `DATABASE_URL`, no mocks; skip when unset. Run with `.env` loaded: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main([...]))"` (plain `uv run pytest` fails on this machine).
- `ensure_schema()` SQL constant must be byte-identical to the migration (same rule as migration 022).
- Copy rule: name the fact, never the judgement (e.g. "across 18 role families", not "spammer"). `likely_agency` drives a filter, never a label.
- Default floor `min_active = 10`; name search has no floor.
- Production migration is applied by hand (`CREATE MATERIALIZED VIEW` populates in seconds); `ensure_schema` copies are for fresh DBs.
- Commit after each task; commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/migrations/024_company_stats.sql` | view + indexes (source of truth for the SQL) |
| `src/mcf/lib/storage/postgres_store.py` | `_COMPANY_STATS_VIEW_SQL` constant, `ensure_schema` entries, 4 new methods |
| `src/mcf/lib/storage/base.py` | 4 new abstract methods |
| `src/mcf/lib/pipeline/incremental_crawl.py` | call `refresh_company_stats()` after `refresh_posting_groups()` |
| `src/mcf/api/routes/companies.py` | `CompanyStatsRow`, `CompanyStatsResponse`, `CompanyReposted` models; `/api/companies/stats`; profile extension |
| `tests/test_migration_024.py` | constant == migration |
| `tests/test_company_stats.py` | storage invariants on live rows |
| `tests/test_smoke.py` | route shapes |
| `frontend/app/api/companies/stats/route.ts` | Next proxy for stats |
| `frontend/lib/types.ts`, `frontend/lib/api.ts` | `CompanyStatsRow`, `CompanyStatsResponse`, `CompanyReposted`, `companiesApi.getStats` |
| `frontend/lib/roleFamilies.ts` | family display-name fallback + colour map |
| `frontend/app/companies/RoleMixBar.tsx` | stacked mini bar (top 3 families + other) |
| `frontend/app/companies/CompanyStatsTable.tsx` | sortable table + mobile cards |
| `frontend/app/companies/page.tsx` | filters in URL, summary strip, table |
| `frontend/app/company/[name]/CompanyContent.tsx` | repost tile + card, role-family / industry charts |

---

### Task 1: Migration 024 — `company_stats` view, `ensure_schema` copy, constant test

**Files:**
- Create: `scripts/migrations/024_company_stats.sql`
- Modify: `src/mcf/lib/storage/postgres_store.py:24-60` (add constant next to `_POSTING_GROUPS_VIEW_SQL`), `:196-207` (ensure_schema list)
- Test: `tests/test_migration_024.py`

**Interfaces:**
- Produces: table-shaped view `company_stats(company_key text PK, company text, active_count int, distinct_postings int, reposted_count int, multi_company_count int, max_repost_count int, median_salary int|null, salary_sample int, role_family_counts jsonb, family_count int, top_family text|null, category_counts jsonb, total_seen int, first_seen timestamptz, last_seen timestamptz, likely_agency bool)`; constant `_COMPANY_STATS_VIEW_SQL`.

- [ ] **Step 1: Write the failing constant test**

```python
# tests/test_migration_024.py
"""SGSAL-026: keep the ensure_schema view constant identical to migration 024."""

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "scripts" / "migrations" / "024_company_stats.sql"
START = "CREATE MATERIALIZED VIEW IF NOT EXISTS company_stats AS"
END = "WHERE a.active_count > 0"


def test_view_constant_matches_migration():
    from mcf.lib.storage.postgres_store import _COMPANY_STATS_VIEW_SQL

    sql = MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = sql.index(START)
    end = sql.index(END, start) + len(END)
    expected = sql[start:end]
    actual = _COMPANY_STATS_VIEW_SQL.replace("\r\n", "\n").strip().rstrip(";").rstrip()
    assert actual == expected
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run python -m pytest tests/test_migration_024.py -q`
Expected: FAIL — `FileNotFoundError` (migration missing) or `ImportError` for `_COMPANY_STATS_VIEW_SQL`.

- [ ] **Step 3: Write the migration**

```sql
-- scripts/migrations/024_company_stats.sql
-- SGSAL-026: per-company aggregates for /companies and /company/[name].
-- One row per company key (lower(COALESCE(company_canonical, company_name))) with an
-- active job; refreshed at crawl end right after posting_groups
-- (Storage.refresh_company_stats). Excluded aliases are dropped.
--
-- Apply to Supabase BY HAND (populates in a few seconds): the view, then the two indexes.
-- ensure_schema() carries identical IF NOT EXISTS copies for fresh DBs.

CREATE MATERIALIZED VIEW IF NOT EXISTS company_stats AS
WITH base AS (
    SELECT j.job_uuid,
           lower(COALESCE(j.company_canonical, j.company_name)) AS company_key,
           COALESCE(j.company_canonical, j.company_name)        AS company,
           j.is_active, j.first_seen_at, j.last_seen_at,
           COALESCE(j.content_hash, j.job_uuid)                 AS posting_key,
           COALESCE(j.role_family, 'other')                     AS role_family,
           CASE WHEN j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
                THEN (j.salary_min + j.salary_max) / 2
                ELSE j.salary_min END                           AS salary_mid,
           j.categories_json,
           pg.repost_count, pg.distinct_companies
      FROM jobs j
      LEFT JOIN posting_groups pg ON pg.content_hash = j.content_hash
     WHERE j.company_name IS NOT NULL
       AND COALESCE(j.company_canonical, j.company_name) NOT IN
           (SELECT canonical_name FROM company_aliases WHERE is_excluded = TRUE)
), fam AS (
    SELECT company_key,
           jsonb_object_agg(role_family, n)                                  AS role_family_counts,
           count(*)::int                                                     AS family_count,
           (array_agg(role_family ORDER BY n DESC, role_family))[1]          AS top_family
      FROM (SELECT company_key, role_family, count(*)::int AS n
              FROM base WHERE is_active GROUP BY 1, 2) f
     GROUP BY company_key
), cat AS (
    SELECT company_key, jsonb_object_agg(category, n) AS category_counts
      FROM (SELECT b.company_key, c.category, count(*)::int AS n
              FROM (SELECT company_key, categories_json FROM base
                     WHERE is_active AND categories_json LIKE '[%') b,
                   jsonb_array_elements_text(b.categories_json::jsonb) AS c(category)
             GROUP BY 1, 2) x
     GROUP BY company_key
), agg AS (
    SELECT company_key,
           mode() WITHIN GROUP (ORDER BY company)                                       AS company,
           (count(*) FILTER (WHERE is_active))::int                                     AS active_count,
           (count(DISTINCT posting_key) FILTER (WHERE is_active))::int                  AS distinct_postings,
           (count(*) FILTER (WHERE is_active AND repost_count >= 2))::int               AS reposted_count,
           (count(*) FILTER (WHERE is_active AND distinct_companies >= 2))::int         AS multi_company_count,
           COALESCE(max(repost_count) FILTER (WHERE is_active), 1)::int                 AS max_repost_count,
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY salary_mid)
                FILTER (WHERE is_active AND salary_mid IS NOT NULL))::int               AS median_salary,
           (count(salary_mid) FILTER (WHERE is_active))::int                            AS salary_sample,
           count(*)::int                                                                AS total_seen,
           min(first_seen_at)                                                           AS first_seen,
           max(last_seen_at)                                                            AS last_seen
      FROM base
     GROUP BY company_key
)
SELECT a.company_key, a.company, a.active_count, a.distinct_postings, a.reposted_count,
       a.multi_company_count, a.max_repost_count, a.median_salary, a.salary_sample,
       COALESCE(f.role_family_counts, '{}'::jsonb) AS role_family_counts,
       COALESCE(f.family_count, 0)                 AS family_count,
       f.top_family,
       COALESCE(c.category_counts, '{}'::jsonb)    AS category_counts,
       a.total_seen, a.first_seen, a.last_seen,
       (COALESCE(f.family_count, 0) >= 10
        OR a.company ~* '(recruit|manpower|staffing|employment|human resource|\mhr\M|talent|consultanc|outsourc)')
                                                   AS likely_agency
  FROM agg a
  LEFT JOIN fam f USING (company_key)
  LEFT JOIN cat c USING (company_key)
 WHERE a.active_count > 0;

-- REFRESH ... CONCURRENTLY needs the unique index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_stats_key ON company_stats (company_key);
CREATE INDEX IF NOT EXISTS idx_company_stats_active ON company_stats (active_count DESC);
```

- [ ] **Step 4: Add the constant and `ensure_schema` entries**

In `src/mcf/lib/storage/postgres_store.py`, directly after the `_POSTING_GROUPS_VIEW_SQL = """..."""` constant, add `_COMPANY_STATS_VIEW_SQL = """<exact text from `CREATE MATERIALIZED VIEW IF NOT EXISTS company_stats AS` through `WHERE a.active_count > 0` in the migration, no trailing semicolon>"""` with a comment `# SGSAL-026: must stay identical to scripts/migrations/024_company_stats.sql.`

In the `migrations = [...]` list in `ensure_schema`, after the line `"CREATE INDEX IF NOT EXISTS idx_posting_groups_reposts_365d ON posting_groups (reposts_365d DESC)",` add:

```python
            # SGSAL-026 company_stats (migration 024). Production migrated by hand.
            _COMPANY_STATS_VIEW_SQL,
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_company_stats_key ON company_stats (company_key)",
            "CREATE INDEX IF NOT EXISTS idx_company_stats_active ON company_stats (active_count DESC)",
```

- [ ] **Step 5: Run the test**

Run: `uv run python -m pytest tests/test_migration_024.py -q`
Expected: PASS

- [ ] **Step 6: Apply the migration to Supabase and sanity-check the rows**

Run (session pooler, port 5432, so `statement_timeout = 0` sticks):

```python
# scratch: apply_024.py
import os, re
from dotenv import load_dotenv; load_dotenv(".env")
import psycopg2
url = re.sub(r":6543", ":5432", os.environ["DATABASE_URL"])
c = psycopg2.connect(url); c.autocommit = True; cur = c.cursor()
cur.execute("SET statement_timeout = 0")
cur.execute(open("scripts/migrations/024_company_stats.sql", encoding="utf-8").read())
cur.execute("select count(*), count(*) filter (where likely_agency), count(*) filter (where active_count >= 10) from company_stats")
print("rows / likely_agency / 10+ openings:", cur.fetchone())
cur.execute("select company, active_count, distinct_postings, reposted_count, family_count, likely_agency, median_salary from company_stats order by active_count desc limit 5")
for r in cur.fetchall(): print(r)
cur.execute("select count(*) from company_stats where reposted_count > active_count or distinct_postings > active_count")
print("invariant violations (must be 0):", cur.fetchone()[0])
```

Expected: ~14.7k rows, ~1,000 with 10+ openings, 0 violations, top rows are the agencies seen in the spec with `likely_agency = True`.

- [ ] **Step 7: Commit**

```bash
git add scripts/migrations/024_company_stats.sql src/mcf/lib/storage/postgres_store.py tests/test_migration_024.py
git commit -m "feat(SGSAL-026): company_stats materialised view (migration 024) + ensure_schema copy"
```

---

### Task 2: Storage methods + crawl hook

**Files:**
- Modify: `src/mcf/lib/storage/base.py` (after `get_top_companies`, line ~646)
- Modify: `src/mcf/lib/storage/postgres_store.py` (after `get_top_companies`)
- Modify: `src/mcf/lib/pipeline/incremental_crawl.py:308-312`
- Test: `tests/test_company_stats.py`

**Interfaces:**
- Produces:
  - `Storage.refresh_company_stats(self) -> None`
  - `Storage.get_company_stats(self, *, family: str | None = None, category: str | None = None, q: str | None = None, agency: str = "all", min_active: int = 10, sort: str = "openings", limit: int = 50) -> dict` returning `{"rows": list[dict], "total_matching": int, "summary": {"companies": int, "openings": int, "median_salary": int | None}}`; each row has every view column plus `family_active_count: int | None`.
  - `Storage.get_company_stats_one(self, company_name: str) -> dict | None`
  - `Storage.get_company_top_reposted(self, company_name: str, limit: int = 5) -> list[dict]` with keys `canonical_job_uuid, title, repost_count, reposts_365d, distinct_companies, first_posted, last_posted, latest_salary_min, latest_salary_max`.

- [ ] **Step 1: Write the failing storage tests**

```python
# tests/test_company_stats.py
"""SGSAL-026: company_stats storage methods against the live view (skipped without DATABASE_URL)."""

import os

import pytest


@pytest.fixture(scope="module")
def store():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    from mcf.lib.storage.postgres_store import PostgresStore

    return PostgresStore(url)


def test_stats_rows_respect_floor_and_invariants(store):
    out = store.get_company_stats(min_active=10, limit=20)
    assert set(out) == {"rows", "total_matching", "summary"}
    assert out["total_matching"] >= len(out["rows"])
    for r in out["rows"]:
        assert r["active_count"] >= 10
        assert r["reposted_count"] <= r["active_count"]
        assert r["distinct_postings"] <= r["active_count"]
        assert sum(r["role_family_counts"].values()) == r["active_count"]
        assert r["family_active_count"] is None
    assert out["summary"]["companies"] == out["total_matching"]


def test_stats_family_filter_sorts_by_family_openings(store):
    out = store.get_company_stats(family="data_ai_analytics", min_active=1, limit=10)
    counts = [r["family_active_count"] for r in out["rows"]]
    assert all(c is not None and c >= 1 for c in counts)
    assert counts == sorted(counts, reverse=True)
    assert all("data_ai_analytics" in r["role_family_counts"] for r in out["rows"])


def test_stats_agency_filter_and_sorts(store):
    direct = store.get_company_stats(agency="direct", min_active=1, limit=5)
    assert all(r["likely_agency"] is False for r in direct["rows"])
    by_rate = store.get_company_stats(sort="repost_rate", min_active=10, limit=5)["rows"]
    rates = [r["reposted_count"] / r["active_count"] for r in by_rate]
    assert rates == sorted(rates, reverse=True)
    by_pay = store.get_company_stats(sort="median_salary", min_active=10, limit=5)["rows"]
    pays = [r["median_salary"] for r in by_pay]
    assert pays == sorted(pays, reverse=True)


def test_one_and_top_reposted(store):
    top = store.get_company_stats(min_active=10, limit=1)["rows"][0]
    one = store.get_company_stats_one(top["company"])
    assert one is not None and one["company_key"] == top["company_key"]
    assert store.get_company_stats_one("no such company zzz") is None
    reposted = store.get_company_top_reposted(top["company"], limit=5)
    assert len(reposted) <= 5
    for r in reposted:
        assert r["repost_count"] >= 2
    assert [r["repost_count"] for r in reposted] == sorted((r["repost_count"] for r in reposted), reverse=True)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main(['tests/test_company_stats.py','-q']))"`
Expected: FAIL — `AttributeError: 'PostgresStore' object has no attribute 'get_company_stats'` (or `TypeError: Can't instantiate abstract class` once the ABC has the methods but the store does not).

- [ ] **Step 3: Add the abstract methods**

In `src/mcf/lib/storage/base.py`, after `get_top_companies`:

```python
    # === Company stats (SGSAL-026, company_stats materialised view) ===

    @abstractmethod
    def refresh_company_stats(self) -> None:
        """REFRESH MATERIALIZED VIEW CONCURRENTLY company_stats. Call at crawl end after posting_groups."""

    @abstractmethod
    def get_company_stats(
        self,
        *,
        family: str | None = None,
        category: str | None = None,
        q: str | None = None,
        agency: str = "all",
        min_active: int = 10,
        sort: str = "openings",
        limit: int = 50,
    ) -> dict:
        """Filtered, sorted company_stats rows.

        Returns {"rows": [...], "total_matching": int, "summary": {"companies", "openings",
        "median_salary"}}. Each row carries every view column plus ``family_active_count``
        (that family's openings when ``family`` is given, else None). ``agency`` is
        ``all`` | ``direct`` | ``agency``; ``sort`` is ``openings`` | ``repost_rate`` |
        ``median_salary``. Empty result when the view does not exist yet."""

    @abstractmethod
    def get_company_stats_one(self, company_name: str) -> dict | None:
        """The company_stats row whose key is lower(company_name), or None."""

    @abstractmethod
    def get_company_top_reposted(self, company_name: str, limit: int = 5) -> list[dict]:
        """The company's active posting groups with repost_count >= 2, most reposted first."""
```

- [ ] **Step 4: Implement in `PostgresStore`**

After `get_top_companies` in `src/mcf/lib/storage/postgres_store.py`:

```python
    # === Company stats (SGSAL-026) ===

    _COMPANY_STATS_COLS = (
        "company_key, company, active_count, distinct_postings, reposted_count, "
        "multi_company_count, max_repost_count, median_salary, salary_sample, "
        "role_family_counts, family_count, top_family, category_counts, "
        "total_seen, first_seen, last_seen, likely_agency"
    )
    _COMPANY_SORTS = {
        "openings": "COALESCE(%(family_count_expr)s, active_count) DESC",
        "repost_rate": "(reposted_count::float / NULLIF(active_count, 0)) DESC NULLS LAST",
        "median_salary": "median_salary DESC NULLS LAST",
    }

    def refresh_company_stats(self) -> None:
        with self._transaction_cur() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY company_stats")

    def get_company_stats(
        self,
        *,
        family: str | None = None,
        category: str | None = None,
        q: str | None = None,
        agency: str = "all",
        min_active: int = 10,
        sort: str = "openings",
        limit: int = 50,
    ) -> dict:
        import psycopg2.errors

        if agency not in ("all", "direct", "agency"):
            agency = "all"
        family_expr = "(role_family_counts->>%(family)s)::int" if family else "NULL::int"
        order = self._COMPANY_SORTS.get(sort, self._COMPANY_SORTS["openings"]) % {
            "family_count_expr": family_expr
        }
        where = ["active_count >= %(min_active)s"]
        if family:
            where.append("role_family_counts ? %(family)s")
        if category:
            where.append("category_counts ? %(category)s")
        if q:
            where.append("company ILIKE %(q)s")
        if agency == "direct":
            where.append("likely_agency = FALSE")
        elif agency == "agency":
            where.append("likely_agency = TRUE")
        params = {
            "family": family,
            "category": category,
            "q": f"%{q}%" if q else None,
            "min_active": max(1, int(min_active)),
            "limit": max(1, min(int(limit), 200)),
        }
        where_sql = " AND ".join(where)
        try:
            with self._cur() as cur:
                cur.execute(
                    f"""
                    SELECT {self._COMPANY_STATS_COLS}, {family_expr} AS family_active_count
                      FROM company_stats
                     WHERE {where_sql}
                     ORDER BY {order}, active_count DESC, company ASC
                     LIMIT %(limit)s
                    """,
                    params,
                )
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                cur.execute(
                    f"""
                    SELECT count(*)::int,
                           COALESCE(sum(COALESCE({family_expr}, active_count)), 0)::int,
                           (percentile_cont(0.5) WITHIN GROUP (ORDER BY median_salary))::int
                      FROM company_stats
                     WHERE {where_sql}
                    """,
                    params,
                )
                total, openings, median = cur.fetchone()
        except psycopg2.errors.UndefinedTable:
            logger.warning("company_stats view missing — run scripts/migrations/024_company_stats.sql")
            return {"rows": [], "total_matching": 0, "summary": {"companies": 0, "openings": 0, "median_salary": None}}
        return {
            "rows": rows,
            "total_matching": total,
            "summary": {"companies": total, "openings": openings, "median_salary": median},
        }

    def get_company_stats_one(self, company_name: str) -> dict | None:
        import psycopg2.errors

        try:
            with self._cur() as cur:
                cur.execute(
                    f"SELECT {self._COMPANY_STATS_COLS}, NULL::int AS family_active_count "
                    "FROM company_stats WHERE company_key = lower(%s)",
                    (company_name,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
        except psycopg2.errors.UndefinedTable:
            return None

    def get_company_top_reposted(self, company_name: str, limit: int = 5) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT pg.canonical_job_uuid, c.title, pg.repost_count, pg.reposts_365d,
                       pg.distinct_companies, pg.first_posted, pg.last_posted,
                       pg.latest_salary_min, pg.latest_salary_max
                  FROM (SELECT DISTINCT content_hash
                          FROM jobs
                         WHERE is_active = TRUE AND content_hash IS NOT NULL
                           AND (company_canonical = %s
                                OR (company_canonical IS NULL AND company_name = %s))) h
                  JOIN posting_groups pg ON pg.content_hash = h.content_hash
                  JOIN jobs c ON c.job_uuid = pg.latest_job_uuid
                 WHERE pg.repost_count >= 2
                 ORDER BY pg.repost_count DESC, pg.last_posted DESC
                 LIMIT %s
                """,
                (company_name, company_name, max(1, min(int(limit), 20))),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
```

Note: `self._cur()` is the existing non-transaction cursor helper used by `get_most_reposted`; psycopg2 returns `jsonb` columns as Python dicts, so `role_family_counts` needs no parsing. `logger` already exists at module top of `postgres_store.py` (check with `grep -n "^logger" src/mcf/lib/storage/postgres_store.py`; if absent add `logger = logging.getLogger(__name__)` with `import logging`).

- [ ] **Step 5: Add the crawl hook**

In `src/mcf/lib/pipeline/incremental_crawl.py`, directly after the `posting_groups` refresh block:

```python
        # company_stats feeds /companies (SGSAL-026). Depends on posting_groups. Non-fatal.
        try:
            store.refresh_company_stats()
        except Exception as e:  # noqa: BLE001
            print(f"Warning: company_stats refresh failed, skipping: {e}")
```

- [ ] **Step 6: Run the storage tests and the full suite**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main(['tests/test_company_stats.py','tests/test_smoke.py','-q']))"`
Expected: all PASS (the smoke suite proves the app still boots with the new abstract methods implemented).

- [ ] **Step 7: Commit**

```bash
git add src/mcf/lib/storage/base.py src/mcf/lib/storage/postgres_store.py src/mcf/lib/pipeline/incremental_crawl.py tests/test_company_stats.py
git commit -m "feat(SGSAL-026): company_stats storage methods + crawl-end refresh"
```

---

### Task 3: API — `/api/companies/stats` and profile extension

**Files:**
- Modify: `src/mcf/api/routes/companies.py` (models after `TopCompany`; new route after `get_popular_companies`; profile route end)
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: Task 2 storage methods.
- Produces: `GET /api/companies/stats?family&category&q&agency&min_active&sort&limit` → `CompanyStatsResponse {rows: CompanyStatsRow[], total_matching: int, summary: {companies: int, openings: int, median_salary: int|null}}`; `CompanyProfileResponse` gains `stats: CompanyStatsRow | None` and `top_reposted: list[CompanyReposted]`.

- [ ] **Step 1: Write the failing smoke tests** (append to `tests/test_smoke.py`)

```python
def test_companies_stats_shape(client):
    r = client.get("/api/companies/stats?min_active=1&limit=3")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"rows", "total_matching", "summary"}
    assert set(data["summary"]) == {"companies", "openings", "median_salary"}
    assert len(data["rows"]) <= 3
    for row in data["rows"]:
        for key in ("company", "active_count", "distinct_postings", "reposted_count",
                    "multi_company_count", "max_repost_count", "median_salary", "salary_sample",
                    "role_family_counts", "family_count", "top_family", "total_seen",
                    "first_seen", "likely_agency", "family_active_count"):
            assert key in row, key
        assert isinstance(row["role_family_counts"], dict)


def test_companies_stats_family_filter(client):
    r = client.get("/api/companies/stats?family=software_engineering&min_active=1&limit=5")
    assert r.status_code == 200
    for row in r.json()["rows"]:
        assert "software_engineering" in row["role_family_counts"]
        assert row["family_active_count"] >= 1


def test_companies_stats_rejects_bad_params(client):
    assert client.get("/api/companies/stats?agency=bogus").status_code == 422
    assert client.get("/api/companies/stats?sort=bogus").status_code == 422
    assert client.get("/api/companies/stats?limit=0").status_code == 422


def test_company_profile_has_stats_and_reposts(client):
    rows = client.get("/api/companies/stats?min_active=10&limit=1").json()["rows"]
    if not rows:
        pytest.skip("company_stats empty")
    r = client.get(f"/api/companies/{rows[0]['company']}/profile")
    assert r.status_code == 200
    data = r.json()
    assert "stats" in data and "top_reposted" in data
    assert isinstance(data["top_reposted"], list)
    if data["stats"] is not None:
        assert data["stats"]["company_key"] == rows[0]["company_key"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main(['tests/test_smoke.py','-q','-k','companies_stats or profile_has_stats']))"`
Expected: FAIL — 404 on `/api/companies/stats`, `KeyError: 'stats'` on the profile.

- [ ] **Step 3: Add models**

In `src/mcf/api/routes/companies.py`, after `class TopCompany`:

```python
class CompanyStatsRow(BaseModel):
    company_key: str
    company: str
    active_count: int
    distinct_postings: int
    reposted_count: int
    multi_company_count: int
    max_repost_count: int
    median_salary: int | None
    salary_sample: int
    role_family_counts: dict[str, int]
    family_count: int
    top_family: str | None
    category_counts: dict[str, int]
    total_seen: int
    first_seen: str | None
    last_seen: str | None
    likely_agency: bool
    family_active_count: int | None = None


class CompanyStatsSummary(BaseModel):
    companies: int
    openings: int
    median_salary: int | None


class CompanyStatsResponse(BaseModel):
    rows: list[CompanyStatsRow]
    total_matching: int
    summary: CompanyStatsSummary


class CompanyReposted(BaseModel):
    canonical_job_uuid: str
    title: str | None
    repost_count: int
    reposts_365d: int
    distinct_companies: int
    first_posted: str | None
    last_posted: str | None
    latest_salary_min: int | None
    latest_salary_max: int | None
```

Extend `CompanyProfileResponse` with two trailing fields:

```python
    stats: CompanyStatsRow | None = None
    top_reposted: list[CompanyReposted] = []
```

Add a helper next to `_to_iso`:

```python
def _stats_row(raw: dict | None) -> CompanyStatsRow | None:
    if not raw:
        return None
    return CompanyStatsRow(
        **{**raw, "first_seen": _to_iso(raw.get("first_seen")) or None,
           "last_seen": _to_iso(raw.get("last_seen")) or None,
           "role_family_counts": raw.get("role_family_counts") or {},
           "category_counts": raw.get("category_counts") or {}}
    )
```

- [ ] **Step 4: Add the stats route** (after `get_popular_companies`; `Literal` from `typing`)

```python
@router.get("/api/companies/stats")
@limiter.limit("60/minute")
@cache_response(
    ttl_seconds=TTL_DASHBOARD,
    key_prefix="companies:stats",
    key_builder=lambda **kw: f"{kw.get('family')}|{kw.get('category')}|{kw.get('q')}|{kw.get('agency')}|{kw.get('min_active')}|{kw.get('sort')}|{kw.get('limit')}",
)
def get_company_stats(
    request: Request,
    family: str | None = Query(default=None, max_length=64),
    category: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=80),
    agency: Literal["all", "direct", "agency"] = Query(default="all"),
    min_active: int = Query(default=10, ge=1, le=1000),
    sort: Literal["openings", "repost_rate", "median_salary"] = Query(default="openings"),
    limit: int = Query(default=50, ge=1, le=200),
    store: Storage = Depends(get_store),
) -> CompanyStatsResponse:
    """Ranked companies from the company_stats view (SGSAL-026)."""
    out = store.get_company_stats(
        family=family or None, category=category or None, q=(q or "").strip() or None,
        agency=agency, min_active=min_active, sort=sort, limit=limit,
    )
    return CompanyStatsResponse(
        rows=[_stats_row(r) for r in out["rows"]],
        total_matching=out["total_matching"],
        summary=CompanyStatsSummary(**out["summary"]),
    )
```

Check how `cache_response` passes kwargs to `key_builder` (`grep -n "key_builder" src/mcf/api/cache/response.py`); if it passes only the route kwargs, the lambda above is right; if it passes the `Request`, read `request.query_params` instead: `key_builder=lambda **kw: str(sorted(kw["request"].query_params.items()))`.

- [ ] **Step 5: Extend the profile route**

In `get_company_profile`, before `return CompanyProfileResponse(...)`:

```python
    stats = _stats_row(store.get_company_stats_one(company_name))
    top_reposted = [
        CompanyReposted(
            canonical_job_uuid=r["canonical_job_uuid"], title=r.get("title"),
            repost_count=r["repost_count"], reposts_365d=r["reposts_365d"],
            distinct_companies=r["distinct_companies"],
            first_posted=_to_iso(r.get("first_posted")) or None,
            last_posted=_to_iso(r.get("last_posted")) or None,
            latest_salary_min=r.get("latest_salary_min"), latest_salary_max=r.get("latest_salary_max"),
        )
        for r in store.get_company_top_reposted(company_name, limit=5)
    ]
```

and pass `stats=stats, top_reposted=top_reposted` into the response.

- [ ] **Step 6: Run the smoke suite**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main(['tests/test_smoke.py','-q']))"`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/mcf/api/routes/companies.py tests/test_smoke.py
git commit -m "feat(SGSAL-026): GET /api/companies/stats; profile returns stats + top_reposted"
```

---

### Task 4: Next.js proxy, client types, API client, role-family helpers

**Files:**
- Create: `frontend/app/api/companies/stats/route.ts`
- Create: `frontend/lib/roleFamilies.ts`
- Modify: `frontend/lib/types.ts` (after `CompanyProfile`), `frontend/lib/api.ts` (`companiesApi`)

**Interfaces:**
- Produces: `companiesApi.getStats(params: CompanyStatsParams): Promise<CompanyStatsResponse>`; types `CompanyStatsRow`, `CompanyStatsSummary`, `CompanyStatsResponse`, `CompanyReposted`, `CompanyStatsParams`; `CompanyProfile.stats?: CompanyStatsRow | null`, `CompanyProfile.top_reposted?: CompanyReposted[]`; `FAMILY_COLORS: Record<string, string>`, `familyLabel(key, rows?)`, `OTHER_FAMILY = 'other'`.

- [ ] **Step 1: Types** (append after `CompanyProfile` in `frontend/lib/types.ts`; add the two optional fields inside `CompanyProfile`)

```ts
// --- Company stats (SGSAL-026) ---

export interface CompanyStatsRow {
  company_key: string
  company: string
  active_count: number
  distinct_postings: number
  reposted_count: number
  multi_company_count: number
  max_repost_count: number
  median_salary: number | null
  salary_sample: number
  role_family_counts: Record<string, number>
  family_count: number
  top_family: string | null
  category_counts: Record<string, number>
  total_seen: number
  first_seen: string | null
  last_seen: string | null
  likely_agency: boolean
  family_active_count: number | null
}

export interface CompanyStatsSummary {
  companies: number
  openings: number
  median_salary: number | null
}

export interface CompanyStatsResponse {
  rows: CompanyStatsRow[]
  total_matching: number
  summary: CompanyStatsSummary
}

export interface CompanyReposted {
  canonical_job_uuid: string
  title: string | null
  repost_count: number
  reposts_365d: number
  distinct_companies: number
  first_posted: string | null
  last_posted: string | null
  latest_salary_min: number | null
  latest_salary_max: number | null
}

export type CompanyAgencyFilter = 'all' | 'direct' | 'agency'
export type CompanyStatsSort = 'openings' | 'repost_rate' | 'median_salary'

export interface CompanyStatsParams {
  family?: string
  category?: string
  q?: string
  agency?: CompanyAgencyFilter
  min_active?: number
  sort?: CompanyStatsSort
  limit?: number
}
```

In `CompanyProfile` add:

```ts
  // SGSAL-026 (absent on older cached responses)
  stats?: CompanyStatsRow | null
  top_reposted?: CompanyReposted[]
```

- [ ] **Step 2: API client** (inside `companiesApi` in `frontend/lib/api.ts`, after `getPopular`; extend the type import at the top of the file with `CompanyStatsParams, CompanyStatsResponse`)

```ts
  getStats: async (params: CompanyStatsParams = {}): Promise<CompanyStatsResponse> => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
    }
    const res = await fetch(`/api/companies/stats?${qs.toString()}`)
    if (!res.ok) throw new Error('Failed to fetch company stats')
    return res.json()
  },
```

- [ ] **Step 3: Next route handler**

```ts
// frontend/app/api/companies/stats/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 900

export const revalidate = REVALIDATE_SECONDS

const ALLOWED = new Set(['family', 'category', 'q', 'agency', 'min_active', 'sort', 'limit'])

export async function GET(request: NextRequest) {
  const qs = new URLSearchParams()
  for (const [k, v] of request.nextUrl.searchParams.entries()) {
    if (ALLOWED.has(k) && v) qs.set(k, v.slice(0, 80))
  }
  qs.sort()
  const key = qs.toString()
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(`${API_BASE_URL}/api/companies/stats?${key}`, {
          next: { revalidate: REVALIDATE_SECONDS },
        })
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      [`companies-stats-${key}`],
      { revalidate: REVALIDATE_SECONDS },
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[companies/stats]', err)
    return NextResponse.json({ detail: 'Failed to fetch company stats' }, { status: 502 })
  }
}
```

- [ ] **Step 4: Role-family helpers**

Before writing colours, load the `dataviz` skill and use its categorical palette if it differs from the Tailwind hexes below; keep `other` neutral.

```ts
// frontend/lib/roleFamilies.ts
import type { RoleFamilyRow } from './types'

export const OTHER_FAMILY = 'other'

/** Fallback labels when the role-families endpoint has not loaded. Keys = role_families.key. */
export const FAMILY_LABELS: Record<string, string> = {
  other: 'Other',
  software_engineering: 'Software Engineering',
  data_ai_analytics: 'Data, AI & Analytics',
  it_infra_support_security: 'IT Infrastructure, Support & Security',
  sales_business_dev: 'Sales & Business Development',
  marketing_comms: 'Marketing & Communications',
  finance_accounting: 'Finance & Accounting',
  banking_financial_services: 'Banking & Financial Services',
  legal_compliance_cosec: 'Legal, Compliance & Corporate Secretarial',
  human_resources: 'Human Resources',
  admin_office_support: 'Admin & Office Support',
  customer_service: 'Customer Service',
  operations_strategy_pm: 'Operations, Strategy & Project Management',
  procurement_supply_chain_logistics: 'Procurement, Supply Chain & Logistics',
  warehouse_drivers_delivery: 'Warehouse, Drivers & Delivery',
  engineering_manufacturing: 'Engineering & Manufacturing',
  trades_technicians: 'Trades & Technicians',
  construction_architecture_property: 'Construction, Architecture & Property',
  healthcare_allied: 'Healthcare & Allied Health',
  education_social_services: 'Education & Social Services',
  fnb_hospitality: 'F&B & Hospitality',
  retail_beauty: 'Retail & Beauty',
  cleaning_security_general_labour: 'Cleaning, Security & General Labour',
  creative_design: 'Creative & Design',
  science_research_lab: 'Science, Research & Lab',
}

/** Stable colour per family (same family = same colour on every page). */
export const FAMILY_COLORS: Record<string, string> = {
  software_engineering: '#6366f1',
  data_ai_analytics: '#8b5cf6',
  it_infra_support_security: '#0ea5e9',
  sales_business_dev: '#f97316',
  marketing_comms: '#ec4899',
  finance_accounting: '#10b981',
  banking_financial_services: '#059669',
  legal_compliance_cosec: '#64748b',
  human_resources: '#f59e0b',
  admin_office_support: '#a3a3a3',
  customer_service: '#14b8a6',
  operations_strategy_pm: '#3b82f6',
  procurement_supply_chain_logistics: '#0891b2',
  warehouse_drivers_delivery: '#78716c',
  engineering_manufacturing: '#84cc16',
  trades_technicians: '#a16207',
  construction_architecture_property: '#ca8a04',
  healthcare_allied: '#f43f5e',
  education_social_services: '#d946ef',
  fnb_hospitality: '#fb7185',
  retail_beauty: '#fda4af',
  cleaning_security_general_labour: '#9ca3af',
  creative_design: '#c084fc',
  science_research_lab: '#22d3ee',
  other: '#cbd5e1',
}

export function familyLabel(key: string, rows?: RoleFamilyRow[]): string {
  return rows?.find((r) => r.role_family === key)?.display_name ?? FAMILY_LABELS[key] ?? key
}

export function familyColor(key: string): string {
  return FAMILY_COLORS[key] ?? FAMILY_COLORS[OTHER_FAMILY]
}

/** Top-N families by count plus an aggregated "other" slice. */
export function topFamilies(
  counts: Record<string, number>,
  n = 3,
): Array<{ key: string; count: number }> {
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const top = sorted.slice(0, n).map(([key, count]) => ({ key, count }))
  const rest = sorted.slice(n).reduce((s, [, c]) => s + c, 0)
  if (rest > 0) top.push({ key: OTHER_FAMILY, count: rest })
  return top
}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p .`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/api/companies/stats/route.ts frontend/lib/roleFamilies.ts frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(SGSAL-026): company stats proxy route, client types, role-family helpers"
```

---

### Task 5: `/companies` page — filters in URL, summary strip, sortable table, role-mix bar

**Files:**
- Create: `frontend/app/companies/RoleMixBar.tsx`, `frontend/app/companies/CompanyStatsTable.tsx`
- Rewrite: `frontend/app/companies/page.tsx`

**Interfaces:**
- Consumes: `companiesApi.getStats`, `dashboardApi.getRoleFamilies`, helpers from `lib/roleFamilies.ts`, `monthYear` from `lib/repost.ts`, `Card, CardBody, PageHeader, EmptyState` from `@/components/design`.
- Produces: `<RoleMixBar counts total familyRows? />`, `<CompanyStatsTable rows sort onSort familyRows selectedFamily />`.

- [ ] **Step 1: `RoleMixBar`**

```tsx
// frontend/app/companies/RoleMixBar.tsx
'use client'

import type { RoleFamilyRow } from '@/lib/types'
import { familyColor, familyLabel, topFamilies } from '@/lib/roleFamilies'

export function RoleMixBar({
  counts,
  total,
  familyRows,
  height = 8,
}: {
  counts: Record<string, number>
  total: number
  familyRows?: RoleFamilyRow[]
  height?: number
}) {
  if (!total) return null
  const slices = topFamilies(counts, 3)
  const title = slices.map((s) => `${familyLabel(s.key, familyRows)}: ${s.count}`).join(' · ')
  return (
    <div
      className="flex w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
      style={{ height }}
      title={title}
      role="img"
      aria-label={`Role mix: ${title}`}
    >
      {slices.map((s) => (
        <div
          key={s.key}
          style={{ width: `${(s.count / total) * 100}%`, backgroundColor: familyColor(s.key) }}
        />
      ))}
    </div>
  )
}
```

- [ ] **Step 2: `CompanyStatsTable`**

```tsx
// frontend/app/companies/CompanyStatsTable.tsx
'use client'

import Link from 'next/link'
import { ArrowDown, Building2 } from 'lucide-react'
import type { CompanyStatsRow, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { monthYear } from '@/lib/repost'
import { familyLabel } from '@/lib/roleFamilies'
import { RoleMixBar } from './RoleMixBar'

const fmtMoney = (v: number | null) => (v == null ? '—' : `$${(v / 1000).toFixed(1)}k`)
const pct = (num: number, den: number) => (den ? Math.round((num / den) * 100) : 0)

function SortHeader({
  label, value, current, onSort, className = '',
}: { label: string; value: CompanyStatsSort; current: CompanyStatsSort; onSort: (s: CompanyStatsSort) => void; className?: string }) {
  const active = current === value
  return (
    <th className={`px-3 py-2 font-medium ${className}`}>
      <button
        type="button"
        onClick={() => onSort(value)}
        className={`inline-flex items-center gap-1 hover:text-indigo-600 dark:hover:text-indigo-400 ${active ? 'text-indigo-600 dark:text-indigo-400' : ''}`}
        aria-sort={active ? 'descending' : 'none'}
      >
        {label}
        {active && <ArrowDown size={12} />}
      </button>
    </th>
  )
}

export function CompanyStatsTable({
  rows, sort, onSort, familyRows, selectedFamily,
}: {
  rows: CompanyStatsRow[]
  sort: CompanyStatsSort
  onSort: (s: CompanyStatsSort) => void
  familyRows?: RoleFamilyRow[]
  selectedFamily?: string
}) {
  return (
    <>
      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="px-3 py-2 font-medium">Company</th>
              <SortHeader label={selectedFamily ? `${familyLabel(selectedFamily, familyRows)} openings` : 'Openings'} value="openings" current={sort} onSort={onSort} className="text-right" />
              <SortHeader label="Repost rate" value="repost_rate" current={sort} onSort={onSort} />
              <SortHeader label="Median salary" value="median_salary" current={sort} onSort={onSort} className="text-right" />
              <th className="px-3 py-2 font-medium">Role mix</th>
              <th className="px-3 py-2 font-medium whitespace-nowrap">Hiring since</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((r) => {
              const rate = pct(r.reposted_count, r.active_count)
              const openings = selectedFamily ? (r.family_active_count ?? 0) : r.active_count
              return (
                <tr key={r.company_key} className="text-slate-700 dark:text-slate-200">
                  <td className="px-3 py-2.5 max-w-[20rem]">
                    <Link href={`/company/${encodeURIComponent(r.company)}`} className="font-medium hover:text-indigo-600 dark:hover:text-indigo-400 truncate block" title={r.company}>
                      {r.company}
                    </Link>
                    <div className="text-xs text-slate-400 dark:text-slate-500">
                      across {r.family_count} role {r.family_count === 1 ? 'family' : 'families'}
                      {r.multi_company_count > 0 && ' · ads also under other names'}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {openings.toLocaleString()}
                    {!selectedFamily && r.distinct_postings < r.active_count && (
                      <div className="text-xs text-slate-400">{r.distinct_postings.toLocaleString()} distinct</div>
                    )}
                  </td>
                  <td className="px-3 py-2.5 min-w-[9rem]">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">
                        <div className="h-full rounded-full bg-amber-400" style={{ width: `${rate}%` }} />
                      </div>
                      <span className="tabular-nums text-xs w-8 text-right">{rate}%</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {fmtMoney(r.median_salary)}
                    {r.salary_sample > 0 && <div className="text-xs text-slate-400">{r.salary_sample} with pay</div>}
                  </td>
                  <td className="px-3 py-2.5 min-w-[8rem]">
                    <RoleMixBar counts={r.role_family_counts} total={r.active_count} familyRows={familyRows} />
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-slate-500 dark:text-slate-400">{monthYear(r.first_seen) || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="md:hidden space-y-2">
        {rows.map((r) => {
          const rate = pct(r.reposted_count, r.active_count)
          const openings = selectedFamily ? (r.family_active_count ?? 0) : r.active_count
          return (
            <Link key={r.company_key} href={`/company/${encodeURIComponent(r.company)}`} className="block rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3">
              <div className="flex items-center gap-2">
                <Building2 size={14} className="shrink-0 text-slate-400" />
                <span className="flex-1 truncate font-medium text-slate-800 dark:text-slate-200">{r.company}</span>
                <span className="tabular-nums text-sm text-slate-600 dark:text-slate-300">{openings.toLocaleString()}</span>
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span>{rate}% reposted · {fmtMoney(r.median_salary)} median</span>
                <span>{monthYear(r.first_seen)}</span>
              </div>
              <div className="mt-2"><RoleMixBar counts={r.role_family_counts} total={r.active_count} familyRows={familyRows} height={6} /></div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
```

- [ ] **Step 3: Rewrite `page.tsx`**

```tsx
// frontend/app/companies/page.tsx
'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { Building2, Search } from 'lucide-react'
import { companiesApi, dashboardApi } from '@/lib/api'
import type { CompanyAgencyFilter, CompanyStatsResponse, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { familyLabel } from '@/lib/roleFamilies'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, EmptyState, PageHeader } from '@/components/design'
import { CompanyStatsTable } from './CompanyStatsTable'

const MIN_ACTIVE_OPTIONS = [10, 3, 1] as const
const SORTS: CompanyStatsSort[] = ['openings', 'repost_rate', 'median_salary']
const AGENCIES: Array<{ value: CompanyAgencyFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'direct', label: 'Direct employers' },
  { value: 'agency', label: 'Staffing agencies' },
]

const selectCls = 'rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500'

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

function CompaniesExplorer() {
  const router = useRouter()
  const sp = useSearchParams()

  const family = sp.get('family') ?? ''
  const category = sp.get('category') ?? ''
  const agency = (sp.get('agency') as CompanyAgencyFilter) || 'all'
  const sort = (SORTS.includes(sp.get('sort') as CompanyStatsSort) ? sp.get('sort') : 'openings') as CompanyStatsSort
  const minActive = Number(sp.get('min_active')) || 10
  const [query, setQuery] = useState(sp.get('q') ?? '')
  const q = useDebounced(query.trim(), 300)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(sp.toString())
    if (value) next.set(key, value); else next.delete(key)
    router.replace(`/companies?${next.toString()}`, { scroll: false })
  }
  useEffect(() => { if ((sp.get('q') ?? '') !== q) setParam('q', q) }, [q]) // eslint-disable-line react-hooks/exhaustive-deps

  const { data: families = [] } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, { revalidateOnFocus: false })

  const params = { family, category, q, agency, min_active: q ? 1 : minActive, sort, limit: 100 }
  const key = ['companies-stats', JSON.stringify(params)]
  const { data, isLoading, error } = useSWR<CompanyStatsResponse>(key, () => companiesApi.getStats(params), { revalidateOnFocus: false, keepPreviousData: true })

  // industry options come from the data itself (MCF categories seen on the current rows)
  const categories = useMemo(() => {
    const set = new Set<string>(category ? [category] : [])
    for (const r of data?.rows ?? []) for (const c of Object.keys(r.category_counts)) set.add(c)
    return Array.from(set).sort()
  }, [data, category])

  const summary = data?.summary
  const subtitle = family || category
    ? `Who is hiring for ${[family && familyLabel(family, families), category].filter(Boolean).join(' · ')}`
    : 'Who is hiring, what they pay, and how much of it is the same ad again'

  return (
    <div className="space-y-5">
      <PageHeader title="Companies" subtitle={subtitle} />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[12rem]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
          <input type="text" placeholder="Search companies…" value={query} onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <select aria-label="Role family" className={selectCls} value={family} onChange={(e) => setParam('family', e.target.value)}>
          <option value="">All role families</option>
          {families.filter((f) => f.role_family !== 'other').map((f) => (
            <option key={f.role_family} value={f.role_family}>{f.display_name}</option>
          ))}
        </select>
        <select aria-label="Industry" className={selectCls} value={category} onChange={(e) => setParam('category', e.target.value)}>
          <option value="">All industries</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <div role="group" aria-label="Employer type" className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-sm">
          {AGENCIES.map((a) => (
            <button key={a.value} type="button" onClick={() => setParam('agency', a.value === 'all' ? '' : a.value)}
              className={`px-2.5 py-1.5 ${agency === a.value ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'}`}>
              {a.label}
            </button>
          ))}
        </div>
        <select aria-label="Minimum openings" className={selectCls} value={minActive} disabled={!!q} onChange={(e) => setParam('min_active', e.target.value === '10' ? '' : e.target.value)}>
          {MIN_ACTIVE_OPTIONS.map((n) => <option key={n} value={n}>{n === 1 ? 'Any openings' : `${n}+ openings`}</option>)}
        </select>
      </div>

      {/* Summary strip */}
      {summary && summary.companies > 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.companies.toLocaleString()}</span> companies ·{' '}
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.openings.toLocaleString()}</span> openings
          {summary.median_salary != null && <> · median <span className="font-medium text-slate-700 dark:text-slate-200">${summary.median_salary.toLocaleString()}</span>/mo</>}
          {data && data.rows.length < data.total_matching && <> · showing top {data.rows.length}</>}
        </p>
      )}
      <p className="text-xs text-slate-400 dark:text-slate-500 -mt-3">
        Repost rate = share of a company&apos;s live postings whose text has been posted before. Agencies are identified by posting across 10+ role families or by name.
      </p>

      {/* Results */}
      <Card>
        <CardBody>
          {isLoading && !data && <div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}
          {error && <EmptyState icon={Building2} message="Couldn't load companies" description="Try again later." />}
          {data && data.rows.length === 0 && (
            <EmptyState icon={Building2} message="No companies match"
              description={minActive > 1 && !q ? 'Lower the minimum openings or clear a filter.' : 'Try a different name or filter.'} />
          )}
          {data && data.rows.length > 0 && (
            <CompanyStatsTable rows={data.rows} sort={sort} onSort={(s) => setParam('sort', s === 'openings' ? '' : s)} familyRows={families} selectedFamily={family || undefined} />
          )}
        </CardBody>
      </Card>
    </div>
  )
}

export default function CompaniesPage() {
  return (
    <Layout userSlot={<NavUserActions />}>
      <Suspense fallback={<div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}>
        <CompaniesExplorer />
      </Suspense>
    </Layout>
  )
}
```

- [ ] **Step 4: Typecheck and run the dev server against the live API**

Run: `cd frontend && npx tsc --noEmit -p .` → clean.
Then with the backend running (`uv run python -m uvicorn mcf.api.server:app --reload --port 8000`) and `npm run dev`, open `http://localhost:3000/companies?family=data_ai_analytics` and check: the table loads, sorting changes order, the agency toggle filters, the URL carries the filters, the mobile layout shows cards at 375 px.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/companies/
git commit -m "feat(SGSAL-026): /companies explorer — role-family/industry filters, repost rate, role mix"
```

---

### Task 6: `/company/[name]` — repost tile + card, role-family and industry charts

**Files:**
- Modify: `frontend/app/company/[name]/CompanyContent.tsx` (imports; stat row ~line 180; new cards before "Hiring patterns")

**Interfaces:**
- Consumes: `profile.stats`, `profile.top_reposted` (Task 4 types), `monthYear`, `salaryRangeText` from `lib/repost.ts`, `familyLabel`, `familyColor` from `lib/roleFamilies.ts`, `dashboardApi.getRoleFamilies`.

- [ ] **Step 1: Imports and data**

Add to imports: `Repeat` from `lucide-react`; `import { monthYear, salaryRangeText } from '@/lib/repost'`; `import { familyColor, familyLabel } from '@/lib/roleFamilies'`; `import type { RoleFamilyRow } from '@/lib/types'`; `dashboardApi` alongside `companiesApi`.

Inside `CompanyContent` after the profile SWR:

```tsx
  const { data: families } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, { revalidateOnFocus: false })
```

After `empTypes`:

```tsx
  const stats = profile.stats ?? null
  const topReposted = profile.top_reposted ?? []
  const repostRate = stats && stats.active_count ? Math.round((stats.reposted_count / stats.active_count) * 100) : null
  const familyMix = stats
    ? Object.entries(stats.role_family_counts).sort((a, b) => b[1] - a[1]).slice(0, 8)
        .map(([key, value]) => ({ key, name: familyLabel(key, families), value }))
    : []
  const industryMix = stats
    ? Object.entries(stats.category_counts).sort((a, b) => b[1] - a[1]).slice(0, 8)
        .map(([name, value]) => ({ name, value }))
    : []
  const showStatsCharts = !!stats && stats.active_count >= 3
```

- [ ] **Step 2: Fifth stat tile**

Change the stat grid class to `grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3` and append to the tiles array:

```tsx
            {
              icon: <Repeat size={18} className="text-amber-500" />,
              label: 'Repost rate',
              value: repostRate != null ? `${repostRate}%` : '—',
            },
```

- [ ] **Step 3: Reposting card** (insert after the Salary overview card, before Latest openings)

```tsx
        {stats && (
          <Card>
            <CardBody>
              <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-1 flex items-center gap-2">
                <Repeat size={16} /> Reposting
              </h2>
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
                {stats.reposted_count.toLocaleString()} of {stats.active_count.toLocaleString()} live postings have been posted before
                {stats.distinct_postings < stats.active_count && <> · {stats.distinct_postings.toLocaleString()} distinct ads behind {stats.active_count.toLocaleString()} listings</>}
                {stats.max_repost_count >= 2 && <> · one ad posted {stats.max_repost_count}×</>}
                {stats.multi_company_count > 0 && <> · {stats.multi_company_count.toLocaleString()} also appear under other company names</>}
                {' · across '}{stats.family_count} role {stats.family_count === 1 ? 'family' : 'families'}
              </p>
              {topReposted.length === 0 ? (
                <p className="text-sm text-slate-400 dark:text-slate-500 py-2">No reposted ads among the live postings.</p>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {topReposted.map((r) => (
                    <div key={r.canonical_job_uuid} className="flex items-start justify-between gap-3 py-2">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate" title={r.title ?? ''}>{r.title ?? '—'}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">
                          {r.repost_count}× · {monthYear(r.first_posted) || '?'} – {monthYear(r.last_posted) || '?'}
                          {r.distinct_companies >= 2 && <> · under {r.distinct_companies} company names</>}
                        </div>
                      </div>
                      <div className="shrink-0 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {salaryRangeText(r.latest_salary_min, r.latest_salary_max) ?? ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        )}
```

- [ ] **Step 4: Role-family and industry charts** (insert before the existing "Hiring patterns" grid; same Recharts pattern as the position-level chart, bar colour per family)

```tsx
        {showStatsCharts && (familyMix.length > 0 || industryMix.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {familyMix.length > 0 && (
              <Card>
                <CardBody>
                  <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-4">Hiring by role family</h2>
                  <ResponsiveContainer width="100%" height={Math.max(160, familyMix.length * 28)}>
                    <BarChart data={familyMix} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                      <XAxis type="number" hide />
                      <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11, fill: 'currentColor' }} className="text-slate-600 dark:text-slate-400" />
                      <Tooltip formatter={(v: number) => [v, 'live postings']} contentStyle={{ fontSize: 12 }} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {familyMix.map((d) => <Cell key={d.key} fill={familyColor(d.key)} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardBody>
              </Card>
            )}
            {industryMix.length > 0 && (
              <Card>
                <CardBody>
                  <h2 className="text-base font-semibold text-slate-700 dark:text-slate-300 mb-4">Industries</h2>
                  <ResponsiveContainer width="100%" height={Math.max(160, industryMix.length * 28)}>
                    <BarChart data={industryMix} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
                      <XAxis type="number" hide />
                      <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11, fill: 'currentColor' }} className="text-slate-600 dark:text-slate-400" />
                      <Tooltip formatter={(v: number) => [v, 'live postings']} contentStyle={{ fontSize: 12 }} />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {industryMix.map((_, i) => <Cell key={i} fill={i === 0 ? '#0ea5e9' : '#bae6fd'} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardBody>
              </Card>
            )}
          </div>
        )}
```

- [ ] **Step 5: Typecheck and check in the browser**

Run: `cd frontend && npx tsc --noEmit -p .` → clean. Open `/company/RECRUIT%20EXPRESS%20PTE%20LTD` (high repost rate, many families) and a direct employer from the explorer's "Direct employers" toggle; confirm the fifth tile, Reposting card and both charts render, and a company with `stats: null` hides them.

- [ ] **Step 6: Commit**

```bash
git add "frontend/app/company/[name]/CompanyContent.tsx"
git commit -m "feat(SGSAL-026): company profile — repost rate, reposting card, role-family and industry charts"
```

---

### Task 7: Docs, ticket, deploy, verify

**Files:**
- Modify: `tickets/SGSAL-026.md` (checklist), `CLAUDE.md` (Design facts: add fact 10 for `company_stats`), `src/mcf/api/README.md` (endpoint list), `frontend/app/components/README.md` if it lists page components.

- [ ] **Step 1: CLAUDE.md design fact**

Append to the Design facts list:

```markdown
10. **Company stats (SGSAL-026):** `company_stats` (materialised view, migration 024, refreshed at crawl end right after `posting_groups`) holds one row per company: openings, distinct postings, repost share, multi-company share, median salary, `role_family_counts` / `category_counts` jsonb, history, and `likely_agency` (≥ 10 role families or an agency-like name). `/api/companies/stats` and the company profile read it; nothing aggregates `jobs` per request. Copy names facts, never judgements.
```

- [ ] **Step 2: API README** — add `GET /api/companies/stats` with its query params and the profile's new fields, next to the existing companies endpoints.

- [ ] **Step 3: Tick the SGSAL-026 checklist, set `status: done`, `updated:` today; update the TICKETS.md row.**

- [ ] **Step 4: Full test run, typecheck, push**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv('.env'); import pytest, sys; sys.exit(pytest.main(['tests/','-q']))"` → all PASS; `cd frontend && npx tsc --noEmit -p .` → clean.

```bash
git add CLAUDE.md src/mcf/api/README.md tickets/SGSAL-026.md TICKETS.md
git commit -m "docs(SGSAL-026): company_stats design fact, API docs, ticket closed"
git push origin master
```

- [ ] **Step 5: Verify production**

`railway deployment list` shows the new deployment SUCCESS; `curl https://mcf-production-5485.up.railway.app/api/companies/stats?min_active=10&limit=2` returns rows; Vercel `/companies?family=data_ai_analytics` renders. Record the production timings in the ticket.

---

## Self-review

- **Spec coverage:** view columns (T1), refresh hook (T2), stats route + profile extension (T3), proxy/types (T4), explorer with filters in URL, summary strip, table, mobile, empty state (T5), profile tile/card/charts, `stats: null` handling (T6), docs/rollout (T7). Error handling: `UndefinedTable` → empty (T2), crawl refresh non-fatal (T2), 422 on bad params (T3). Testing: constant (T1), storage invariants (T2), route shapes (T3), `tsc` (T4–6).
- **Type consistency:** `family_active_count` is `int | None` in storage, pydantic and TS; `agency` values `all|direct|agency` everywhere; `sort` values `openings|repost_rate|median_salary` everywhere; `company_key` is the join key in `get_company_stats_one` and the TS key prop.
- **Open check for the implementer:** `cache_response`'s `key_builder` kwargs (T3 step 4 note) and whether `logger` exists in `postgres_store.py` (T2 step 4 note). Both are verified in-step, not deferred.
