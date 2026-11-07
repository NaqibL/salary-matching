"""Guard test (not a semantics test) for the assign_canonicals ranking term."""
from mcf.lib.storage import postgres_store as ps


def test_canon_rank_term_is_null_safe():
    # NULL pointer AND vector is NULL in SQL three-valued logic and would sort last.
    assert "IS TRUE" in ps._CANON_RANK_EXISTING
    assert "NULLS LAST" not in ps._CANON_RANK_EXISTING


def test_assign_canonicals_sql_uses_rank_term():
    assert ps._CANON_RANK_EXISTING in ps._ASSIGN_CANONICALS_SQL


def _backfill_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_posting_keys.py"
    spec = importlib.util.spec_from_file_location("backfill_posting_keys", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_expect_max_brake_aborts_with_exit_2():
    import pytest

    mod = _backfill_script()
    with pytest.raises(SystemExit) as exc:
        mod.check_expect_max(260_001, 260_000)
    assert exc.value.code == 2
    mod.check_expect_max(260_000, 260_000)  # at the limit: proceeds
    mod.check_expect_max(10**9, None)       # no brake set: proceeds


def test_active_vector_gate_keeps_index_friendly_or_form():
    gate = ps._ACTIVE_VECTOR_GATE.format(e="e")
    assert "a.canonical_job_uuid = e.job_uuid" in gate
    assert "a.canonical_job_uuid IS NULL AND a.job_uuid = e.job_uuid" in gate
    assert "COALESCE" not in gate  # COALESCE(...) = x would defeat idx_jobs_canonical / PK


def test_reposts_never_inherit_above_market_pct():
    # above_market_pct is derived from the row's own salary_min; hot_jobs_cluster
    # is safe to copy (identical vector).
    for sql in (ps._LINK_REPOSTS_SQL, ps._COPY_FIELDS_SQL):
        assert "above_market_pct" not in sql
        assert "hot_jobs_cluster" in sql
