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
