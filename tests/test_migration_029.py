"""SGSAL-032: keep the ensure_schema view constant identical to migration 029 (company_stats v4)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "scripts" / "migrations" / "029_company_stats_v4.sql"
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


def test_ad_text_rules_never_flag_public_bodies():
    """The licence-number and client-wording rules both exclude public bodies."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "(a.registered_agency OR (a.ea_licence_ads >= 2 AND NOT a.public_body))" in sql
    assert "NOT a.public_body\n        AND a.described_ads >= 10" in sql


def test_typical_pay_counts_standard_ads_only():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.count("pay_kind = 'standard'") >= 3  # company median, its sample, per-family medians


def test_crawl_links_names_and_upgrades_the_view_before_refreshing():
    src = (ROOT / "src" / "mcf" / "lib" / "pipeline" / "incremental_crawl.py").read_text(encoding="utf-8")
    assert src.index("store.link_company_name_variants()") < src.index("store.refresh_posting_groups()")
    assert src.index("store.upgrade_company_stats_view()") < src.index("store.refresh_company_stats()")
