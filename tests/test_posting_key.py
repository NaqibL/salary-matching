"""Posting key (content hash) and repost link planning (SGSAL-024). No network/DB."""

from mcf.lib.pipeline.posting_key import plan_repost_links, posting_key


def test_identical_inputs_give_identical_keys():
    assert posting_key("Data Analyst", "Build dashboards.") == posting_key("Data Analyst", "Build dashboards.")


def test_key_is_32_hex_chars():
    k = posting_key("Data Analyst", "Build dashboards.")
    assert k is not None and len(k) == 32 and int(k, 16) >= 0


def test_whitespace_and_case_in_title_do_not_matter():
    a = posting_key("  Data   Analyst ", "Build dashboards.")
    b = posting_key("data analyst", "Build dashboards.")
    assert a == b


def test_whitespace_runs_in_description_do_not_matter():
    a = posting_key("Data Analyst", "Build\n\n  dashboards.\r\n")
    b = posting_key("Data Analyst", "Build dashboards.")
    assert a == b


def test_description_case_matters():
    assert posting_key("x", "Build dashboards.") != posting_key("x", "build dashboards.")


def test_title_changes_key():
    assert posting_key("Data Analyst", "d") != posting_key("Senior Data Analyst", "d")


def test_company_is_not_part_of_key():
    # signature has no company parameter at all
    import inspect
    assert list(inspect.signature(posting_key).parameters) == ["title", "description"]


def test_blank_description_gives_none():
    assert posting_key("Data Analyst", None) is None
    assert posting_key("Data Analyst", "") is None
    assert posting_key("Data Analyst", "   \n ") is None


def test_emoji_title_is_stable():
    assert posting_key("🔥 Sales Crew", "d") == posting_key("🔥 sales crew", "d")


def test_plan_links_repost_to_existing_canonical():
    keys = {"new1": "h1"}
    canon = {"h1": "old1"}
    pairs, reposts = plan_repost_links(keys, canon)
    assert pairs == [("new1", "old1")]
    assert reposts == {"new1"}


def test_plan_first_of_a_new_key_becomes_canonical_for_the_rest_of_the_batch():
    keys = {"a": "h9", "b": "h9", "c": "h9"}
    pairs, reposts = plan_repost_links(keys, {})
    assert pairs == [("a", "a"), ("b", "a"), ("c", "a")]
    assert reposts == {"b", "c"}


def test_plan_none_key_is_self_canonical_and_never_a_repost():
    pairs, reposts = plan_repost_links({"a": None, "b": None}, {})
    assert pairs == [("a", "a"), ("b", "b")]
    assert reposts == set()


def test_plan_rerun_of_an_already_canonical_job_is_not_a_repost():
    pairs, reposts = plan_repost_links({"a": "h1"}, {"h1": "a"})
    assert pairs == [("a", "a")]
    assert reposts == set()
