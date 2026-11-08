"""SGSAL-028: keep the ensure_schema companies DDL identical to migration 025."""

from pathlib import Path

MIGRATION = Path(__file__).resolve().parent.parent / "scripts" / "migrations" / "025_companies.sql"
START = "CREATE TABLE IF NOT EXISTS companies ("
END = "fetched_at       TIMESTAMPTZ NOT NULL DEFAULT now()\n)"


def test_companies_ddl_matches_migration():
    from mcf.lib.storage.postgres_store import _COMPANIES_DDL

    sql = MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = sql.index(START)
    end = sql.index(END, start) + len(END)
    assert _COMPANIES_DDL.replace("\r\n", "\n").strip().rstrip(";").rstrip() == sql[start:end]


def test_ensure_schema_creates_companies_before_company_stats():
    """company_stats LEFT JOINs companies, so a fresh DB needs the table first (review finding)."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "src" / "mcf" / "lib" / "storage" / "postgres_store.py").read_text(
        encoding="utf-8"
    )
    list_start = src.index("migrations = [")
    body = src[list_start:]
    assert body.index("_COMPANIES_DDL,") < body.index("_COMPANY_STATS_VIEW_SQL,")
