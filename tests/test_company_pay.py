"""Pay kinds: the Python rule and the SQL rule in the company_stats view must agree."""

import json
import os

import pytest

from mcf.lib.companies.pay import pay_kind

CASES = [
    # (salary_min, salary_max, employment types, expected kind)
    (4000, 5000, ["Full Time"], "standard"),
    (4000, None, ["Permanent"], "standard"),
    (3000, 4000, ["Part Time", "Full Time", "Permanent"], "standard"),  # ticks every box
    (3000, 4000, ["Contract"], "standard"),
    (3000, 4000, [], "standard"),
    (12, 15, ["Part Time"], "hourly"),
    (13, 13, ["Permanent", "Full Time"], "hourly"),
    (150, 150, ["Full Time"], "daily"),
    (1500, 1800, ["Part Time"], "part_time"),
    (1500, 1800, ["Contract", "Part Time"], "part_time"),
    (800, 1000, ["Internship/Attachment"], "internship"),
    (800, 1000, ["Internship/Attachment", "Full Time"], "standard"),
    (1, 1, ["Full Time"], None),  # placeholder
    (None, None, ["Full Time"], None),
    (None, 5000, ["Full Time"], None),
]


@pytest.mark.parametrize("lo,hi,types,expected", CASES)
def test_pay_kind(lo, hi, types, expected):
    assert pay_kind(lo, hi, types) == expected


def test_sql_rule_matches_python_rule():
    """Evaluate the view's CASE expression in Postgres for every case above."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    import psycopg2

    from mcf.lib.storage.postgres_store import _COMPANY_STATS_VIEW_SQL

    start = _COMPANY_STATS_VIEW_SQL.index("CASE WHEN j.salary_min IS NULL OR COALESCE(j.salary_max, j.salary_min) < 5")
    end = _COMPANY_STATS_VIEW_SQL.index("AS pay_kind", start)
    case_sql = _COMPANY_STATS_VIEW_SQL[start:end]
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor()
        for lo, hi, types, expected in CASES:
            cur.execute(
                f"SELECT {case_sql} FROM (SELECT %s::int AS salary_min, %s::int AS salary_max, "
                "%s::text AS employment_types_json) j",
                (lo, hi, json.dumps(types)),
            )
            assert cur.fetchone()[0] == expected, (lo, hi, types)
    finally:
        conn.close()
