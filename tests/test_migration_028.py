"""SGSAL-030: keep the ensure_schema view constant identical to migration 028 (market_stats)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "scripts" / "migrations" / "028_market_stats.sql"
START = "CREATE MATERIALIZED VIEW IF NOT EXISTS market_stats AS"
END = "UNION ALL SELECT *, now() FROM bucket"


def test_view_constant_matches_migration():
    from mcf.lib.storage.postgres_store import _MARKET_STATS_VIEW_SQL

    sql = MIGRATION.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = sql.index(START)
    end = sql.index(END, start) + len(END)
    assert _MARKET_STATS_VIEW_SQL.replace("\r\n", "\n").strip().rstrip(";").rstrip() == sql[start:end]


def test_ensure_schema_orders_market_stats_after_its_sources():
    """market_stats joins posting_groups and company_stats, so a fresh DB needs both first."""
    src = (ROOT / "src" / "mcf" / "lib" / "storage" / "postgres_store.py").read_text(encoding="utf-8")
    body = src[src.index("migrations = [") :]
    assert body.index("_POSTING_GROUPS_VIEW_SQL,") < body.index("_MARKET_STATS_VIEW_SQL,")
    assert body.index("_COMPANY_STATS_VIEW_SQL,") < body.index("_MARKET_STATS_VIEW_SQL,")


def test_crawl_refreshes_market_stats_after_company_stats():
    src = (ROOT / "src" / "mcf" / "lib" / "pipeline" / "incremental_crawl.py").read_text(encoding="utf-8")
    assert src.index("store.refresh_company_stats()") < src.index("store.refresh_market_stats()")
