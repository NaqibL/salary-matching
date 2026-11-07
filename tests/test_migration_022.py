"""SGSAL-024: keep the ensure_schema view constant identical to migration 022."""

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "scripts" / "migrations" / "022_posting_groups.sql"
START = "CREATE MATERIALIZED VIEW IF NOT EXISTS posting_groups AS"
END = "GROUP BY content_hash"


def test_view_constant_matches_migration():
    from mcf.lib.storage.postgres_store import _POSTING_GROUPS_VIEW_SQL

    sql = MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = sql.index(START)
    end = sql.index(END, start) + len(END)
    expected = sql[start:end]
    actual = _POSTING_GROUPS_VIEW_SQL.replace("\r\n", "\n").strip().rstrip(";").rstrip()
    assert actual == expected
