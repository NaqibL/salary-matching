"""Guard test (not a semantics test) for the assign_canonicals ranking term."""
from mcf.lib.storage import postgres_store as ps


def test_canon_rank_term_is_null_safe():
    # NULL pointer AND vector is NULL in SQL three-valued logic and would sort last.
    assert "IS TRUE" in ps._CANON_RANK_EXISTING
    assert "NULLS LAST" not in ps._CANON_RANK_EXISTING


def test_assign_canonicals_sql_uses_rank_term():
    assert ps._CANON_RANK_EXISTING in ps._ASSIGN_CANONICALS_SQL
