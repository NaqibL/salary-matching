"""PostgreSQL-backed storage for incremental crawling and embeddings.

Uses psycopg2. All JSON fields are stored as TEXT for portability (matching
the DuckDB store), so no pgvector or JSONB extension is required.

The DATABASE_URL must be a libpq-style connection string, e.g.:
  postgresql://user:password@host:5432/dbname?sslmode=require
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Sequence

import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from psycopg2.extras import execute_values

from mcf.lib.storage.base import RunStats, Storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresStore(Storage):
    """PostgreSQL-backed persistence layer — mirrors DuckDBStore API exactly."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=8,
            dsn=database_url,
        )

    def close(self) -> None:
        self._pool.closeall()

    @contextmanager
    def _cur(self):
        conn = self._pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                yield cur
        finally:
            self._pool.putconn(conn)

    # === Crawl runs ===

    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats:
        started_at = _utcnow()
        run_id = started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO crawl_runs(run_id, started_at, finished_at, kind, categories_json,
                                      total_seen, added, maintained, removed)
                VALUES (%s, %s, NULL, %s, %s, 0, 0, 0, 0)
                """,
                [run_id, started_at, kind, json.dumps(list(categories) if categories else [])],
            )
        return RunStats(
            run_id=run_id,
            started_at=started_at,
            finished_at=None,
            total_seen=0,
            added=0,
            maintained=0,
            removed=0,
        )

    def finish_run(
        self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int
    ) -> None:
        with self._cur() as cur:
            cur.execute(
                """
                UPDATE crawl_runs
                   SET finished_at = %s,
                       total_seen = %s,
                       added = %s,
                       maintained = %s,
                       removed = %s
                 WHERE run_id = %s
                """,
                [_utcnow(), total_seen, added, maintained, removed, run_id],
            )

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT run_id, started_at, finished_at, total_seen, added, maintained, removed
                FROM crawl_runs
                WHERE finished_at IS NOT NULL
                ORDER BY finished_at DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        return [
            {
                "run_id": r[0],
                "started_at": r[1],
                "finished_at": r[2],
                "total_seen": r[3],
                "added": r[4],
                "maintained": r[5],
                "removed": r[6],
            }
            for r in rows
        ]

    # === Job lifecycle ===

    def existing_job_uuids(self) -> set[str]:
        with self._cur() as cur:
            cur.execute("SELECT job_uuid FROM jobs")
            return {r[0] for r in cur.fetchall()}

    def active_job_uuids(self) -> set[str]:
        with self._cur() as cur:
            cur.execute("SELECT job_uuid FROM jobs WHERE is_active = TRUE")
            return {r[0] for r in cur.fetchall()}

    def active_job_uuids_for_source(self, job_source: str) -> set[str]:
        with self._cur() as cur:
            cur.execute("SELECT job_uuid FROM jobs WHERE is_active = TRUE AND job_source = %s", [job_source])
            return {r[0] for r in cur.fetchall()}

    def active_job_uuids_for_source_and_categories(
        self, job_source: str, categories: list[str]
    ) -> set[str]:
        """Get active job UUIDs whose primary category is in `categories`."""
        import json as _json
        with self._cur() as cur:
            cur.execute("SELECT job_uuid, categories_json FROM jobs WHERE is_active = TRUE AND job_source = %s", [job_source])
            rows = cur.fetchall()
        cats_set = set(categories)
        result: set[str] = set()
        for uuid, cat_json in rows:
            if cat_json:
                job_cats = _json.loads(cat_json) if isinstance(cat_json, str) else cat_json
                if job_cats and job_cats[0] in cats_set:
                    result.add(uuid)
        return result

    def get_job_uuids_needing_description_backfill(self, limit: int | None = None) -> list[str]:
        """Return active job UUIDs where description is NULL."""
        with self._cur() as cur:
            sql = """
                SELECT job_uuid FROM jobs
                WHERE is_active = TRUE
                  AND description IS NULL
                ORDER BY job_uuid
            """
            if limit is not None:
                sql += " LIMIT %s"
                cur.execute(sql, [limit])
            else:
                cur.execute(sql)
            return [r[0] for r in cur.fetchall()]

    def update_job_description(self, job_uuid: str, description: str) -> None:
        with self._cur() as cur:
            cur.execute("UPDATE jobs SET description = %s WHERE job_uuid = %s", [description, job_uuid])

    def get_job_uuids_needing_rich_backfill(self, limit: int | None = None) -> list[str]:
        """Return job UUIDs where categories_json is NULL or empty."""
        with self._cur() as cur:
            sql = """
                SELECT job_uuid FROM jobs
                WHERE (categories_json IS NULL OR categories_json = '' OR categories_json = '[]')
                ORDER BY job_uuid
            """
            if limit is not None:
                sql += " LIMIT %s"
                cur.execute(sql, [limit])
            else:
                cur.execute(sql)
            return [r[0] for r in cur.fetchall()]

    def record_statuses(
        self,
        run_id: str,
        *,
        added: Iterable[str],
        maintained: Iterable[str],
        removed: Iterable[str],
    ) -> None:
        # Only store added/removed — maintained is ~70k rows/day and never queried.
        rows: list[tuple[str, str, str]] = []
        rows.extend((run_id, uuid, "added") for uuid in added)
        rows.extend((run_id, uuid, "removed") for uuid in removed)
        if not rows:
            return
        with self._cur() as cur:
            execute_values(
                cur,
                """
                INSERT INTO job_run_status(run_id, job_uuid, status) VALUES %s
                ON CONFLICT (run_id, job_uuid) DO UPDATE SET status = EXCLUDED.status
                """,
                rows,
            )

    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        with self._cur() as cur:
            cur.executemany(
                "UPDATE jobs SET last_seen_run_id = %s, last_seen_at = %s, is_active = TRUE WHERE job_uuid = %s",
                rows,
            )

    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        with self._cur() as cur:
            cur.executemany(
                "UPDATE jobs SET last_seen_run_id = %s, last_seen_at = %s, is_active = FALSE WHERE job_uuid = %s",
                rows,
            )

    def upsert_new_job_detail(
        self,
        *,
        run_id: str,
        job_uuid: str,
        title: str | None,
        company_name: str | None,
        location: str | None,
        job_url: str | None,
        skills: list[str] | None = None,
        raw_json: dict | None = None,
        categories: list[str] | None = None,
        employment_types: list[str] | None = None,
        position_levels: list[str] | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        posted_date: str | None = None,
        expiry_date: str | None = None,
        description: str | None = None,
    ) -> None:
        now = _utcnow()
        skills_json_str = json.dumps(skills) if skills else None
        categories_json_str = json.dumps(categories) if categories else None
        employment_types_json_str = json.dumps(employment_types) if employment_types else None
        position_levels_json_str = json.dumps(position_levels) if position_levels else None
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO jobs(job_uuid, first_seen_run_id, last_seen_run_id,
                                 is_active, first_seen_at, last_seen_at,
                                 title, company_name, location, job_url, skills_json,
                                 categories_json, employment_types_json, position_levels_json,
                                 salary_min, salary_max, posted_date, expiry_date,
                                 description)
                VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_uuid) DO UPDATE SET
                  last_seen_run_id      = EXCLUDED.last_seen_run_id,
                  is_active             = TRUE,
                  last_seen_at          = EXCLUDED.last_seen_at,
                  title                 = COALESCE(EXCLUDED.title, jobs.title),
                  company_name          = COALESCE(EXCLUDED.company_name, jobs.company_name),
                  location              = COALESCE(EXCLUDED.location, jobs.location),
                  job_url               = COALESCE(EXCLUDED.job_url, jobs.job_url),
                  skills_json           = COALESCE(EXCLUDED.skills_json, jobs.skills_json),
                  categories_json       = COALESCE(EXCLUDED.categories_json, jobs.categories_json),
                  employment_types_json = COALESCE(EXCLUDED.employment_types_json, jobs.employment_types_json),
                  position_levels_json  = COALESCE(EXCLUDED.position_levels_json, jobs.position_levels_json),
                  salary_min            = COALESCE(EXCLUDED.salary_min, jobs.salary_min),
                  salary_max            = COALESCE(EXCLUDED.salary_max, jobs.salary_max),
                  posted_date           = COALESCE(EXCLUDED.posted_date, jobs.posted_date),
                  expiry_date           = COALESCE(EXCLUDED.expiry_date, jobs.expiry_date),
                  description           = COALESCE(EXCLUDED.description, jobs.description)
                """,
                [
                    job_uuid, run_id, run_id,
                    now, now, title, company_name, location, job_url, skills_json_str,
                    categories_json_str, employment_types_json_str, position_levels_json_str,
                    salary_min, salary_max, posted_date, expiry_date,
                    description,
                ],
            )

    def get_job(self, job_uuid: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT job_uuid, title, company_name, location, job_url,
                       is_active, first_seen_at, last_seen_at, skills_json, description
                FROM jobs WHERE job_uuid = %s
                """,
                [job_uuid],
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "job_uuid": row[0], "title": row[1], "company_name": row[2],
            "location": row[3], "job_url": row[4], "is_active": row[5],
            "first_seen_at": row[6], "last_seen_at": row[7],
            "skills": json.loads(row[8]) if row[8] else [],
            "description": row[9],
        }

    def get_active_job_count(self) -> int:
        with self._cur() as cur:
            cur.execute("SELECT COUNT(*) FROM jobs WHERE is_active = TRUE")
            row = cur.fetchone()
        return row[0] if row else 0

    # === Embeddings cache (content_hash -> embedding) ===

    def get_embedding_by_content_hash(
        self, *, content_hash: str, model_name: str, embed_type: str
    ) -> list[float] | None:
        """Return cached embedding by content hash, or None."""
        try:
            with self._cur() as cur:
                cur.execute(
                    """
                    SELECT embedding_json FROM embeddings_cache
                    WHERE content_hash = %s AND model_name = %s AND embed_type = %s
                    """,
                    [content_hash, model_name, embed_type],
                )
                row = cur.fetchone()
        except psycopg2.ProgrammingError:
            return None  # table may not exist
        if not row:
            return None
        return json.loads(row[0])

    def upsert_embedding_cache(
        self, *, content_hash: str, model_name: str, embed_type: str, embedding: Sequence[float]
    ) -> None:
        """Store embedding in cache by content hash."""
        emb_list = [float(x) for x in embedding]
        emb_str = json.dumps(emb_list)
        try:
            with self._cur() as cur:
                cur.execute(
                    """
                    INSERT INTO embeddings_cache(content_hash, model_name, embed_type, embedding_json, dim, cached_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (content_hash, model_name, embed_type) DO UPDATE SET
                      embedding_json = EXCLUDED.embedding_json,
                      dim = EXCLUDED.dim,
                      cached_at = EXCLUDED.cached_at
                    """,
                    [content_hash, model_name, embed_type, emb_str, len(emb_list)],
                )
        except psycopg2.ProgrammingError:
            pass  # table may not exist

    # === Job classifications ===

    def batch_upsert_job_classifications(
        self, classifications: list[tuple[str, int, str]]
    ) -> None:
        if not classifications:
            return
        with self._cur() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE jobs
                SET role_cluster = %s, predicted_tier = %s
                WHERE job_uuid = %s
                """,
                [(rc, tier, uuid) for uuid, rc, tier in classifications],
                page_size=500,
            )

    # === Job embeddings ===

    def upsert_embedding(
        self, *, job_uuid: str, model_name: str, embedding: Sequence[float]
    ) -> None:
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        emb_str = json.dumps(emb_list)
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO job_embeddings(job_uuid, model_name, embedding, dim, embedded_at)
                VALUES (%s, %s, %s::vector, %s, %s)
                ON CONFLICT (job_uuid) DO UPDATE SET
                  model_name  = EXCLUDED.model_name,
                  embedding   = EXCLUDED.embedding,
                  dim         = EXCLUDED.dim,
                  embedded_at = EXCLUDED.embedded_at
                """,
                [job_uuid, model_name, emb_str, len(emb_list), now],
            )

    def get_active_job_embeddings(
        self,
        query_embedding: Sequence[float] | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, str, list[float], dict]]:
        if query_embedding is not None and limit is not None and limit > 0:
            emb_str = json.dumps([float(x) for x in query_embedding])
            with self._cur() as cur:
                cur.execute(
                    """
                    SELECT j.job_uuid, j.title, e.embedding::text,
                           j.company_name, j.location, j.job_url,
                           j.first_seen_at, j.last_seen_at, j.skills_json
                      FROM jobs j
                      JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                     WHERE j.is_active = TRUE
                       AND e.embedding IS NOT NULL
                     ORDER BY e.embedding <=> %s::vector ASC
                     LIMIT %s
                    """,
                    [emb_str, limit],
                )
                rows = cur.fetchall()
        else:
            with self._cur() as cur:
                cur.execute(
                    """
                    SELECT j.job_uuid, j.title, e.embedding::text,
                           j.company_name, j.location, j.job_url,
                           j.first_seen_at, j.last_seen_at, j.skills_json
                      FROM jobs j
                      JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                     WHERE j.is_active = TRUE
                       AND e.embedding IS NOT NULL
                    """
                )
                rows = cur.fetchall()
        out: list[tuple[str, str, list[float], dict]] = []
        for uuid, title, emb_json, company_name, location, job_url, first_seen_at, last_seen_at, skills_json in rows:
            job_details = {
                "company_name": company_name,
                "location": location,
                "job_url": job_url,
                "first_seen_at": first_seen_at,
                "last_seen_at": last_seen_at,
                "skills": json.loads(skills_json) if skills_json else [],
            }
            out.append((uuid, title or "", json.loads(emb_json), job_details))
        return out

    def get_active_jobs_pool(
        self,
    ) -> list[tuple[str, list[float], datetime | None]]:
        """Return (job_uuid, embedding, last_seen_at) for all active jobs with embeddings."""
        with self._cur() as cur:
            cur.execute(
                """
                SELECT j.job_uuid, e.embedding::text, j.last_seen_at
                  FROM jobs j
                  JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                 WHERE j.is_active = TRUE
                   AND e.embedding IS NOT NULL
                """,
            )
            rows = cur.fetchall()
        return [
            (r[0], json.loads(r[1]), r[2])
            for r in rows
            if r[1] is not None
        ]

    def get_active_job_ids_ranked(
        self,
        query_embedding: Sequence[float],
        limit: int = 5000,
    ) -> list[tuple[str, float, datetime | None]]:
        emb_str = json.dumps([float(x) for x in query_embedding])
        with self._cur() as cur:
            cur.execute(
                """
                SELECT j.job_uuid,
                       (e.embedding <=> %s::vector) AS distance,
                       j.last_seen_at
                  FROM jobs j
                  JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                 WHERE j.is_active = TRUE
                   AND e.embedding IS NOT NULL
                 ORDER BY distance ASC
                 LIMIT %s
                """,
                [emb_str, limit],
            )
            rows = cur.fetchall()
        return [(r[0], float(r[1]), r[2]) for r in rows]

    def get_all_embedded_job_ids_ranked(
        self,
        query_embedding: Sequence[float],
        limit: int = 5000,
    ) -> list[tuple[str, float, datetime | None]]:
        emb_str = json.dumps([float(x) for x in query_embedding])
        with self._cur() as cur:
            cur.execute(
                """
                SELECT j.job_uuid,
                       (e.embedding <=> %s::vector) AS distance,
                       j.last_seen_at
                  FROM jobs j
                  JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                 WHERE e.embedding IS NOT NULL
                 ORDER BY distance ASC
                 LIMIT %s
                """,
                [emb_str, limit],
            )
            rows = cur.fetchall()
        return [(r[0], float(r[1]), r[2]) for r in rows]

    def get_jobs_by_uuids(self, uuids: list[str]) -> list[dict]:
        if not uuids:
            return []
        with self._cur() as cur:
            cur.execute(
                """
                SELECT job_uuid, title, company_name, location, job_url, last_seen_at, skills_json,
                       role_cluster, predicted_tier, role_clusters_json, salary_min, salary_max, description
                  FROM jobs WHERE job_uuid = ANY(%s)
                """,
                [uuids],
            )
            rows = cur.fetchall()
        by_id = {
            r[0]: {
                "job_uuid": r[0],
                "title": r[1] or "",
                "company_name": r[2],
                "location": r[3],
                "job_url": r[4],
                "last_seen_at": r[5],
                "skills": json.loads(r[6]) if r[6] else [],
                "role_cluster": r[7],
                "predicted_tier": r[8],
                "role_clusters": list(r[9]) if r[9] else None,
                "salary_min": r[10],
                "salary_max": r[11],
                "description": r[12],
            }
            for r in rows
        }
        return [by_id[uid] for uid in uuids if uid in by_id]

    def get_job_uuids_for_filter(
        self,
        role_clusters: list[int] | None = None,
        predicted_tiers: list[str] | None = None,
    ) -> set[str] | None:
        if not role_clusters and not predicted_tiers:
            return None
        conditions = ["is_active = TRUE"]
        params: list = []
        if role_clusters:
            # Match primary cluster OR any multi-label cluster (array overlap &&)
            conditions.append("(role_cluster = ANY(%s) OR role_clusters_json && %s::integer[])")
            params.append(role_clusters)
            params.append(role_clusters)
        if predicted_tiers:
            conditions.append("predicted_tier = ANY(%s)")
            params.append(predicted_tiers)
        with self._cur() as cur:
            cur.execute(
                f"SELECT job_uuid FROM jobs WHERE {' AND '.join(conditions)}",
                params,
            )
            return {r[0] for r in cur.fetchall()}

    def get_job_uuids_with_salary_filter(
        self,
        salary_min: int | None = None,
        salary_max: int | None = None,
    ) -> set[str] | None:
        if salary_min is None and salary_max is None:
            return None
        conditions = ["is_active = TRUE", "salary_min IS NOT NULL"]
        params: list = []
        if salary_min is not None:
            conditions.append("salary_min >= %s")
            params.append(salary_min)
        if salary_max is not None:
            conditions.append("salary_min <= %s")
            params.append(salary_max)
        with self._cur() as cur:
            cur.execute(
                f"SELECT job_uuid FROM jobs WHERE {' AND '.join(conditions)}",
                params,
            )
            return {r[0] for r in cur.fetchall()}

    def batch_upsert_multi_label_clusters(
        self, data: list[tuple[str, list[int]]]
    ) -> None:
        if not data:
            return
        with self._cur() as cur:
            psycopg2.extras.execute_batch(
                cur,
                "UPDATE jobs SET role_clusters_json = %s WHERE job_uuid = %s",
                [(clusters, uuid) for uuid, clusters in data],
                page_size=500,
            )

    def create_match_session(
        self, *, user_id: str, mode: str, ranked_ids: list[str], ttl_seconds: int = 7200
    ) -> str:
        import secrets
        from datetime import timedelta

        session_id = secrets.token_urlsafe(16)
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._cur() as cur:
            cur.execute(
                "DELETE FROM match_sessions WHERE user_id = %s AND expires_at < %s",
                [user_id, now],
            )
            cur.execute(
                """
                INSERT INTO match_sessions(session_id, user_id, mode, ranked_ids, total, created_at, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [session_id, user_id, mode, json.dumps(ranked_ids), len(ranked_ids), now, expires_at],
            )
        return session_id

    def get_match_session(self, session_id: str, user_id: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT session_id, ranked_ids, total
                  FROM match_sessions
                 WHERE session_id = %s AND user_id = %s AND expires_at > %s
                """,
                [session_id, user_id, _utcnow()],
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "session_id": row[0],
            "ranked_ids": json.loads(row[1]),
            "total": row[2],
        }

    def get_all_active_jobs(self) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                "SELECT job_uuid, title, skills_json, position_levels_json, description"
                " FROM jobs WHERE is_active = TRUE"
            )
            rows = cur.fetchall()
        return [
            {
                "job_uuid": r[0],
                "title": r[1] or "",
                "skills": json.loads(r[2]) if r[2] else [],
                "position_levels": json.loads(r[3]) if r[3] else [],
                "description": r[4],
            }
            for r in rows
        ]

    def get_active_jobs_without_embeddings(self) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                "SELECT j.job_uuid, j.title, j.skills_json, j.position_levels_json, j.description"
                " FROM jobs j LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid"
                " WHERE j.is_active = TRUE AND e.job_uuid IS NULL"
            )
            rows = cur.fetchall()
        return [
            {
                "job_uuid": r[0],
                "title": r[1] or "",
                "skills": json.loads(r[2]) if r[2] else [],
                "position_levels": json.loads(r[3]) if r[3] else [],
                "description": r[4],
            }
            for r in rows
        ]

    def get_job_embeddings_for_uuids(
        self, uuids: list[str]
    ) -> list[tuple[str, list[float]]]:
        if not uuids:
            return []
        with self._cur() as cur:
            cur.execute(
                "SELECT job_uuid, embedding::text FROM job_embeddings WHERE job_uuid = ANY(%s) AND embedding IS NOT NULL",
                [uuids],
            )
            rows = cur.fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def get_embedding_model_name(self) -> str | None:
        with self._cur() as cur:
            cur.execute("SELECT model_name FROM job_embeddings LIMIT 1")
            row = cur.fetchone()
        return row[0] if row else None

    # === Users ===

    def get_user_by_id(self, user_id: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                "SELECT user_id, email, role, created_at, last_login FROM users WHERE user_id = %s",
                [user_id],
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"user_id": row[0], "email": row[1], "role": row[2], "created_at": row[3], "last_login": row[4]}

    def upsert_user(self, *, user_id: str, email: str, role: str = "candidate") -> None:
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO users(user_id, email, role, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  email = EXCLUDED.email,
                  role  = EXCLUDED.role
                """,
                [user_id, email, role, _utcnow()],
            )

    # === Profiles ===

    def create_profile(
        self,
        *,
        profile_id: str,
        user_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
    ) -> None:
        now = _utcnow()
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO candidate_profiles(profile_id, user_id, raw_resume_text,
                    expanded_profile_json, skills_json, experience_json, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    profile_id, user_id, raw_resume_text,
                    json.dumps(expanded_profile_json) if expanded_profile_json else None,
                    json.dumps(skills_json) if skills_json else None,
                    json.dumps(experience_json) if experience_json else None,
                    now, now,
                ],
            )

    def get_profile_by_user_id(self, user_id: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                       skills_json, experience_json, created_at, updated_at
                FROM candidate_profiles WHERE user_id = %s
                """,
                [user_id],
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0], "user_id": row[1], "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6], "updated_at": row[7],
        }

    def get_profile_by_profile_id(self, profile_id: str) -> dict | None:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                       skills_json, experience_json, created_at, updated_at
                FROM candidate_profiles WHERE profile_id = %s
                """,
                [profile_id],
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0], "user_id": row[1], "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6], "updated_at": row[7],
        }

    def update_profile(
        self,
        *,
        profile_id: str,
        raw_resume_text: str | None = None,
        expanded_profile_json: dict | None = None,
        skills_json: list[str] | None = None,
        experience_json: list[dict] | None = None,
        resume_storage_path: str | None = None,
    ) -> None:
        now = _utcnow()
        updates = []
        values: list = []
        if raw_resume_text is not None:
            updates.append("raw_resume_text = %s")
            values.append(raw_resume_text)
        if expanded_profile_json is not None:
            updates.append("expanded_profile_json = %s")
            values.append(json.dumps(expanded_profile_json))
        if skills_json is not None:
            updates.append("skills_json = %s")
            values.append(json.dumps(skills_json))
        if experience_json is not None:
            updates.append("experience_json = %s")
            values.append(json.dumps(experience_json))
        if resume_storage_path is not None:
            updates.append("resume_storage_path = %s")
            values.append(resume_storage_path)
        updates.append("updated_at = %s")
        values.append(now)
        values.append(profile_id)
        with self._cur() as cur:
            cur.execute(
                f"UPDATE candidate_profiles SET {', '.join(updates)} WHERE profile_id = %s",
                values,
            )

    # === Candidate embeddings ===

    def upsert_candidate_embedding(
        self, *, profile_id: str, model_name: str, embedding: Sequence[float]
    ) -> None:
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        emb_str = json.dumps(emb_list)
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO candidate_embeddings(profile_id, model_name, embedding, dim, embedded_at)
                VALUES (%s, %s, %s::vector, %s, %s)
                ON CONFLICT (profile_id) DO UPDATE SET
                  model_name  = EXCLUDED.model_name,
                  embedding   = EXCLUDED.embedding,
                  dim         = EXCLUDED.dim,
                  embedded_at = EXCLUDED.embedded_at
                """,
                [profile_id, model_name, emb_str, len(emb_list), now],
            )

    def get_candidate_embedding(self, profile_id: str) -> list[float] | None:
        with self._cur() as cur:
            cur.execute(
                "SELECT embedding::text FROM candidate_embeddings WHERE profile_id = %s",
                [profile_id],
            )
            row = cur.fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def upsert_taste_embedding(
        self, *, profile_id: str, model_name: str, embedding: Sequence[float]
    ) -> None:
        taste_key = f"{profile_id}:taste"
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        emb_str = json.dumps(emb_list)
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO candidate_embeddings(profile_id, model_name, embedding, dim, embedded_at)
                VALUES (%s, %s, %s::vector, %s, %s)
                ON CONFLICT (profile_id) DO UPDATE SET
                  model_name  = EXCLUDED.model_name,
                  embedding   = EXCLUDED.embedding,
                  dim         = EXCLUDED.dim,
                  embedded_at = EXCLUDED.embedded_at
                """,
                [taste_key, model_name, emb_str, len(emb_list), now],
            )

    def get_taste_embedding(self, profile_id: str) -> list[float] | None:
        taste_key = f"{profile_id}:taste"
        with self._cur() as cur:
            cur.execute(
                "SELECT embedding::text FROM candidate_embeddings WHERE profile_id = %s",
                [taste_key],
            )
            row = cur.fetchone()
        return json.loads(row[0]) if row and row[0] else None

    # === Interactions ===

    def record_interaction(
        self, *, user_id: str, job_uuid: str, interaction_type: str
    ) -> None:
        now = _utcnow()
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO job_interactions(user_id, job_uuid, interaction_type, interacted_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, job_uuid, interaction_type)
                DO UPDATE SET interacted_at = EXCLUDED.interacted_at
                """,
                [user_id, job_uuid, interaction_type, now],
            )

    def get_interacted_jobs(self, user_id: str) -> set[str]:
        with self._cur() as cur:
            cur.execute(
                "SELECT DISTINCT job_uuid FROM job_interactions WHERE user_id = %s",
                [user_id],
            )
            return {r[0] for r in cur.fetchall()}

    def get_interested_job_uuids(self, user_id: str) -> list[str]:
        with self._cur() as cur:
            cur.execute(
                "SELECT job_uuid FROM job_interactions WHERE user_id = %s AND interaction_type = 'interested'",
                [user_id],
            )
            return [r[0] for r in cur.fetchall()]

    def get_not_interested_job_uuids(self, user_id: str) -> list[str]:
        with self._cur() as cur:
            cur.execute(
                "SELECT job_uuid FROM job_interactions WHERE user_id = %s AND interaction_type = 'not_interested'",
                [user_id],
            )
            return [r[0] for r in cur.fetchall()]

    def get_interested_jobs(self, user_id: str) -> list[dict]:
        """Return interested jobs with job details, ordered by interacted_at desc."""
        with self._cur() as cur:
            cur.execute(
                """
                SELECT j.job_uuid, j.title, j.company_name, j.location, j.job_url, j.last_seen_at, j.skills_json
                  FROM jobs j
                  JOIN job_interactions i ON i.job_uuid = j.job_uuid
                 WHERE i.user_id = %s AND i.interaction_type = 'interested'
                 ORDER BY i.interacted_at DESC
                """,
                [user_id],
            )
            rows = cur.fetchall()
        return [
            {
                "job_uuid": r[0],
                "title": r[1] or "",
                "company_name": r[2],
                "location": r[3],
                "job_url": r[4],
                "last_seen_at": r[5],
                "similarity_score": 1.0,
                "job_skills": json.loads(r[6]) if r[6] else [],
            }
            for r in rows
        ]

    def reset_profile_ratings(self, user_id: str) -> dict:
        """Reset job interactions and taste profile for a user (for testing)."""
        profile = self.get_profile_by_user_id(user_id)
        profile_id = profile["profile_id"] if profile else None
        taste_key = f"{profile_id}:taste" if profile_id else None

        with self._cur() as cur:
            cur.execute("DELETE FROM job_interactions WHERE user_id = %s", [user_id])
            interactions_deleted = cur.rowcount

            if taste_key:
                cur.execute("DELETE FROM candidate_embeddings WHERE profile_id = %s", [taste_key])
                taste_deleted = cur.rowcount
            else:
                taste_deleted = 0

            if profile_id:
                cur.execute("DELETE FROM matches WHERE profile_id = %s", [profile_id])
                matches_deleted = cur.rowcount
            else:
                matches_deleted = 0

        return {
            "interactions_deleted": interactions_deleted,
            "taste_deleted": taste_deleted,
            "matches_deleted": matches_deleted,
        }

    # === Discover ===

    def get_discover_stats(self, user_id: str) -> dict:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE interaction_type = 'interested')     AS interested,
                  COUNT(*) FILTER (WHERE interaction_type = 'not_interested')  AS not_interested
                FROM job_interactions
                WHERE user_id = %s
                """,
                [user_id],
            )
            row = cur.fetchone()
        interested = row[0] if row else 0
        not_interested = row[1] if row else 0

        with self._cur() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                  FROM jobs j
                  JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                 WHERE j.is_active = TRUE
                   AND NOT EXISTS (
                         SELECT 1 FROM job_interactions i
                          WHERE i.user_id = %s
                            AND i.job_uuid = j.job_uuid
                            AND i.interaction_type IN ('interested', 'not_interested')
                       )
                """,
                [user_id],
            )
            unrated_row = cur.fetchone()
        unrated = unrated_row[0] if unrated_row else 0

        return {
            "interested": interested,
            "not_interested": not_interested,
            "unrated": unrated,
            "total_rated": interested + not_interested,
        }

    # === Dashboard ===

    def get_dashboard_summary(self) -> dict:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE j.is_active = TRUE) AS active,
                  COUNT(*) FILTER (WHERE j.is_active = FALSE) AS inactive,
                  COUNT(e.job_uuid) FILTER (WHERE j.is_active = TRUE) AS active_with_embeddings,
                  COUNT(e.job_uuid) FILTER (WHERE j.is_active = FALSE) AS inactive_with_embeddings
                FROM jobs j
                LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
                """
            )
            row = cur.fetchone()
        total = row[0] if row else 0
        active = row[1] if row else 0
        inactive = row[2] if row else 0
        jobs_with_embeddings = row[3] if row else 0
        inactive_jobs_with_embeddings = row[4] if row else 0

        with self._cur() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM jobs
                WHERE is_active = TRUE
                  AND (categories_json IS NULL OR categories_json = '' OR categories_json = '[]')
                """
            )
            row = cur.fetchone()
        jobs_needing_backfill = row[0] if row else 0

        return {
            "total_jobs": jobs_with_embeddings + inactive_jobs_with_embeddings,
            "active_jobs": active,
            "inactive_jobs": inactive,
            "by_source": {"mcf": active},
            "jobs_with_embeddings": jobs_with_embeddings,
            "inactive_jobs_with_embeddings": inactive_jobs_with_embeddings,
            "jobs_needing_backfill": jobs_needing_backfill,
        }

    def get_jobs_over_time_posted_and_removed(self, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)

        with self._cur() as cur:
            cur.execute(
                """
                SELECT stat_date::date AS day,
                       SUM(added_count)::int AS added_count,
                       SUM(removed_count)::int AS removed_count
                FROM job_daily_stats
                WHERE stat_date >= %s AND category != 'Unknown'
                GROUP BY stat_date
                ORDER BY stat_date ASC
                """,
                [cutoff],
            )
            rows = cur.fetchall()

        return [
            {"date": str(r[0]), "added_count": r[1], "removed_count": r[2]}
            for r in rows
        ]

    def get_active_jobs_over_time(self, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)

        with self._cur() as cur:
            cur.execute(
                """
                SELECT stat_date::date AS day, SUM(active_count)::int AS active_count
                FROM job_daily_stats
                WHERE stat_date >= %s AND category != 'Unknown'
                GROUP BY stat_date
                ORDER BY stat_date ASC
                """,
                [cutoff],
            )
            rows = cur.fetchall()

        return [{"date": str(r[0]), "active_count": r[1]} for r in rows]

    def backfill_job_daily_stats(self, limit_days: int = 365) -> dict:
        """One-time backfill of job_daily_stats from jobs table for historical dates."""
        from datetime import timedelta

        today = _utcnow().date()
        if limit_days <= 0:
            with self._cur() as cur:
                cur.execute(
                    """
                    SELECT MIN(LEAST(
                        COALESCE(posted_date::date, '9999-12-31'::date),
                        COALESCE(first_seen_at::date, '9999-12-31'::date),
                        COALESCE(last_seen_at::date, '9999-12-31'::date)
                    ))
                    FROM jobs
                    """
                )
                row = cur.fetchone()
            start_date = row[0] if row and row[0] and str(row[0]) != "9999-12-31" else today
        else:
            start_date = today - timedelta(days=limit_days)

        cat_ex = "COALESCE(NULLIF(TRIM(BOTH '\"' FROM (categories_json::jsonb->0)::text), ''), 'Unknown')"
        et_ex = "COALESCE(NULLIF(TRIM(BOTH '\"' FROM (employment_types_json::jsonb->0)::text), ''), 'Unknown')"
        pl_ex = "COALESCE(NULLIF(TRIM(BOTH '\"' FROM (position_levels_json::jsonb->0)::text), ''), 'Unknown')"

        total_rows = 0
        d = start_date
        while d <= today:
            with self._cur() as cur:
                cur.execute(
                    f"""
                    INSERT INTO job_daily_stats
                        (stat_date, category, employment_type, position_level, active_count, added_count, removed_count)
                    SELECT
                        %s AS stat_date,
                        {cat_ex} AS category,
                        {et_ex} AS employment_type,
                        {pl_ex} AS position_level,
                        COUNT(*) FILTER (
                            WHERE posted_date IS NOT NULL AND posted_date::date <= %s
                            AND (is_active = TRUE OR (last_seen_at IS NOT NULL AND last_seen_at::date > %s))
                        )::int AS active_count,
                        COUNT(*) FILTER (
                            WHERE (posted_date IS NOT NULL AND posted_date::date = %s)
                            OR (first_seen_at IS NOT NULL AND first_seen_at::date = %s)
                        )::int AS added_count,
                        COUNT(*) FILTER (
                            WHERE last_seen_at IS NOT NULL AND last_seen_at::date = %s AND is_active = FALSE
                        )::int AS removed_count
                    FROM jobs
                    GROUP BY 2, 3, 4
                    HAVING COUNT(*) FILTER (
                        WHERE posted_date IS NOT NULL AND posted_date::date <= %s
                        AND (is_active = TRUE OR (last_seen_at IS NOT NULL AND last_seen_at::date > %s))
                    ) > 0
                    OR COUNT(*) FILTER (
                        WHERE (posted_date IS NOT NULL AND posted_date::date = %s)
                        OR (first_seen_at IS NOT NULL AND first_seen_at::date = %s)
                    ) > 0
                    OR COUNT(*) FILTER (
                        WHERE last_seen_at IS NOT NULL AND last_seen_at::date = %s AND is_active = FALSE
                    ) > 0
                    ON CONFLICT (stat_date, category, employment_type, position_level)
                    DO UPDATE SET
                        active_count = EXCLUDED.active_count,
                        added_count = EXCLUDED.added_count,
                        removed_count = EXCLUDED.removed_count
                    """,
                    [d, d, d, d, d, d, d, d, d, d, d],
                )
                total_rows += cur.rowcount
            d += timedelta(days=1)

        return {"rows_upserted": total_rows, "date_start": str(start_date), "date_end": str(today)}

    def update_daily_stats(self, run_id: str) -> None:
        """Upsert today's aggregated stats by category x employment_type x position_level."""
        today = _utcnow().date()
        with self._cur() as cur:
                cur.execute(
                    """
                    INSERT INTO job_daily_stats
                        (stat_date, category, employment_type, position_level, active_count, added_count, removed_count)
                    SELECT
                        %s AS stat_date,
                        COALESCE(
                            NULLIF(TRIM(BOTH '"' FROM (j.categories_json::jsonb->0)::text), ''),
                            'Unknown'
                        ) AS category,
                        COALESCE(
                            NULLIF(TRIM(BOTH '"' FROM (j.employment_types_json::jsonb->0)::text), ''),
                            'Unknown'
                        ) AS employment_type,
                        COALESCE(
                            NULLIF(TRIM(BOTH '"' FROM (j.position_levels_json::jsonb->0)::text), ''),
                            'Unknown'
                        ) AS position_level,
                        COUNT(*) FILTER (WHERE j.is_active = TRUE) AS active_count,
                        COUNT(*) FILTER (WHERE jrs.status = 'added') AS added_count,
                        COUNT(*) FILTER (WHERE jrs.status = 'removed') AS removed_count
                    FROM jobs j
                    LEFT JOIN job_run_status jrs ON jrs.job_uuid = j.job_uuid AND jrs.run_id = %s
                    GROUP BY 2, 3, 4
                    ON CONFLICT (stat_date, category, employment_type, position_level)
                    DO UPDATE SET
                        active_count  = EXCLUDED.active_count,
                        added_count   = job_daily_stats.added_count + EXCLUDED.added_count,
                        removed_count = job_daily_stats.removed_count + EXCLUDED.removed_count
                    """,
                    [today, run_id],
                )

    def refresh_dashboard_materialized_views(self) -> None:
        """Refresh mv_dashboard_daily_stats and mv_dashboard_category_trends.
        Call after crawl completion. Requires migration 005."""
        with self._cur() as cur:
            cur.execute("SELECT refresh_dashboard_materialized_views()")

    def get_cache_metadata(self, key: str) -> dict | None:
        """Return {key, value_json, updated_at} or None. Requires migration 007."""
        try:
            with self._cur() as cur:
                cur.execute(
                    "SELECT key, value_json, updated_at FROM cache_metadata WHERE key = %s",
                    [key],
                )
                row = cur.fetchone()
        except psycopg2.ProgrammingError:
            return None
        if not row:
            return None
        val = row[1]
        if isinstance(val, str):
            val = json.loads(val) if val else None
        return {
            "key": row[0],
            "value_json": val,
            "updated_at": row[2],
        }

    def set_cache_metadata(self, key: str, value_json: dict) -> None:
        """Upsert cache_metadata row. Requires migration 007."""
        try:
            with self._cur() as cur:
                cur.execute(
                    """
                    INSERT INTO cache_metadata (key, value_json, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE SET value_json = EXCLUDED.value_json, updated_at = NOW()
                    """,
                    [key, json.dumps(value_json)],
                )
        except psycopg2.ProgrammingError:
            pass

    def delete_inactive_job_embeddings(self) -> int:
        """Delete embeddings for inactive jobs that no user has ever interacted with."""
        with self._cur() as cur:
            cur.execute(
                """
                DELETE FROM job_embeddings
                WHERE job_uuid IN (
                    SELECT e.job_uuid
                      FROM job_embeddings e
                      JOIN jobs j ON j.job_uuid = e.job_uuid
                     WHERE j.is_active = FALSE
                       AND j.last_seen_at < NOW() - INTERVAL '24 hours'
                       AND NOT EXISTS (
                             SELECT 1 FROM job_interactions i
                              WHERE i.job_uuid = e.job_uuid
                           )
                )
                """
            )
            return cur.rowcount

    def get_jobs_by_category(self, limit_days: int = 90, limit: int = 30) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT category, SUM(active_count)::int AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND category != 'Unknown'
                GROUP BY category
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        if rows:
            return [{"category": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(BOTH '"' FROM (categories_json::jsonb->0)::text), ''),
                        'Unknown'
                    ) AS category,
                    COUNT(*)::int AS count
                FROM jobs
                WHERE is_active = TRUE
                GROUP BY 1
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        return [{"category": r[0], "count": r[1]} for r in rows]

    def get_category_trends(self, category: str, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)
        today = _utcnow().date()

        with self._cur() as cur:
            try:
                cur.execute(
                    """
                    SELECT stat_date::date AS day,
                           active_count, added_count, removed_count
                    FROM mv_dashboard_category_trends
                    WHERE category = %s AND stat_date >= %s
                    ORDER BY stat_date ASC
                    """,
                    [category, cutoff],
                )
                rows = cur.fetchall()
            except psycopg2.ProgrammingError:
                try:
                    cur.execute(
                        """
                        SELECT stat_date::date AS day,
                               SUM(active_count)::int AS active_count,
                               SUM(added_count)::int AS added_count,
                               SUM(removed_count)::int AS removed_count
                        FROM job_daily_stats
                        WHERE category = %s AND stat_date >= %s
                        GROUP BY stat_date
                        ORDER BY stat_date ASC
                        """,
                        [category, cutoff],
                    )
                    rows = cur.fetchall()
                except Exception:
                    rows = []
            except Exception:
                rows = []

        if rows:
            return [
                {"date": str(r[0]), "active_count": r[1], "added_count": r[2], "removed_count": r[3]}
                for r in rows
            ]

        # Fallback: compute active count per day from jobs table for this category
        cat_extract = "COALESCE(NULLIF(TRIM(BOTH '\"' FROM (categories_json::jsonb->0)::text), ''), 'Unknown')"
        with self._cur() as cur:
            cur.execute(
                f"""
                WITH date_series AS (
                    SELECT generate_series(%s::date, %s::date, '1 day'::interval)::date AS d
                )
                SELECT ds.d::text AS date,
                    (SELECT COUNT(*)::int FROM jobs j
                     WHERE {cat_extract} = %s
                       AND j.posted_date IS NOT NULL
                       AND j.posted_date::date <= ds.d
                       AND (j.is_active = TRUE
                            OR (j.last_seen_at IS NOT NULL AND j.last_seen_at::date > ds.d))
                    ) AS active_count
                FROM date_series ds
                ORDER BY ds.d
                """,
                [cutoff, today, category],
            )
            rows = cur.fetchall()
        return [
            {"date": str(r[0]), "active_count": r[1], "added_count": 0, "removed_count": 0}
            for r in rows
        ]

    def get_category_stats(self, category: str) -> dict:
        bucket_order = [
            "$0-1k", "$1k-2k", "$2k-3k", "$3k-4k", "$4k-5k",
            "$5k-6k", "$6k-8k", "$8k-10k", "$10k+", "Not disclosed",
        ]

        # Single pass over filtered rows using a MATERIALIZED CTE
        with self._cur() as cur:
            cur.execute(
                """
                WITH filtered AS MATERIALIZED (
                    SELECT
                        COALESCE(NULLIF(TRIM(BOTH '"' FROM (employment_types_json::jsonb->0)::text), ''), 'Unknown') AS et,
                        COALESCE(NULLIF(TRIM(BOTH '"' FROM (position_levels_json::jsonb->0)::text), ''), 'Unknown') AS pl,
                        salary_min
                    FROM jobs
                    WHERE is_active = TRUE
                      AND COALESCE(NULLIF(TRIM(BOTH '"' FROM (categories_json::jsonb->0)::text), ''), 'Unknown') = %s
                )
                SELECT 'summary' AS kind, '' AS val,
                       COUNT(*)::text AS a,
                       COALESCE(ROUND(AVG(salary_min)::numeric, 0)::text, '') AS b
                FROM filtered
                UNION ALL
                SELECT 'et', et, cnt::text, ''
                FROM (
                    SELECT et, COUNT(*)::int AS cnt
                    FROM filtered WHERE et != 'Unknown'
                    GROUP BY et ORDER BY cnt DESC LIMIT 20
                ) t
                UNION ALL
                SELECT 'pl', pl, cnt::text, ''
                FROM (
                    SELECT pl, COUNT(*)::int AS cnt
                    FROM filtered WHERE pl != 'Unknown'
                    GROUP BY pl ORDER BY cnt DESC LIMIT 20
                ) t
                UNION ALL
                SELECT 'sal',
                       CASE
                           WHEN salary_min IS NULL THEN 'Not disclosed'
                           WHEN salary_min < 1000 THEN '$0-1k'
                           WHEN salary_min < 2000 THEN '$1k-2k'
                           WHEN salary_min < 3000 THEN '$2k-3k'
                           WHEN salary_min < 4000 THEN '$3k-4k'
                           WHEN salary_min < 5000 THEN '$4k-5k'
                           WHEN salary_min < 6000 THEN '$5k-6k'
                           WHEN salary_min < 8000 THEN '$6k-8k'
                           WHEN salary_min < 10000 THEN '$8k-10k'
                           ELSE '$10k+'
                       END,
                       COUNT(*)::text, ''
                FROM filtered GROUP BY 2
                """,
                [category],
            )
            rows = cur.fetchall()

        active_count = 0
        avg_salary = None
        employment_types: list[dict] = []
        position_levels: list[dict] = []
        by_bucket: dict[str, int] = {}

        for kind, val, a, b in rows:
            if kind == "summary":
                active_count = int(a) if a else 0
                avg_salary = int(float(b)) if b else None
            elif kind == "et":
                employment_types.append({"employment_type": val, "count": int(a)})
            elif kind == "pl":
                position_levels.append({"position_level": val, "count": int(a)})
            elif kind == "sal":
                by_bucket[val] = int(a)

        salary_buckets = [{"bucket": b, "count": by_bucket.get(b, 0)} for b in bucket_order]
        top_employment_type = employment_types[0]["employment_type"] if employment_types else None
        top_position_level = position_levels[0]["position_level"] if position_levels else None

        return {
            "active_count": active_count,
            "top_employment_type": top_employment_type,
            "top_position_level": top_position_level,
            "avg_salary": avg_salary,
            "employment_types": employment_types,
            "position_levels": position_levels,
            "salary_buckets": salary_buckets,
        }

    def get_jobs_by_employment_type(self, limit_days: int = 90, limit: int = 20) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT employment_type, SUM(active_count)::int AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND employment_type != 'Unknown'
                GROUP BY employment_type
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        if rows:
            return [{"employment_type": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(BOTH '"' FROM (employment_types_json::jsonb->0)::text), ''),
                        'Unknown'
                    ) AS employment_type,
                    COUNT(*)::int AS count
                FROM jobs
                WHERE is_active = TRUE
                GROUP BY 1
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        return [{"employment_type": r[0], "count": r[1]} for r in rows]

    def get_jobs_by_position_level(self, limit_days: int = 90, limit: int = 20) -> list[dict]:
        with self._cur() as cur:
            cur.execute(
                """
                SELECT position_level, SUM(active_count)::int AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND position_level != 'Unknown'
                GROUP BY position_level
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        if rows:
            return [{"position_level": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(BOTH '"' FROM (position_levels_json::jsonb->0)::text), ''),
                        'Unknown'
                    ) AS position_level,
                    COUNT(*)::int AS count
                FROM jobs
                WHERE is_active = TRUE
                GROUP BY 1
                ORDER BY count DESC
                LIMIT %s
                """,
                [limit],
            )
            rows = cur.fetchall()
        return [{"position_level": r[0], "count": r[1]} for r in rows]

    def get_salary_distribution(self) -> list[dict]:
        bucket_order = [
            "$0-1k", "$1k-2k", "$2k-3k", "$3k-4k", "$4k-5k",
            "$5k-6k", "$6k-8k", "$8k-10k", "$10k+", "Not disclosed",
        ]
        with self._cur() as cur:
            cur.execute(
                """
                SELECT
                    CASE
                        WHEN salary_min IS NULL THEN 'Not disclosed'
                        WHEN salary_min < 1000 THEN '$0-1k'
                        WHEN salary_min < 2000 THEN '$1k-2k'
                        WHEN salary_min < 3000 THEN '$2k-3k'
                        WHEN salary_min < 4000 THEN '$3k-4k'
                        WHEN salary_min < 5000 THEN '$4k-5k'
                        WHEN salary_min < 6000 THEN '$5k-6k'
                        WHEN salary_min < 8000 THEN '$6k-8k'
                        WHEN salary_min < 10000 THEN '$8k-10k'
                        ELSE '$10k+'
                    END AS bucket,
                    COUNT(*)::int AS count
                FROM jobs
                WHERE is_active = TRUE
                GROUP BY 1
                """
            )
            rows = cur.fetchall()
        by_bucket = {r[0]: r[1] for r in rows}
        return [{"bucket": b, "count": by_bucket.get(b, 0)} for b in bucket_order]

    def get_jobs_with_salary_by_uuids(self, job_uuids: list[str]) -> list[dict]:
        if not job_uuids:
            return []
        with self._cur() as cur:
            cur.execute(
                "SELECT job_uuid, title, company_name, location, job_url, salary_min, salary_max, last_seen_at, is_active "
                "FROM jobs WHERE job_uuid = ANY(%s)",
                (job_uuids,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # === Match recording ===

    def record_match(
        self,
        *,
        match_id: str,
        profile_id: str,
        job_uuid: str,
        similarity_score: float,
        match_type: str,
    ) -> None:
        with self._cur() as cur:
            cur.execute(
                """
                INSERT INTO matches(match_id, profile_id, job_uuid, similarity_score, match_type, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [match_id, profile_id, job_uuid, similarity_score, match_type, _utcnow()],
            )
