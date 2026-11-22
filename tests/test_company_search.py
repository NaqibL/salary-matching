"""Company name search helpers (pure functions, no database)."""

from mcf.api.routes.companies import _percentiles, short_name_expansions
from mcf.lib.storage.postgres_store import _like_escape


def test_short_names_expand_case_insensitively():
    assert short_name_expansions("NUH") == ("national university hospital",)
    assert short_name_expansions("  govtech ") == ("government technology agency",)
    assert short_name_expansions("dbs bank") == ()
    assert short_name_expansions(None) == ()
    assert short_name_expansions("") == ()


def test_like_escape_makes_wildcards_literal():
    assert _like_escape("100%_x") == "100\\%\\_x"
    assert _like_escape("a\\b") == "a\\\\b"
    assert _like_escape(None) == ""


def test_percentiles_small_samples_collapse_to_the_median():
    assert _percentiles([]) == (None, None, None)
    assert _percentiles([3000, 5000]) == (4000, 4000, 4000)
    p25, p50, p75 = _percentiles([1000, 2000, 3000, 4000, 5000])
    assert (p25, p50, p75) == (2000, 3000, 4000)
