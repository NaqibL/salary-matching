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
    # pay ranking: figures backed by 10+ salaried ads lead, highest first; thinner rows follow
    by_pay = store.get_company_stats(sort="median_salary", min_active=1, limit=50)["rows"]
    solid = [r["salary_sample"] >= 10 for r in by_pay]
    assert solid == sorted(solid, reverse=True)
    pays = [r["median_salary"] for r in by_pay if r["salary_sample"] >= 10]
    assert pays == sorted(pays, reverse=True)
    fam_pay = store.get_company_stats(sort="median_salary", family="healthcare_allied", min_active=1, limit=50)["rows"]
    fam_solid = [(r["family_salary_sample"] or 0) >= 10 for r in fam_pay]
    assert fam_solid == sorted(fam_solid, reverse=True)
    fam_pays = [r["family_median_salary"] for r in fam_pay if (r["family_salary_sample"] or 0) >= 10]
    assert fam_pays == sorted(fam_pays, reverse=True)


def test_name_search_ranks_and_escapes(store):
    top = store.get_company_stats(min_active=1, limit=1)["rows"]
    if not top:
        pytest.skip("company_stats empty")
    name = top[0]["company"]
    exact = store.get_company_stats(q=name.upper(), min_active=1, limit=5)["rows"]
    assert exact[0]["company_key"] == top[0]["company_key"]
    # a short name's full form (q_also) is searched as well and outranks plain substring hits
    via_also = store.get_company_stats(q="zz-no-such-text", q_also=[name], min_active=1, limit=5)["rows"]
    assert via_also and via_also[0]["company_key"] == top[0]["company_key"]
    assert store.get_company_stats(q="%", min_active=1, limit=5)["rows"] == []
    assert store.get_company_stats(q="_", min_active=1, limit=5)["total_matching"] <= store.get_company_stats(
        min_active=1, limit=1
    )["total_matching"]


def test_open_jobs_and_counts_agree(store):
    top = store.get_company_stats(min_active=1, limit=1)["rows"]
    if not top:
        pytest.skip("company_stats empty")
    name = top[0]["company"]
    counts = store.get_company_job_counts(name)
    jobs = store.get_open_jobs_by_company(name)
    assert counts["active"] == len(jobs) <= counts["total"]
    assert all(j["role_family"] for j in jobs)
    assert store.get_company_job_counts("no such company zzz") == {"total": 0, "active": 0, "first_seen": None}
    assert store.get_open_jobs_by_company("no such company zzz") == []


def test_one_and_top_reposted(store):
    rows = store.get_company_stats(min_active=10, limit=1)["rows"]
    if not rows:
        pytest.skip("company_stats empty")
    top = rows[0]
    one = store.get_company_stats_one(top["company"])
    assert one is not None and one["company_key"] == top["company_key"]
    assert store.get_company_stats_one("no such company zzz") is None
    reposted = store.get_company_top_reposted(top["company"], limit=5)
    assert len(reposted) <= 5
    for r in reposted:
        assert r["repost_count"] >= 2
    assert [r["repost_count"] for r in reposted] == sorted((r["repost_count"] for r in reposted), reverse=True)


def test_agency_rule_spares_public_bodies(store):
    """Universities, research institutes and hospitals are never agencies, whatever their names."""
    for name in ("NUS", "NTU", "A*STAR"):
        row = store.get_company_stats_one(name)
        if row is not None:
            assert row["is_agency"] is False, name
    keys = store.get_agency_company_keys()
    assert "nus" not in keys and "a*star" not in keys


def test_client_and_pay_columns_are_consistent(store):
    """SGSAL-032: an agency is never also "hires for clients"; "direct" shows neither; typical pay
    counts standard ads only, so its sample and the other-pay count never exceed the open ads."""
    rows = store.get_company_stats(min_active=1, limit=200)["rows"]
    for r in rows:
        assert not (r["is_agency"] and r["hires_for_clients"])
        assert r["salary_sample"] + r["nonstandard_pay_count"] <= r["active_count"]
        assert r["client_ads"] <= r["described_ads"] <= r["active_count"]
    direct = store.get_company_stats(agency="direct", min_active=1, limit=200)["rows"]
    assert all(not r["is_agency"] and not r["hires_for_clients"] for r in direct)
    others = store.get_company_stats(agency="agency", min_active=1, limit=200)["rows"]
    assert all(r["is_agency"] or r["hires_for_clients"] for r in others)


def test_view_upgrade_is_a_no_op_once_current(store):
    store.upgrade_company_stats_view()
    assert store.upgrade_company_stats_view() is False
