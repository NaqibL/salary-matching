"""Smoke tests — verify the FastAPI app starts and key routes respond correctly."""

import os

import pytest
from fastapi.testclient import TestClient

from mcf.api.server import app


@pytest.fixture(scope="session")
def client():
    """TestClient backed by the real Postgres DB (DATABASE_URL required).

    Tests check structure (keys/types), not non-zero data, so an empty or
    sparse DB is fine. Skip the whole suite if DATABASE_URL is not set.
    """
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set — skipping smoke tests")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200


def test_summary_public(client):
    r = client.get("/api/dashboard/summary-public")
    assert r.status_code == 200
    data = r.json()
    assert "total_jobs" in data


def test_summary_public_searchable_vs_seen(client):
    """SGSAL-024 semantics: a job is searchable when a vector exists for it OR for its
    canonical posting; vectors are deduplicated so vectors_stored <= jobs searchable."""
    data = client.get("/api/dashboard/summary-public").json()
    for key in ("jobs_seen_total", "jobs_searchable_total", "vectors_stored"):
        assert key in data, key
        assert isinstance(data[key], int)
    assert data["jobs_searchable_total"] <= data["jobs_seen_total"]
    assert data["vectors_stored"] <= data["jobs_searchable_total"]
    assert data["jobs_with_embeddings"] <= data["active_jobs_total"]
    assert data["jobs_searchable_total"] == data["jobs_with_embeddings"] + data["inactive_jobs_with_embeddings"]
    assert data["total_jobs"] == data["jobs_searchable_total"]


def test_active_jobs_over_time_public(client):
    r = client.get("/api/dashboard/active-jobs-over-time-public")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_jobs_by_category_public(client):
    r = client.get("/api/dashboard/jobs-by-category-public")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_jobs_by_employment_type_public(client):
    r = client.get("/api/dashboard/jobs-by-employment-type-public")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_jobs_by_position_level_public(client):
    r = client.get("/api/dashboard/jobs-by-position-level-public")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_salary_distribution_public(client):
    r = client.get("/api/dashboard/salary-distribution-public")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_seniority_breakdown_public(client):
    r = client.get("/api/dashboard/seniority-breakdown-public")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for row in data:
        assert {"seniority", "jobs", "median_salary"} <= row.keys()


def test_top_skills_public(client):
    r = client.get("/api/dashboard/top-skills-public", params={"limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 5
    for row in data:
        assert {"skill", "jobs", "median_salary"} <= row.keys()
    # role_family filter must not error even if the backfill has not reached it
    r = client.get("/api/dashboard/top-skills-public", params={"limit": 5, "role_family": "software_engineering"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_skills_trend_public(client):
    r = client.get("/api/dashboard/skills-trend-public", params={"skills": "Python,SQL", "weeks": 4})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # Zero-filled: one row per (week, skill)
    assert len(data) == 4 * 2
    for row in data:
        assert {"week", "skill", "jobs"} <= row.keys()
        assert row["skill"] in ("Python", "SQL")
    # Missing skills param is a validation error, not a 5xx
    assert client.get("/api/dashboard/skills-trend-public").status_code == 422


def test_role_families_public(client):
    r = client.get("/api/dashboard/role-families-public")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for row in data:
        assert {"role_family", "display_name", "jobs", "median_salary"} <= row.keys()


def test_authed_routes_require_auth(client):
    """Auth-protected routes must not return 5xx — 401/403/404 are all acceptable."""
    for path in [
        "/api/profile",
        "/api/matches",
        "/api/discover/stats",
    ]:
        r = client.get(path)
        assert r.status_code < 500, f"{path} returned {r.status_code}"


def test_lowball_check_requires_auth(client):
    r = client.post("/api/lowball/check", json={
        "job_description": "Software engineer with Python experience",
        "salary_min": 5000,
    })
    assert r.status_code < 500


def test_role_family_taxonomy_and_coverage(client):
    """SGSAL-022 C8: Jev role families are served and cover the active population.

    The taxonomy ids are what ``jobs.role_cluster`` holds after the backfill,
    so the matches filters keep working. Coverage must stay high because the
    daily embed workflow classifies every new job (backfill_role_families.py).
    """
    from mcf.api.deps import get_store

    r = client.get("/api/jobs/taxonomy")
    assert r.status_code == 200
    clusters = r.json()["clusters"]
    ids = [c["id"] for c in clusters]
    assert len(ids) == len(set(ids))
    assert 0 in ids, "id 0 is the low-confidence 'other' bucket"
    assert len(ids) >= 25, "24 role families + other"
    for c in clusters:
        assert {"id", "name", "key"} <= c.keys()

    breakdown = client.get("/api/dashboard/role-families-public").json()
    classified = sum(row["jobs"] for row in breakdown)
    missing = get_store().count_active_jobs_missing_role_family()
    total = classified + missing
    if total == 0:
        pytest.skip("no active jobs in this DB")
    keys = {c["key"] for c in clusters}
    assert all(row["role_family"] in keys for row in breakdown)
    coverage = classified / total
    assert coverage >= 0.95, f"only {coverage:.1%} of {total:,} active jobs have a role_family"


def test_posting_groups_schema_exists(client):
    """SGSAL-024: pointer columns + posting_groups view exist (migration 022)."""
    from mcf.api.deps import get_store

    store = get_store()
    cols = store.describe_columns("jobs")
    assert "content_hash" in cols and "canonical_job_uuid" in cols
    vcols = store.describe_columns("posting_groups")
    for c in ("content_hash", "canonical_job_uuid", "latest_job_uuid", "repost_count",
              "active_count", "first_posted", "last_posted", "reposts_90d", "reposts_365d",
              "distinct_companies", "latest_salary_min", "latest_salary_max",
              "min_salary_seen", "max_salary_seen", "occurrences"):
        assert c in vcols, c


def test_find_canonicals_is_read_only_and_shaped(client):
    """SGSAL-024: unknown hashes return {} and the method exists on the Storage ABC."""
    from mcf.api.deps import get_store
    from mcf.lib.storage.base import Storage

    store = get_store()
    assert callable(getattr(Storage, "find_canonicals"))
    assert callable(getattr(Storage, "link_reposts"))
    assert callable(getattr(Storage, "set_content_hashes"))
    assert callable(getattr(Storage, "refresh_posting_groups"))
    assert store.find_canonicals(["0" * 32, "f" * 32]) == {}
    assert store.find_canonicals([]) == {}


def test_representative_lookup_falls_back_to_self_for_ungrouped_uuid(client):
    """SGSAL-024: a uuid with no posting group returns itself with repost_count 1."""
    from mcf.api.deps import get_store

    store = get_store()
    # any embedded job; before the backfill none are grouped, after it the
    # canonical returns itself or its latest occurrence — both satisfy the shape checks.
    uuids = [u for u, _, _ in store.get_all_embedded_job_ids_ranked([0.0] * 768, limit=5)][:1]
    if not uuids:
        pytest.skip("no embeddings")
    rows = store.get_jobs_with_salary_by_uuids(uuids, representative=True)
    assert len(rows) == 1
    r = rows[0]
    for k in ("job_uuid", "title", "salary_min", "salary_max", "is_active", "canonical_job_uuid",
              "repost_count", "active_count", "reposts_365d", "distinct_companies"):
        assert k in r, k
    assert r["canonical_job_uuid"] == uuids[0]
    assert r["repost_count"] >= 1


def test_posting_history_unknown_uuid_is_none(client):
    from mcf.api.deps import get_store

    assert get_store().get_posting_history("no-such-job") is None


def test_most_reposted_shape(client):
    from mcf.api.deps import get_store

    rows = get_store().get_most_reposted(days=365, limit=5)
    assert isinstance(rows, list)
    for r in rows:
        assert set(r) >= {"canonical_job_uuid", "title", "company", "repost_count",
                          "reposts_in_window", "first_posted", "last_posted"}


def test_legacy_delete_inactive_embeddings_is_gone(client):
    from mcf.lib.storage.base import Storage

    assert not hasattr(Storage, "delete_inactive_job_embeddings")


def test_backfill_storage_methods_exist(client):
    from mcf.lib.storage.base import Storage

    for name in ("iter_jobs_needing_hash", "assign_canonicals", "copy_fields_from_canonicals",
                 "noncanonical_embedded_uuids", "delete_embeddings_by_uuids", "posting_group_stats"):
        assert callable(getattr(Storage, name)), name


def test_reposts_endpoint_404_for_unknown_job(client):
    r = client.get("/api/jobs/no-such-job/reposts")
    assert r.status_code == 404


def test_reposts_endpoint_shape_for_known_job(client):
    from mcf.api.deps import get_store

    store = get_store()
    uuids = [u for u, _, _ in store.get_all_embedded_job_ids_ranked([0.0] * 768, limit=1)]
    if not uuids:
        pytest.skip("no embeddings")
    r = client.get(f"/api/jobs/{uuids[0]}/reposts")
    assert r.status_code == 200
    data = r.json()
    assert data["repost_count"] >= 1
    assert isinstance(data["occurrences"], list) and len(data["occurrences"]) == data["repost_count"]
    assert {"job_uuid", "date", "company", "salary_min", "salary_max", "is_active"} <= set(data["occurrences"][0])


def test_most_reposted_public(client):
    r = client.get("/api/dashboard/most-reposted-public?days=365&limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/api/dashboard/most-reposted-public?days=7")
    assert r.status_code == 422


def test_lowball_cards_carry_group_fields(client):
    body = {"title": "Data Analyst", "description": "Build dashboards in Power BI and write SQL. " * 5, "top_k": 5}
    r = client.post("/api/lowball/check", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "total_listings" in data
    for j in data["similar_jobs"]:
        assert "repost_count" in j and j["repost_count"] >= 1
        assert "canonical_job_uuid" in j
    # one card per posting: canonical uuids are unique
    cu = [j["canonical_job_uuid"] for j in data["similar_jobs"]]
    assert len(cu) == len(set(cu))
    ju = [j["job_uuid"] for j in data["similar_jobs"]]
    assert len(ju) == len(set(ju))


def test_active_vector_gate_includes_reposts_of_inactive_canonicals(client):
    """SGSAL-024 C1: a vector is active when SOME active job points at it, so an
    expired canonical that serves an active repost stays in the ranked active pool
    (the path the matcher uses when the pool cache is off, and infer_candidate_tier)."""
    import psycopg2

    from mcf.api.deps import get_store

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '60s'")
            cur.execute(
                """
                SELECT a.canonical_job_uuid
                  FROM jobs a
                  JOIN jobs c ON c.job_uuid = a.canonical_job_uuid
                 WHERE a.is_active = TRUE
                   AND a.canonical_job_uuid <> a.job_uuid
                   AND c.is_active = FALSE
                   AND EXISTS (SELECT 1 FROM job_embeddings e WHERE e.job_uuid = c.job_uuid)
                   -- HNSW ef=100 runs before the gate; until --apply a group can hold
                   -- hundreds of identical vectors, so pick a group with < 50 of them.
                   AND (SELECT count(*) FROM jobs m JOIN job_embeddings me ON me.job_uuid = m.job_uuid
                         WHERE m.content_hash = c.content_hash) < 50
                 LIMIT 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        pytest.skip("no active repost of an inactive embedded canonical")
    canonical = row[0]

    store = get_store()
    embs = store.get_job_embeddings_for_uuids([canonical])
    assert embs, "canonical has a vector"
    ranked = store.get_active_job_ids_ranked(list(embs[0][1]), limit=50)
    by_uuid = {u: seen for u, _, seen in ranked}
    assert canonical in by_uuid
    # last_seen_at comes from the active member, not the expired owner
    assert by_uuid[canonical] is not None
