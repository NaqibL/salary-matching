"""SGSAL-028: keep the ensure_schema view constant identical to migration 027 (company_stats v3)."""

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "scripts" / "migrations" / "027_company_stats_v3.sql"
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


def test_public_bodies_are_never_name_tagged():
    """The name rule must be fenced by the public-body SSIC exclusion and the ministry guard."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "!~ '^(72|84|85|86|91|94)'" in sql
    assert "!~* 'ministry'" in sql
    assert "c.source = 'mcf' AND c.ssic_code_2020 IS NOT NULL" in sql
