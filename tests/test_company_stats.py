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
    for r in out["rows"]:
        assert "family_median_salary" in r and "family_salary_sample" in r
        if r["family_salary_sample"]:
            assert r["family_median_salary"] is not None


def test_stats_agency_filter_and_sorts(store):
    direct = store.get_company_stats(agency="direct", min_active=1, limit=5)
    assert all(r["is_agency"] is False for r in direct["rows"])
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
