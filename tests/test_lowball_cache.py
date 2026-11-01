"""Unit tests for the salary checker / salary search response-cache key.

No network, no DB. Only exercises key construction and the in-memory cache helpers.
"""

from __future__ import annotations

from mcf.api.cache.response import (
    TTL_LOWBALL,
    cache_get,
    cache_set,
    invalidate_lowball,
    make_body_cache_key,
    normalize_text,
)
from mcf.api.routes.lowball import (
    LowballCheckRequest,
    SalarySearchRequest,
    lowball_cache_key,
    salary_search_cache_key,
)

_DESC = (
    "We are looking for a Data Engineer to build and maintain ETL pipelines on "
    "Airflow and Spark. 3+ years experience. Python, SQL, GCP."
)


def _req(**overrides) -> LowballCheckRequest:
    base = dict(title="Data Engineer", description=_DESC, salary=6000, company_name="Shopee")
    base.update(overrides)
    return LowballCheckRequest(**base)


def test_same_inputs_same_key():
    assert lowball_cache_key(_req()) == lowball_cache_key(_req())


def test_each_result_affecting_field_changes_key():
    base = lowball_cache_key(_req())
    assert lowball_cache_key(_req(salary=7000)) != base
    assert lowball_cache_key(_req(salary=None)) != base
    assert lowball_cache_key(_req(title="Data Scientist")) != base
    assert lowball_cache_key(_req(company_name="Grab")) != base
    assert lowball_cache_key(_req(company_name=None)) != base
    assert lowball_cache_key(_req(description=_DESC + " Kubernetes.")) != base
    assert lowball_cache_key(_req(top_k=10)) != base
    assert lowball_cache_key(_req(seniority="Intern")) != base


def test_title_and_description_normalized_whitespace_and_case():
    base = lowball_cache_key(_req())
    assert lowball_cache_key(_req(title="  data   ENGINEER ")) == base
    assert lowball_cache_key(_req(description="  " + _DESC.upper().replace(". ", ".\n\n  "))) == base


def test_exact_fields_are_not_normalized():
    # company_name is an exact DB match and seniority is compared literally,
    # so a case change must produce a different key.
    base = lowball_cache_key(_req())
    assert lowball_cache_key(_req(company_name="shopee")) != base
    assert lowball_cache_key(_req(seniority="Intern")) != lowball_cache_key(_req(seniority="intern"))


def test_description_is_hashed_not_stored_raw():
    key = lowball_cache_key(_req())
    assert key.startswith("lowball:")
    assert "data engineer" not in key.lower()
    assert "airflow" not in key.lower()
    assert "shopee" not in key.lower()
    # prefix + short digest only
    assert len(key) < 64


def test_salary_search_key_fields():
    body = SalarySearchRequest(title="Data Engineer", description=_DESC, salary_min=5000, salary_max=8000)
    base = salary_search_cache_key(body)
    assert base.startswith("salary_search:")
    assert base == salary_search_cache_key(body.model_copy())
    assert salary_search_cache_key(body.model_copy(update={"salary_min": 4000})) != base
    assert salary_search_cache_key(body.model_copy(update={"salary_max": None})) != base
    assert salary_search_cache_key(body.model_copy(update={"offset": 25})) != base
    assert salary_search_cache_key(body.model_copy(update={"top_k": 10})) != base
    # lowball and salary_search never collide even with the same text
    assert base != lowball_cache_key(_req(salary=None, company_name=None, top_k=25))


def test_normalize_text():
    assert normalize_text(None) == ""
    assert normalize_text("") == ""
    assert normalize_text("  Data \n\t Engineer  ") == "data engineer"


def test_make_body_cache_key_none_params_are_ignored_consistently():
    a = make_body_cache_key("p", title="t", description="d", salary=None)
    b = make_body_cache_key("p", title="t", description="d")
    assert a == b


def test_invalidate_lowball_clears_both_prefixes_only():
    k_low = lowball_cache_key(_req())
    k_search = salary_search_cache_key(SalarySearchRequest(title="x", description="y"))
    other = "dashboard:test-key-unrelated"
    cache_set(k_low, TTL_LOWBALL, {"v": 1})
    cache_set(k_search, TTL_LOWBALL, {"v": 2})
    cache_set(other, TTL_LOWBALL, {"v": 3})
    try:
        assert invalidate_lowball() == 2
        assert cache_get(k_low) is None
        assert cache_get(k_search) is None
        assert cache_get(other) == {"v": 3}
    finally:
        from mcf.api.cache.response import cache_invalidate

        cache_invalidate(key=other)
