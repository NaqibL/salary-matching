"""SGSAL-028: companies registry round-trip against the live table (skipped without DATABASE_URL)."""

import os
import uuid

import pytest


@pytest.fixture(scope="module")
def store():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    from mcf.lib.storage.postgres_store import PostgresStore

    return PostgresStore(url)


def test_upsert_marks_ssic_78_as_agency_and_merges_nulls(store):
    name = f"test registry {uuid.uuid4().hex[:8]} pte ltd"
    key = name.lower()
    try:
        store.upsert_company(name=name, uen="T00TEST0A", source="mcf")
        assert key not in store.get_agency_company_keys()
        # second upsert adds the SSIC; the earlier UEN must survive (COALESCE merge)
        store.upsert_company(name=name.upper(), ssic_code_2020="78104", ssic_description="EMPLOYMENT AGENCIES")
        assert key in store.get_agency_company_keys()
        with store._cur() as cur:
            cur.execute("select name, uen, ssic_code_2020 from companies where company_key = %s", (key,))
            row = cur.fetchone()
        assert row == (name.upper(), "T00TEST0A", "78104")
    finally:
        with store._transaction_cur() as cur:
            cur.execute("delete from companies where company_key = %s", (key,))


def test_batch_upsert_keeps_source_sticky_and_merges(store):
    name = f"test batch {uuid.uuid4().hex[:8]} pte ltd"
    key = name.lower()
    try:
        n = store.upsert_companies([
            {"name": name, "source": "mcf"},
            {"name": name.upper(), "uen": "T00BATCH0A", "ssic_code_2020": "62011", "source": "mcf"},
        ])
        assert n == 1
        store.upsert_company(name=name, source="cag")  # must not flip an MCF row to cag
        with store._cur() as cur:
            cur.execute("select uen, ssic_code_2020, source from companies where company_key = %s", (key,))
            assert cur.fetchone() == ("T00BATCH0A", "62011", "mcf")
    finally:
        with store._transaction_cur() as cur:
            cur.execute("delete from companies where company_key = %s", (key,))


def test_missing_registry_lists_only_mcf_companies(store):
    rows = store.get_companies_missing_registry(min_active=1, limit=5)
    assert len(rows) <= 5
    for name, sample in rows:
        assert name and sample
        assert not sample.startswith("cag:")
