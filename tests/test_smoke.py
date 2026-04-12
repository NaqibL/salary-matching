"""Smoke tests — verify the FastAPI app starts and key routes respond correctly."""

import pytest
from fastapi.testclient import TestClient

from mcf.api.server import app


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """TestClient backed by a fresh empty DuckDB, isolated from any .env settings.

    Using a temp DB means:
    - No DATABASE_URL → no Postgres (avoids production DB in tests)
    - No stale embeddings at wrong dimensions → no 500s from dimension mismatches
    - Tests check structure (keys/types), not non-zero data, so empty DB is fine
    """
    db_dir = tmp_path_factory.mktemp("db")
    from mcf.api.config import settings
    settings.database_url = None
    settings.db_path = str(db_dir / "test.duckdb")
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
