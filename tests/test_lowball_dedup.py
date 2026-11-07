"""Benchmark-pool dedup and zero-safe repost facts (SGSAL-024 I3/M3). Pure logic — no DB."""

from mcf.api.routes.lowball import _build_similar_jobs, _by_score, _dedup_by_job_uuid


def _row(job_uuid: str, canonical: str, **kw) -> dict:
    return {"job_uuid": job_uuid, "canonical_job_uuid": canonical, "title": "T",
            "salary_min": 5000, "salary_max": 6000, "is_active": True, **kw}


def test_dedup_keeps_first_occurrence_per_job_uuid():
    rows = [_row("rep", "c1", salary_min=1), _row("other", "c2"), _row("rep", "c3", salary_min=2)]
    out = _dedup_by_job_uuid(rows)
    assert [r["job_uuid"] for r in out] == ["rep", "other"]
    assert out[0]["salary_min"] == 1


def test_by_score_then_dedup_keeps_best_scoring_hit():
    rows = [_row("rep", "c1"), _row("rep", "c2")]
    out = _dedup_by_job_uuid(_by_score(rows, {"c1": 0.5, "c2": 0.9}))
    assert len(out) == 1 and out[0]["canonical_job_uuid"] == "c2"


def test_one_salary_per_posting_in_benchmark_pool():
    # three vector hits from one posting group resolve to one representative row
    rows = [_row("rep", f"c{i}") for i in range(3)] + [_row("x", "cx", salary_min=9000)]
    assert [r["salary_min"] for r in _dedup_by_job_uuid(rows)] == [5000, 9000]


def test_zero_repost_facts_are_not_masked():
    j = _row("a", "a", repost_count=4, active_count=0, reposts_365d=0, distinct_companies=2, is_active=False)
    card = _build_similar_jobs([j], {"a": 0.8}, 5)[0]
    assert card["reposts_365d"] == 0
    assert card["active_count"] == 0
    assert card["repost_count"] == 4


def test_missing_repost_facts_fall_back_to_single_occurrence():
    card = _build_similar_jobs([_row("a", "a")], {"a": 0.8}, 5)[0]
    assert card["repost_count"] == 1 and card["reposts_365d"] == 1
    assert card["active_count"] == 1 and card["distinct_companies"] == 1
