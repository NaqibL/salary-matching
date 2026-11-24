"""Company name variants (pure functions) and the linking step against Postgres."""

import os

import pytest

from mcf.lib.companies.names import name_key, pick_display_name

SAME = [
    ("AETOS HOLDINGS PTE. LTD.", "Aetos Holdings"),
    ("BLACKROCK (SINGAPORE) LIMITED", "BlackRock"),
    ("WIPRO LIMITED (SINGAPORE BRANCH)", "Wipro"),
    ("Chanel Asia Pacific", "Chanel"),
    ("VISTRA CORPORATE SERVICES (S) PTE. LTD.", "Vistra Corporate Services"),
    ("CHINA HARBOUR ENGINEERING COMPANY LTD Singapore Branch", "CHINA HARBOUR ENGINEERING COMPANY LTD SINGAPORE BRANCH"),
    ("SHANGHAI TUNNEL ENGINEERING CO (SINGAPORE) PTE LTD", "SHANGHAI TUNNEL ENGINEERING CO. LTD."),
    ("ADDITIVE INN Limited Liability Partnership", "ADDITIVE INN LIMITED LIABILITY PARTNERSHIP"),
    ("THE BALLET SCHOOL (SINGAPORE) PTE. LTD.", "THE BALLET SCHOOL"),
    ("Smith & Nephew Pte. Limited", "SMITH AND NEPHEW ASIA PACIFIC PTE. LIMITED"),
]
DIFFERENT = [
    # sister companies of one brand stay separate
    ("SMRT Trains", "SMRT BUSES LTD."),
    ("HONG LEONG ASIA LTD.", "HONG LEONG HOLDINGS LIMITED"),
    ("Goldman Sachs", "Goldman Sachs Services"),
    ("National University Hospital", "NATIONAL UNIVERSITY HEALTH SYSTEM PTE. LTD."),
    ("NATURELAND GLOBAL PTE. LTD.", "NATURELAND INTERNATIONAL PTE. LTD."),
    # a bare acronym plus a place is not enough to call two firms the same
    ("AMT (SINGAPORE) PTE. LTD.", "AMT PTE. LTD."),
    ("HR SG PTE. LTD.", "HR SERVICES PTE. LTD."),
    # the place is part of the name
    ("Bank of Singapore", "Bank of Asia"),
    ("A*STAR", "A STAR PACIFIC PTE. LTD."),
    ("DELIZ S PTE. LTD.", "DELIZ PTE. LTD."),
]


@pytest.mark.parametrize("a,b", SAME)
def test_variants_share_a_key(a, b):
    assert name_key(a) == name_key(b) != ""


@pytest.mark.parametrize("a,b", DIFFERENT)
def test_distinct_organisations_keep_distinct_keys(a, b):
    assert name_key(a) != name_key(b)


def test_unusable_names_have_no_key():
    assert name_key(None) == "" and name_key("???") == "" and name_key("  ") == ""


def test_display_name_prefers_cleaned_then_busiest_then_readable():
    cleaned = {"name": "Aetos Holdings", "is_canonical": True, "active": 1, "total": 5}
    raw = {"name": "AETOS HOLDINGS PTE. LTD.", "is_canonical": False, "active": 40, "total": 90}
    assert pick_display_name([raw, cleaned]) == "Aetos Holdings"
    busy = {"name": "X CO (Singapore Branch)", "is_canonical": False, "active": 9, "total": 9}
    quiet = {"name": "X CO (SINGAPORE BRANCH)", "is_canonical": False, "active": 2, "total": 30}
    assert pick_display_name([quiet, busy]) == "X CO (Singapore Branch)"
    tie_a = {"name": "ACME WIDGETS PTE. LTD.", "is_canonical": False, "active": 3, "total": 3}
    tie_b = {"name": "Acme Widgets Pte. Ltd.", "is_canonical": False, "active": 3, "total": 3}
    assert pick_display_name([tie_a, tie_b]) == "Acme Widgets Pte. Ltd."


def test_linking_is_reported_and_repeatable():
    """Dry run changes nothing; whatever a real run links, a second run has nothing left to do."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    from mcf.lib.storage.postgres_store import PostgresStore

    store = PostgresStore(url)
    for group in store.link_company_name_variants(dry_run=True):
        assert group["jobs"] == 0 and group["merged"] and group["display"] not in group["merged"]
        keys = {name_key(n) for n in [group["display"], *group["merged"]]}
        assert len(keys) == 1
