"""SGSAL-028: keep the ensure_schema view constant identical to migration 026 (company_stats v2)."""

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "scripts" / "migrations" / "026_company_stats_v2.sql"
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
