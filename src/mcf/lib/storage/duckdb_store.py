"""DuckDB-backed storage for incremental crawling and embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import duckdb

from mcf.lib.storage.base import RunStats, Storage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DuckDBStore(Storage):
    """Persistence layer for incremental crawl state."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._con = duckdb.connect(self.db_path)
        self._con.execute("PRAGMA threads=4")
        self.ensure_schema()

    def close(self) -> None:
        self._con.close()

    def ensure_schema(self) -> None:
        # Note: keep schema simple and portable; store large/variable structures as JSON.
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_runs (
              run_id TEXT PRIMARY KEY,
              started_at TIMESTAMP,
              finished_at TIMESTAMP,
              kind TEXT,
              categories_json TEXT,
              total_seen INTEGER,
              added INTEGER,
              maintained INTEGER,
              removed INTEGER
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              job_uuid TEXT PRIMARY KEY,
              job_source TEXT DEFAULT 'mcf',
              first_seen_run_id TEXT,
              last_seen_run_id TEXT,
              is_active BOOLEAN,
              first_seen_at TIMESTAMP,
              last_seen_at TIMESTAMP,
              title TEXT,
              company_name TEXT,
              location TEXT,
              job_url TEXT,
              skills_json TEXT
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_run_status (
              run_id TEXT,
              job_uuid TEXT,
              status TEXT,
              PRIMARY KEY (run_id, job_uuid)
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_embeddings (
              job_uuid TEXT PRIMARY KEY,
              model_name TEXT,
              embedding_json TEXT,
              dim INTEGER,
              embedded_at TIMESTAMP
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at DESC)")
        
        # Job interactions table for tracking user interactions
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_interactions (
              user_id TEXT,
              job_uuid TEXT,
              interaction_type TEXT,
              interacted_at TIMESTAMP,
              PRIMARY KEY (user_id, job_uuid, interaction_type)
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_job_interactions_user_job ON job_interactions(user_id, job_uuid)")
        
        # Migrations: add columns introduced after initial schema (safe to re-run)
        for _col_ddl in [
            "ALTER TABLE jobs ADD COLUMN job_url TEXT",
            "ALTER TABLE jobs ADD COLUMN skills_json TEXT",
            "ALTER TABLE jobs ADD COLUMN job_source TEXT DEFAULT 'mcf'",
            "ALTER TABLE jobs ADD COLUMN categories_json TEXT",
            "ALTER TABLE jobs ADD COLUMN employment_types_json TEXT",
            "ALTER TABLE jobs ADD COLUMN position_levels_json TEXT",
            "ALTER TABLE jobs ADD COLUMN salary_min INTEGER",
            "ALTER TABLE jobs ADD COLUMN salary_max INTEGER",
            "ALTER TABLE jobs ADD COLUMN posted_date DATE",
            "ALTER TABLE jobs ADD COLUMN expiry_date DATE",
            "ALTER TABLE jobs ADD COLUMN min_years_experience INTEGER",
            # candidate_embeddings: support multiple embedding types per profile
            # (taste embedding stored with profile_id suffix ':taste')
            "ALTER TABLE candidate_embeddings ADD COLUMN embedding_type TEXT DEFAULT 'resume'",
        ]:
            try:
                self._con.execute(_col_ddl)
            except duckdb.ProgrammingError:
                pass  # column already exists

        # Backfill job_url for MCF rows that have NULL (jobs crawled before URL extraction).
        # Only apply MCF URL pattern when job_source is NULL or 'mcf'.
        self._con.execute(
            """
            UPDATE jobs
               SET job_url = 'https://www.mycareersfuture.gov.sg/job/' || job_uuid
             WHERE job_url IS NULL
               AND (job_source IS NULL OR job_source = 'mcf')
            """
        )
        # Backfill job_source for existing rows
        self._con.execute(
            """
            UPDATE jobs SET job_source = 'mcf' WHERE job_source IS NULL
            """
        )

        # User and profile tables
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              user_id TEXT PRIMARY KEY,
              email TEXT UNIQUE,
              password_hash TEXT,
              created_at TIMESTAMP,
              last_login TIMESTAMP,
              role TEXT
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_profiles (
              profile_id TEXT PRIMARY KEY,
              user_id TEXT,
              raw_resume_text TEXT,
              expanded_profile_json TEXT,
              skills_json TEXT,
              experience_json TEXT,
              created_at TIMESTAMP,
              updated_at TIMESTAMP
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_embeddings (
              profile_id TEXT PRIMARY KEY,
              model_name TEXT,
              embedding_json TEXT,
              dim INTEGER,
              embedded_at TIMESTAMP
            )
            """
        )
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
              match_id TEXT PRIMARY KEY,
              profile_id TEXT,
              job_uuid TEXT,
              similarity_score FLOAT,
              match_type TEXT,
              created_at TIMESTAMP
            )
            """
        )
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_profiles_user ON candidate_profiles(user_id)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_matches_profile ON matches(profile_id)")
        self._con.execute("CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_uuid)")

        # Embeddings cache: content_hash -> embedding (avoids re-computing BGE)
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS embeddings_cache (
              content_hash TEXT,
              model_name TEXT,
              embed_type TEXT,
              embedding_json TEXT,
              dim INTEGER,
              cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (content_hash, model_name, embed_type)
            )
            """
        )

        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS job_daily_stats (
                stat_date       DATE NOT NULL,
                category        TEXT NOT NULL,
                employment_type TEXT NOT NULL DEFAULT 'Unknown',
                position_level  TEXT NOT NULL DEFAULT 'Unknown',
                active_count    INTEGER NOT NULL DEFAULT 0,
                added_count     INTEGER NOT NULL DEFAULT 0,
                removed_count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (stat_date, category, employment_type, position_level)
            )
            """
        )

        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS match_sessions (
                session_id  TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                mode        TEXT NOT NULL,
                ranked_ids  TEXT NOT NULL,
                total       INTEGER NOT NULL,
                created_at  TIMESTAMP,
                expires_at  TIMESTAMP
            )
            """
        )

        # Migration: add resume_storage_path column for Supabase Storage paths
        try:
            self._con.execute("ALTER TABLE candidate_profiles ADD COLUMN resume_storage_path TEXT")
        except duckdb.ProgrammingError:
            pass

    def begin_run(self, *, kind: str, categories: Sequence[str] | None) -> RunStats:
        started_at = _utcnow()
        run_id = started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        self._con.execute(
            """
            INSERT INTO crawl_runs(run_id, started_at, finished_at, kind, categories_json,
                                  total_seen, added, maintained, removed)
            VALUES (?, ?, NULL, ?, ?, 0, 0, 0, 0)
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

    def finish_run(self, run_id: str, *, total_seen: int, added: int, maintained: int, removed: int) -> None:
        self._con.execute(
            """
            UPDATE crawl_runs
               SET finished_at = ?,
                   total_seen = ?,
                   added = ?,
                   maintained = ?,
                   removed = ?
             WHERE run_id = ?
            """,
            [_utcnow(), total_seen, added, maintained, removed, run_id],
        )

    def existing_job_uuids(self) -> set[str]:
        rows = self._con.execute("SELECT job_uuid FROM jobs").fetchall()
        return {r[0] for r in rows}

    def active_job_uuids(self) -> set[str]:
        rows = self._con.execute("SELECT job_uuid FROM jobs WHERE is_active = TRUE").fetchall()
        return {r[0] for r in rows}

    def active_job_uuids_for_source(self, job_source: str) -> set[str]:
        """Get active job UUIDs for a specific source (for multi-source removal logic)."""
        if job_source == "mcf":
            rows = self._con.execute(
                "SELECT job_uuid FROM jobs WHERE is_active = TRUE AND (job_source = 'mcf' OR job_source IS NULL)"
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT job_uuid FROM jobs WHERE is_active = TRUE AND job_source = ?",
                [job_source],
            ).fetchall()
        return {r[0] for r in rows}

    def get_job_uuids_needing_rich_backfill(self, limit: int | None = None) -> list[str]:
        """Return MCF job UUIDs where categories_json is NULL or empty."""
        sql = """
            SELECT job_uuid FROM jobs
            WHERE (job_source = 'mcf' OR job_source IS NULL)
              AND (categories_json IS NULL OR categories_json = '' OR categories_json = '[]')
            ORDER BY job_uuid
        """
        if limit is not None:
            sql += " LIMIT ?"
            rows = self._con.execute(sql, [limit]).fetchall()
        else:
            rows = self._con.execute(sql).fetchall()
        return [r[0] for r in rows]

    def record_statuses(self, run_id: str, *, added: Iterable[str], maintained: Iterable[str], removed: Iterable[str]) -> None:
        # Batch insert for speed
        rows: list[tuple[str, str, str]] = []
        rows.extend((run_id, uuid, "added") for uuid in added)
        rows.extend((run_id, uuid, "maintained") for uuid in maintained)
        rows.extend((run_id, uuid, "removed") for uuid in removed)
        if not rows:
            return
        self._con.executemany(
            "INSERT OR REPLACE INTO job_run_status(run_id, job_uuid, status) VALUES (?, ?, ?)",
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
        job_source: str = "mcf",
        skills: list[str] | None = None,
        raw_json: dict | None = None,
        categories: list[str] | None = None,
        employment_types: list[str] | None = None,
        position_levels: list[str] | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        posted_date: str | None = None,
        expiry_date: str | None = None,
        min_years_experience: int | None = None,
    ) -> None:
        now = _utcnow()
        skills_json_str = json.dumps(skills) if skills else None
        categories_json_str = json.dumps(categories) if categories else None
        employment_types_json_str = json.dumps(employment_types) if employment_types else None
        position_levels_json_str = json.dumps(position_levels) if position_levels else None
        self._con.execute(
            """
            INSERT INTO jobs(job_uuid, job_source, first_seen_run_id, last_seen_run_id, is_active,
                             first_seen_at, last_seen_at,
                             title, company_name, location, job_url, skills_json,
                             categories_json, employment_types_json, position_levels_json,
                             salary_min, salary_max, posted_date, expiry_date, min_years_experience)
            VALUES (?, ?, ?, ?, TRUE, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (job_uuid) DO UPDATE SET
              job_source = COALESCE(excluded.job_source, jobs.job_source),
              last_seen_run_id = excluded.last_seen_run_id,
              is_active = TRUE,
              last_seen_at = excluded.last_seen_at,
              title = COALESCE(excluded.title, jobs.title),
              company_name = COALESCE(excluded.company_name, jobs.company_name),
              location = COALESCE(excluded.location, jobs.location),
              job_url = COALESCE(excluded.job_url, jobs.job_url),
              skills_json = COALESCE(excluded.skills_json, jobs.skills_json),
              categories_json = COALESCE(excluded.categories_json, jobs.categories_json),
              employment_types_json = COALESCE(excluded.employment_types_json, jobs.employment_types_json),
              position_levels_json = COALESCE(excluded.position_levels_json, jobs.position_levels_json),
              salary_min = COALESCE(excluded.salary_min, jobs.salary_min),
              salary_max = COALESCE(excluded.salary_max, jobs.salary_max),
              posted_date = COALESCE(excluded.posted_date, jobs.posted_date),
              expiry_date = COALESCE(excluded.expiry_date, jobs.expiry_date),
              min_years_experience = COALESCE(excluded.min_years_experience, jobs.min_years_experience)
            """,
            [
                job_uuid,
                job_source,
                run_id,
                run_id,
                now,
                now,
                title,
                company_name,
                location,
                job_url,
                skills_json_str,
                categories_json_str,
                employment_types_json_str,
                position_levels_json_str,
                salary_min,
                salary_max,
                posted_date,
                expiry_date,
                min_years_experience,
            ],
        )

    def touch_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        self._con.executemany(
            "UPDATE jobs SET last_seen_run_id = ?, last_seen_at = ?, is_active = TRUE WHERE job_uuid = ?",
            rows,
        )

    def deactivate_jobs(self, *, run_id: str, job_uuids: Iterable[str]) -> None:
        now = _utcnow()
        rows = [(run_id, now, uuid) for uuid in job_uuids]
        if not rows:
            return
        self._con.executemany(
            "UPDATE jobs SET last_seen_run_id = ?, last_seen_at = ?, is_active = FALSE WHERE job_uuid = ?",
            rows,
        )

    def jobs_missing_embeddings(self, *, limit: int | None = None) -> list[str]:
        """Get job UUIDs that are missing embeddings. Note: descriptions are not stored, so this is mainly for migration."""
        sql = """
          SELECT j.job_uuid
            FROM jobs j
       LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
           WHERE j.is_active = TRUE
             AND e.job_uuid IS NULL
        """
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        rows = self._con.execute(sql).fetchall()
        return [r[0] for r in rows]

    def get_embedding_by_content_hash(
        self, *, content_hash: str, model_name: str, embed_type: str
    ) -> list[float] | None:
        """Return cached embedding by content hash, or None."""
        try:
            row = self._con.execute(
                """
                SELECT embedding_json FROM embeddings_cache
                WHERE content_hash = ? AND model_name = ? AND embed_type = ?
                """,
                [content_hash, model_name, embed_type],
            ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        return json.loads(row[0])

    def batch_upsert_job_classifications(
        self, classifications: list[tuple[str, int, str]]
    ) -> None:
        if not classifications:
            return
        self._con.executemany(
            "UPDATE jobs SET role_cluster = ?, predicted_tier = ? WHERE job_uuid = ?",
            [(rc, tier, uuid) for uuid, rc, tier in classifications],
        )

    def upsert_embedding_cache(
        self, *, content_hash: str, model_name: str, embed_type: str, embedding: Sequence[float]
    ) -> None:
        """Store embedding in cache by content hash."""
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO embeddings_cache(content_hash, model_name, embed_type, embedding_json, dim, cached_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (content_hash, model_name, embed_type) DO UPDATE SET
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              cached_at = excluded.cached_at
            """,
            [content_hash, model_name, embed_type, json.dumps(emb_list), len(emb_list)],
        )

    def upsert_embedding(self, *, job_uuid: str, model_name: str, embedding: Sequence[float]) -> None:
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO job_embeddings(job_uuid, model_name, embedding_json, dim, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (job_uuid) DO UPDATE SET
              model_name = excluded.model_name,
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              embedded_at = excluded.embedded_at
            """,
            [job_uuid, model_name, json.dumps(emb_list), len(emb_list), now],
        )

    def get_active_job_embeddings(
        self,
        query_embedding: Sequence[float] | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, str, list[float], dict]]:
        """Get active job embeddings with all job details in a single query.

        query_embedding and limit are ignored (DuckDB has no vector search).
        Returns:
            List of tuples: (job_uuid, title, embedding, job_details_dict)
            where job_details_dict contains: company_name, location, job_url,
            first_seen_at, last_seen_at, skills (list[str])
        """
        rows = self._con.execute(
            """
            SELECT j.job_uuid, j.title, e.embedding_json,
                   j.company_name, j.location, j.job_url,
                   j.first_seen_at, j.last_seen_at, j.skills_json
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
            """
        ).fetchall()
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
        rows = self._con.execute(
            """
            SELECT j.job_uuid, e.embedding_json, j.last_seen_at
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
            """
        ).fetchall()
        return [
            (r[0], json.loads(r[1]), r[2])
            for r in rows
        ]

    def get_active_job_ids_ranked(
        self,
        query_embedding: Sequence[float],
        limit: int = 5000,
    ) -> list[tuple[str, float, datetime | None]]:
        import numpy as np

        rows = self._con.execute(
            """
            SELECT j.job_uuid, e.embedding_json, j.last_seen_at
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
            """
        ).fetchall()
        query_vec = np.array(query_embedding, dtype=np.float32)
        scored = []
        for uuid, emb_json, last_seen_at in rows:
            emb = np.array(json.loads(emb_json), dtype=np.float32)
            cosine_sim = float(np.dot(query_vec, emb))
            distance = 1.0 - cosine_sim
            scored.append((uuid, distance, last_seen_at))
        scored.sort(key=lambda x: x[1])
        return scored[:limit]

    def get_jobs_by_uuids(self, uuids: list[str]) -> list[dict]:
        if not uuids:
            return []
        placeholders = ", ".join("?" * len(uuids))
        rows = self._con.execute(
            f"SELECT job_uuid, title, company_name, location, job_url, last_seen_at, skills_json, "
            f"role_cluster, predicted_tier, role_clusters_json "
            f"FROM jobs WHERE job_uuid IN ({placeholders})",
            uuids,
        ).fetchall()
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
                "role_clusters": json.loads(r[9]) if r[9] else None,
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
            # DuckDB: check single-label only (role_clusters_json is TEXT/JSON, no native array ops)
            placeholders = ", ".join("?" * len(role_clusters))
            conditions.append(f"role_cluster IN ({placeholders})")
            params.extend(role_clusters)
        if predicted_tiers:
            placeholders = ", ".join("?" * len(predicted_tiers))
            conditions.append(f"predicted_tier IN ({placeholders})")
            params.extend(predicted_tiers)
        rows = self._con.execute(
            f"SELECT job_uuid FROM jobs WHERE {' AND '.join(conditions)}",
            params,
        ).fetchall()
        return {r[0] for r in rows}

    def batch_upsert_multi_label_clusters(
        self, data: list[tuple[str, list[int]]]
    ) -> None:
        if not data:
            return
        self._con.executemany(
            "UPDATE jobs SET role_clusters_json = ? WHERE job_uuid = ?",
            [(json.dumps(clusters), uuid) for uuid, clusters in data],
        )

    def create_match_session(
        self, *, user_id: str, mode: str, ranked_ids: list[str], ttl_seconds: int = 7200
    ) -> str:
        import secrets
        from datetime import timedelta

        session_id = secrets.token_urlsafe(16)
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        self._con.execute(
            "DELETE FROM match_sessions WHERE user_id = ? AND expires_at < ?",
            [user_id, now],
        )
        self._con.execute(
            """
            INSERT INTO match_sessions(session_id, user_id, mode, ranked_ids, total, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [session_id, user_id, mode, json.dumps(ranked_ids), len(ranked_ids), now, expires_at],
        )
        return session_id

    def get_match_session(self, session_id: str, user_id: str) -> dict | None:
        row = self._con.execute(
            """
            SELECT session_id, ranked_ids, total
              FROM match_sessions
             WHERE session_id = ? AND user_id = ? AND expires_at > ?
            """,
            [session_id, user_id, _utcnow()],
        ).fetchone()
        if not row:
            return None
        return {
            "session_id": row[0],
            "ranked_ids": json.loads(row[1]),
            "total": row[2],
        }

    def get_all_active_jobs(self) -> list[dict]:
        """Get all active jobs with stored metadata (for re-embedding).

        Returns a list of dicts with: job_uuid, title, skills (list[str]),
        position_levels (list[str]), min_years_experience (int | None).
        """
        rows = self._con.execute(
            "SELECT job_uuid, title, skills_json, position_levels_json, min_years_experience"
            " FROM jobs WHERE is_active = TRUE"
        ).fetchall()
        result = []
        for uuid, title, skills_json, position_levels_json, min_years_exp in rows:
            result.append({
                "job_uuid": uuid,
                "title": title or "",
                "skills": json.loads(skills_json) if skills_json else [],
                "position_levels": json.loads(position_levels_json) if position_levels_json else [],
                "min_years_experience": min_years_exp,
            })
        return result

    def get_embedding_model_name(self) -> str | None:
        """Return the model name used for the most recent job embedding, or None."""
        row = self._con.execute("SELECT model_name FROM job_embeddings LIMIT 1").fetchone()
        return row[0] if row else None

    def upsert_user(self, *, user_id: str, email: str, role: str = "candidate") -> None:
        """Create or update a user record (no password — auth handled by Supabase)."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO users(user_id, email, role, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (user_id) DO UPDATE SET
              email = EXCLUDED.email,
              role = EXCLUDED.role
            """,
            [user_id, email, role, now],
        )

    # User management
    def create_user(self, *, user_id: str, email: str, password_hash: str, role: str = "candidate") -> None:
        """Create a new user."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO users(user_id, email, password_hash, created_at, last_login, role)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            [user_id, email, password_hash, now, role],
        )

    def get_user_by_email(self, email: str) -> dict | None:
        """Get user by email."""
        row = self._con.execute(
            "SELECT user_id, email, password_hash, role, created_at, last_login FROM users WHERE email = ?",
            [email],
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "role": row[3],
            "created_at": row[4],
            "last_login": row[5],
        }

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Get user by ID."""
        row = self._con.execute(
            "SELECT user_id, email, password_hash, role, created_at, last_login FROM users WHERE user_id = ?",
            [user_id],
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "email": row[1],
            "password_hash": row[2],
            "role": row[3],
            "created_at": row[4],
            "last_login": row[5],
        }

    def update_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        self._con.execute("UPDATE users SET last_login = ? WHERE user_id = ?", [_utcnow(), user_id])

    # Profile management
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
        """Create a candidate profile."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO candidate_profiles(profile_id, user_id, raw_resume_text, expanded_profile_json,
                                          skills_json, experience_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                profile_id,
                user_id,
                raw_resume_text,
                json.dumps(expanded_profile_json) if expanded_profile_json else None,
                json.dumps(skills_json) if skills_json else None,
                json.dumps(experience_json) if experience_json else None,
                now,
                now,
            ],
        )

    def get_profile_by_user_id(self, user_id: str) -> dict | None:
        """Get profile by user ID."""
        row = self._con.execute(
            """
            SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                   skills_json, experience_json, created_at, updated_at
            FROM candidate_profiles WHERE user_id = ?
            """,
            [user_id],
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0],
            "user_id": row[1],
            "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
            "updated_at": row[7],
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
        """Update a candidate profile."""
        now = _utcnow()
        updates = []
        values = []
        if raw_resume_text is not None:
            updates.append("raw_resume_text = ?")
            values.append(raw_resume_text)
        if expanded_profile_json is not None:
            updates.append("expanded_profile_json = ?")
            values.append(json.dumps(expanded_profile_json))
        if skills_json is not None:
            updates.append("skills_json = ?")
            values.append(json.dumps(skills_json))
        if experience_json is not None:
            updates.append("experience_json = ?")
            values.append(json.dumps(experience_json))
        if resume_storage_path is not None:
            updates.append("resume_storage_path = ?")
            values.append(resume_storage_path)
        updates.append("updated_at = ?")
        values.append(now)
        values.append(profile_id)
        self._con.execute(
            f"UPDATE candidate_profiles SET {', '.join(updates)} WHERE profile_id = ?",
            values,
        )

    # Candidate embeddings
    def upsert_candidate_embedding(self, *, profile_id: str, model_name: str, embedding: Sequence[float]) -> None:
        """Store candidate embedding."""
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO candidate_embeddings(profile_id, model_name, embedding_json, dim, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (profile_id) DO UPDATE SET
              model_name = excluded.model_name,
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              embedded_at = excluded.embedded_at
            """,
            [profile_id, model_name, json.dumps(emb_list), len(emb_list), now],
        )

    def get_candidate_embeddings(self) -> list[tuple[str, list[float]]]:
        """Get all candidate embeddings."""
        rows = self._con.execute(
            "SELECT profile_id, embedding_json FROM candidate_embeddings"
        ).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def get_candidate_embedding(self, profile_id: str) -> list[float] | None:
        """Get candidate embedding by profile ID."""
        row = self._con.execute(
            "SELECT embedding_json FROM candidate_embeddings WHERE profile_id = ?",
            [profile_id],
        ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    # Matching
    def record_match(
        self, *, match_id: str, profile_id: str, job_uuid: str, similarity_score: float, match_type: str
    ) -> None:
        """Record a match."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT INTO matches(match_id, profile_id, job_uuid, similarity_score, match_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [match_id, profile_id, job_uuid, similarity_score, match_type, now],
        )

    def get_job(self, job_uuid: str) -> dict | None:
        """Get job by UUID."""
        row = self._con.execute(
            """
            SELECT job_uuid, title, company_name, location, job_url, is_active, first_seen_at, last_seen_at, skills_json
            FROM jobs WHERE job_uuid = ?
            """,
            [job_uuid],
        ).fetchone()
        if not row:
            return None
        return {
            "job_uuid": row[0],
            "title": row[1],
            "company_name": row[2],
            "location": row[3],
            "job_url": row[4],
            "is_active": row[5],
            "first_seen_at": row[6],
            "last_seen_at": row[7],
            "skills": json.loads(row[8]) if row[8] else [],
        }

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent crawl runs with statistics."""
        rows = self._con.execute(
            """
            SELECT run_id, started_at, finished_at, total_seen, added, maintained, removed
            FROM crawl_runs
            WHERE finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [
            {
                "run_id": row[0],
                "started_at": row[1],
                "finished_at": row[2],
                "total_seen": row[3],
                "added": row[4],
                "maintained": row[5],
                "removed": row[6],
            }
            for row in rows
        ]

    def get_active_job_count(self) -> int:
        """Get count of active jobs."""
        row = self._con.execute("SELECT COUNT(*) FROM jobs WHERE is_active = TRUE").fetchone()
        return row[0] if row else 0

    # Job interaction tracking
    def record_interaction(self, *, user_id: str, job_uuid: str, interaction_type: str) -> None:
        """Record a user interaction with a job."""
        now = _utcnow()
        self._con.execute(
            """
            INSERT OR REPLACE INTO job_interactions(user_id, job_uuid, interaction_type, interacted_at)
            VALUES (?, ?, ?, ?)
            """,
            [user_id, job_uuid, interaction_type, now],
        )

    def get_interacted_jobs(self, user_id: str) -> set[str]:
        """Get set of job UUIDs that the user has interacted with."""
        rows = self._con.execute(
            "SELECT DISTINCT job_uuid FROM job_interactions WHERE user_id = ?",
            [user_id],
        ).fetchall()
        return {row[0] for row in rows}

    def has_interacted(self, user_id: str, job_uuid: str) -> bool:
        """Check if user has interacted with a job."""
        row = self._con.execute(
            "SELECT 1 FROM job_interactions WHERE user_id = ? AND job_uuid = ? LIMIT 1",
            [user_id, job_uuid],
        ).fetchone()
        return row is not None

    # Discover / taste-profile helpers

    def get_interested_job_uuids(self, user_id: str) -> list[str]:
        """Return job UUIDs the user has marked as 'interested'."""
        rows = self._con.execute(
            "SELECT job_uuid FROM job_interactions WHERE user_id = ? AND interaction_type = 'interested'",
            [user_id],
        ).fetchall()
        return [r[0] for r in rows]

    def get_not_interested_job_uuids(self, user_id: str) -> list[str]:
        """Return job UUIDs the user has marked as 'not_interested'."""
        rows = self._con.execute(
            "SELECT job_uuid FROM job_interactions WHERE user_id = ? AND interaction_type = 'not_interested'",
            [user_id],
        ).fetchall()
        return [r[0] for r in rows]

    def get_interested_jobs(self, user_id: str) -> list[dict]:
        """Return interested jobs with job details, ordered by interacted_at desc."""
        rows = self._con.execute(
            """
            SELECT j.job_uuid, j.title, j.company_name, j.location, j.job_url, j.last_seen_at, j.skills_json
              FROM jobs j
              JOIN job_interactions i ON i.job_uuid = j.job_uuid
             WHERE i.user_id = ? AND i.interaction_type = 'interested'
             ORDER BY i.interacted_at DESC
            """,
            [user_id],
        ).fetchall()
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

        n = self._con.execute(
            "SELECT COUNT(*) FROM job_interactions WHERE user_id = ?", [user_id]
        ).fetchone()[0]
        self._con.execute("DELETE FROM job_interactions WHERE user_id = ?", [user_id])
        interactions_deleted = n

        taste_deleted = 0
        if taste_key:
            n = self._con.execute(
                "SELECT COUNT(*) FROM candidate_embeddings WHERE profile_id = ?", [taste_key]
            ).fetchone()[0]
            self._con.execute("DELETE FROM candidate_embeddings WHERE profile_id = ?", [taste_key])
            taste_deleted = n

        matches_deleted = 0
        if profile_id:
            n = self._con.execute(
                "SELECT COUNT(*) FROM matches WHERE profile_id = ?", [profile_id]
            ).fetchone()[0]
            self._con.execute("DELETE FROM matches WHERE profile_id = ?", [profile_id])
            matches_deleted = n

        return {
            "interactions_deleted": interactions_deleted,
            "taste_deleted": taste_deleted,
            "matches_deleted": matches_deleted,
        }

    def get_discover_stats(self, user_id: str) -> dict:
        """Return counts of interested, not_interested, and unrated jobs."""
        row = self._con.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE interaction_type = 'interested')       AS interested,
              COUNT(*) FILTER (WHERE interaction_type = 'not_interested')   AS not_interested
            FROM job_interactions
            WHERE user_id = ?
            """,
            [user_id],
        ).fetchone()
        interested = row[0] if row else 0
        not_interested = row[1] if row else 0

        unrated_row = self._con.execute(
            """
            SELECT COUNT(*)
              FROM jobs j
              JOIN job_embeddings e ON e.job_uuid = j.job_uuid
             WHERE j.is_active = TRUE
               AND NOT EXISTS (
                     SELECT 1 FROM job_interactions i
                      WHERE i.user_id = ?
                        AND i.job_uuid = j.job_uuid
                        AND i.interaction_type IN ('interested', 'not_interested')
                   )
            """,
            [user_id],
        ).fetchone()
        unrated = unrated_row[0] if unrated_row else 0

        return {
            "interested": interested,
            "not_interested": not_interested,
            "unrated": unrated,
            "total_rated": interested + not_interested,
        }

    # === Dashboard ===

    def get_dashboard_summary(self) -> dict:
        """Summary for MCF jobs only (excludes CAG)."""
        # Query 1: counts + embeddings in a single LEFT JOIN pass
        row = self._con.execute(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE j.is_active = TRUE) AS active,
              COUNT(*) FILTER (WHERE j.is_active = FALSE) AS inactive,
              COUNT(e.job_uuid) FILTER (WHERE j.is_active = TRUE) AS with_embeddings
            FROM jobs j
            LEFT JOIN job_embeddings e ON e.job_uuid = j.job_uuid
            WHERE (j.job_source = 'mcf' OR j.job_source IS NULL)
            """
        ).fetchone()
        total = row[0] if row else 0
        active = row[1] if row else 0
        inactive = row[2] if row else 0
        jobs_with_embeddings = row[3] if row else 0

        # Query 2: backfill count
        row = self._con.execute(
            """
            SELECT COUNT(*) FROM jobs
            WHERE is_active = TRUE
              AND (job_source = 'mcf' OR job_source IS NULL)
              AND (categories_json IS NULL OR categories_json = '' OR categories_json = '[]')
            """
        ).fetchone()
        jobs_needing_backfill = row[0] if row else 0

        return {
            "total_jobs": total,
            "active_jobs": active,
            "inactive_jobs": inactive,
            "by_source": {"mcf": total},
            "jobs_with_embeddings": jobs_with_embeddings,
            "jobs_needing_backfill": jobs_needing_backfill,
        }

    def get_jobs_over_time_posted_and_removed(self, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)

        rows = self._con.execute(
            """
            SELECT stat_date AS day,
                   SUM(added_count)::INTEGER AS added_count,
                   SUM(removed_count)::INTEGER AS removed_count
            FROM job_daily_stats
            WHERE stat_date >= ? AND category != 'Unknown'
            GROUP BY stat_date
            ORDER BY stat_date ASC
            """,
            [cutoff],
        ).fetchall()

        return [
            {"date": str(r[0]), "added_count": r[1], "removed_count": r[2]}
            for r in rows
        ]

    def get_active_jobs_over_time(self, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)

        rows = self._con.execute(
            """
            SELECT stat_date AS day, SUM(active_count)::INTEGER AS active_count
            FROM job_daily_stats
            WHERE stat_date >= ? AND category != 'Unknown'
            GROUP BY stat_date
            ORDER BY stat_date ASC
            """,
            [cutoff],
        ).fetchall()

        return [{"date": str(r[0]), "active_count": r[1]} for r in rows]

    def backfill_job_daily_stats(self, limit_days: int = 365) -> dict:
        """One-time backfill of job_daily_stats from jobs table for historical dates."""
        from datetime import timedelta

        today = _utcnow().date()
        if limit_days <= 0:
            try:
                row = self._con.execute(
                    """
                    SELECT MIN(LEAST(
                        COALESCE(CAST(posted_date AS DATE), DATE '9999-12-31'),
                        COALESCE(CAST(first_seen_at AS DATE), DATE '9999-12-31'),
                        COALESCE(CAST(last_seen_at AS DATE), DATE '9999-12-31')
                    ))
                    FROM jobs
                    WHERE (job_source = 'mcf' OR job_source IS NULL)
                    """
                ).fetchone()
            except duckdb.ProgrammingError:
                row = None
            start_date = row[0] if row and row[0] and str(row[0]) != "9999-12-31" else today
        else:
            start_date = today - timedelta(days=limit_days)

        cat_ex = "COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(categories_json, '$[0]'), '')), ''), 'Unknown')"
        et_ex = "COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(employment_types_json, '$[0]'), '')), ''), 'Unknown')"
        pl_ex = "COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(position_levels_json, '$[0]'), '')), ''), 'Unknown')"
        mcf = "AND (job_source = 'mcf' OR job_source IS NULL)"

        days_processed = 0
        d = start_date
        while d <= today:
            try:
                self._con.execute(
                    f"""
                    INSERT INTO job_daily_stats
                        (stat_date, category, employment_type, position_level, active_count, added_count, removed_count)
                    SELECT
                        ? AS stat_date,
                        {cat_ex} AS category,
                        {et_ex} AS employment_type,
                        {pl_ex} AS position_level,
                        COUNT(*) FILTER (
                            WHERE posted_date IS NOT NULL AND CAST(posted_date AS DATE) <= ?
                            AND (is_active = TRUE OR (last_seen_at IS NOT NULL AND CAST(last_seen_at AS DATE) > ?))
                        )::INTEGER AS active_count,
                        COUNT(*) FILTER (
                            WHERE (posted_date IS NOT NULL AND CAST(posted_date AS DATE) = ?)
                            OR (first_seen_at IS NOT NULL AND CAST(first_seen_at AS DATE) = ?)
                        )::INTEGER AS added_count,
                        COUNT(*) FILTER (
                            WHERE last_seen_at IS NOT NULL AND CAST(last_seen_at AS DATE) = ? AND is_active = FALSE
                        )::INTEGER AS removed_count
                    FROM jobs
                    WHERE 1=1 {mcf}
                    GROUP BY 2, 3, 4
                    HAVING COUNT(*) FILTER (
                        WHERE posted_date IS NOT NULL AND CAST(posted_date AS DATE) <= ?
                        AND (is_active = TRUE OR (last_seen_at IS NOT NULL AND CAST(last_seen_at AS DATE) > ?))
                    ) > 0
                    OR COUNT(*) FILTER (
                        WHERE (posted_date IS NOT NULL AND CAST(posted_date AS DATE) = ?)
                        OR (first_seen_at IS NOT NULL AND CAST(first_seen_at AS DATE) = ?)
                    ) > 0
                    OR COUNT(*) FILTER (
                        WHERE last_seen_at IS NOT NULL AND CAST(last_seen_at AS DATE) = ? AND is_active = FALSE
                    ) > 0
                    ON CONFLICT (stat_date, category, employment_type, position_level)
                    DO UPDATE SET
                        active_count = EXCLUDED.active_count,
                        added_count = EXCLUDED.added_count,
                        removed_count = EXCLUDED.removed_count
                    """,
                    [d, d, d, d, d, d, d, d, d, d, d],
                )
                days_processed += 1
            except duckdb.ProgrammingError:
                pass
            d += timedelta(days=1)

        return {"rows_upserted": days_processed, "date_start": str(start_date), "date_end": str(today)}

    def update_daily_stats(self, run_id: str) -> None:
        """Upsert today's aggregated stats by category x employment_type x position_level."""
        today = _utcnow().date()
        try:
            rows = self._con.execute(
                """
                SELECT j.job_uuid, j.is_active, j.categories_json, j.employment_types_json, j.position_levels_json,
                       jrs.status
                FROM jobs j
                LEFT JOIN job_run_status jrs ON jrs.job_uuid = j.job_uuid AND jrs.run_id = ?
                """,
                [run_id],
            ).fetchall()
        except duckdb.ProgrammingError:
            return
        agg: dict[tuple[str, str, str], dict[str, int]] = {}
        for job_uuid, is_active, cat_json, et_json, pl_json, status in rows:
            cats = json.loads(cat_json) if cat_json else []
            ets = json.loads(et_json) if et_json else []
            pls = json.loads(pl_json) if pl_json else []
            cat = (cats[0] if cats else "Unknown").strip() or "Unknown"
            et = (ets[0] if ets else "Unknown").strip() or "Unknown"
            pl = (pls[0] if pls else "Unknown").strip() or "Unknown"
            key = (cat, et, pl)
            if key not in agg:
                agg[key] = {"active_count": 0, "added_count": 0, "removed_count": 0}
            if is_active:
                agg[key]["active_count"] += 1
            if status == "added":
                agg[key]["added_count"] += 1
            elif status == "removed":
                agg[key]["removed_count"] += 1
        for (cat, et, pl), counts in agg.items():
            self._con.execute(
                """
                INSERT INTO job_daily_stats(stat_date, category, employment_type, position_level,
                    active_count, added_count, removed_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (stat_date, category, employment_type, position_level)
                DO UPDATE SET
                    active_count = EXCLUDED.active_count,
                    added_count = job_daily_stats.added_count + EXCLUDED.added_count,
                    removed_count = job_daily_stats.removed_count + EXCLUDED.removed_count
                """,
                [today, cat, et, pl, counts["active_count"], counts["added_count"], counts["removed_count"]],
            )

    def delete_inactive_job_embeddings(self) -> int:
        """Delete embeddings for inactive jobs that no user has ever interacted with."""
        rows = self._con.execute(
            """
            SELECT e.job_uuid
            FROM job_embeddings e
            JOIN jobs j ON j.job_uuid = e.job_uuid
            WHERE j.is_active = FALSE
              AND NOT EXISTS (SELECT 1 FROM job_interactions i WHERE i.job_uuid = e.job_uuid)
            """
        ).fetchall()
        uuids = [r[0] for r in rows]
        if not uuids:
            return 0
        placeholders = ", ".join("?" for _ in uuids)
        self._con.execute(f"DELETE FROM job_embeddings WHERE job_uuid IN ({placeholders})", uuids)
        return len(uuids)

    def get_jobs_by_category(self, limit_days: int = 90, limit: int = 30) -> list[dict]:
        try:
            rows = self._con.execute(
                """
                SELECT category, SUM(active_count)::INTEGER AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND category != 'Unknown'
                GROUP BY category
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            rows = []
        if rows:
            return [{"category": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        try:
            rows = self._con.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(COALESCE(json_extract_string(categories_json, '$[0]'), '')), ''),
                        'Unknown'
                    ) AS category,
                    COUNT(*)::INTEGER AS count
                FROM jobs
                WHERE is_active = TRUE
                  AND (job_source = 'mcf' OR job_source IS NULL)
                GROUP BY 1
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            return []
        return [{"category": r[0], "count": r[1]} for r in rows]

    def get_category_trends(self, category: str, limit_days: int = 90) -> list[dict]:
        from datetime import timedelta

        cutoff = _utcnow().date() - timedelta(days=limit_days)
        today = _utcnow().date()
        cat_extract = "COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(categories_json, '$[0]'), '')), ''), 'Unknown')"

        try:
            rows = self._con.execute(
                """
                SELECT stat_date AS day,
                       SUM(active_count)::INTEGER AS active_count,
                       SUM(added_count)::INTEGER AS added_count,
                       SUM(removed_count)::INTEGER AS removed_count
                FROM job_daily_stats
                WHERE category = ? AND stat_date >= ?
                GROUP BY stat_date
                ORDER BY stat_date ASC
                """,
                [category, cutoff],
            ).fetchall()
        except duckdb.ProgrammingError:
            rows = []

        if rows:
            return [
                {"date": str(r[0]), "active_count": r[1], "added_count": r[2], "removed_count": r[3]}
                for r in rows
            ]

        # Fallback: compute from jobs table for this category
        result = []
        for i in range(limit_days + 1):
            d = cutoff + timedelta(days=i)
            if d > today:
                break
            row = self._con.execute(
                f"""
                SELECT COUNT(*)::INTEGER FROM jobs j
                WHERE (j.job_source = 'mcf' OR j.job_source IS NULL)
                  AND {cat_extract} = ?
                  AND j.posted_date IS NOT NULL
                  AND CAST(j.posted_date AS DATE) <= ?
                  AND (j.is_active = TRUE
                       OR (j.last_seen_at IS NOT NULL AND CAST(j.last_seen_at AS DATE) > ?))
                """,
                [category, d, d],
            ).fetchone()
            result.append({"date": str(d), "active_count": row[0] if row else 0, "added_count": 0, "removed_count": 0})
        return result

    def get_category_stats(self, category: str) -> dict:
        bucket_order = [
            "$0-1k", "$1k-2k", "$2k-3k", "$3k-4k", "$4k-5k",
            "$5k-6k", "$6k-8k", "$8k-10k", "$10k+", "Not disclosed",
        ]

        try:
            # Single pass over filtered rows using a MATERIALIZED CTE
            rows = self._con.execute(
                """
                WITH filtered AS MATERIALIZED (
                    SELECT
                        COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(employment_types_json, '$[0]'), '')), ''), 'Unknown') AS et,
                        COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(position_levels_json, '$[0]'), '')), ''), 'Unknown') AS pl,
                        salary_min
                    FROM jobs
                    WHERE is_active = TRUE
                      AND (job_source = 'mcf' OR job_source IS NULL)
                      AND COALESCE(NULLIF(TRIM(COALESCE(json_extract_string(categories_json, '$[0]'), '')), ''), 'Unknown') = ?
                )
                SELECT 'summary' AS kind, '' AS val,
                       COUNT(*)::VARCHAR AS a,
                       COALESCE(ROUND(AVG(salary_min), 0)::INTEGER::VARCHAR, '') AS b
                FROM filtered
                UNION ALL
                SELECT 'et', et, cnt::VARCHAR, ''
                FROM (
                    SELECT et, COUNT(*)::INTEGER AS cnt
                    FROM filtered WHERE et != 'Unknown'
                    GROUP BY et ORDER BY cnt DESC LIMIT 20
                )
                UNION ALL
                SELECT 'pl', pl, cnt::VARCHAR, ''
                FROM (
                    SELECT pl, COUNT(*)::INTEGER AS cnt
                    FROM filtered WHERE pl != 'Unknown'
                    GROUP BY pl ORDER BY cnt DESC LIMIT 20
                )
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
                       COUNT(*)::VARCHAR, ''
                FROM filtered GROUP BY 2
                """,
                [category],
            ).fetchall()
        except duckdb.ProgrammingError:
            return {
                "active_count": 0,
                "top_employment_type": None,
                "top_position_level": None,
                "avg_salary": None,
                "employment_types": [],
                "position_levels": [],
                "salary_buckets": [],
            }

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
        try:
            rows = self._con.execute(
                """
                SELECT employment_type, SUM(active_count)::INTEGER AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND employment_type != 'Unknown'
                GROUP BY employment_type
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            rows = []
        if rows:
            return [{"employment_type": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        try:
            rows = self._con.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(COALESCE(json_extract_string(employment_types_json, '$[0]'), '')), ''),
                        'Unknown'
                    ) AS employment_type,
                    COUNT(*)::INTEGER AS count
                FROM jobs
                WHERE is_active = TRUE
                  AND (job_source = 'mcf' OR job_source IS NULL)
                GROUP BY 1
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            return []
        return [{"employment_type": r[0], "count": r[1]} for r in rows]

    def get_jobs_by_position_level(self, limit_days: int = 90, limit: int = 20) -> list[dict]:
        try:
            rows = self._con.execute(
                """
                SELECT position_level, SUM(active_count)::INTEGER AS count
                FROM job_daily_stats
                WHERE stat_date = (SELECT MAX(stat_date) FROM job_daily_stats)
                  AND position_level != 'Unknown'
                GROUP BY position_level
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            rows = []
        if rows:
            return [{"position_level": r[0], "count": r[1]} for r in rows]
        # Fallback to jobs table if job_daily_stats is empty
        try:
            rows = self._con.execute(
                """
                SELECT
                    COALESCE(
                        NULLIF(TRIM(COALESCE(json_extract_string(position_levels_json, '$[0]'), '')), ''),
                        'Unknown'
                    ) AS position_level,
                    COUNT(*)::INTEGER AS count
                FROM jobs
                WHERE is_active = TRUE
                  AND (job_source = 'mcf' OR job_source IS NULL)
                GROUP BY 1
                ORDER BY count DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        except duckdb.ProgrammingError:
            return []
        return [{"position_level": r[0], "count": r[1]} for r in rows]

    def get_salary_distribution(self) -> list[dict]:
        bucket_order = [
            "$0-1k", "$1k-2k", "$2k-3k", "$3k-4k", "$4k-5k",
            "$5k-6k", "$6k-8k", "$8k-10k", "$10k+", "Not disclosed",
        ]
        try:
            rows = self._con.execute(
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
                    COUNT(*)::INTEGER AS count
                FROM jobs
                WHERE is_active = TRUE AND (job_source = 'mcf' OR job_source IS NULL)
                GROUP BY 1
                """
            ).fetchall()
        except duckdb.ProgrammingError:
            return [{"bucket": b, "count": 0} for b in bucket_order]
        by_bucket = {r[0]: r[1] for r in rows}
        return [{"bucket": b, "count": by_bucket.get(b, 0)} for b in bucket_order]

    def get_jobs_with_salary_by_uuids(self, job_uuids: list[str]) -> list[dict]:
        if not job_uuids:
            return []
        placeholders = ", ".join("?" * len(job_uuids))
        rows = self._con.execute(
            f"SELECT job_uuid, title, company_name, job_url, salary_min, salary_max "
            f"FROM jobs WHERE job_uuid IN ({placeholders})",
            job_uuids,
        ).fetchall()
        cols = ["job_uuid", "title", "company_name", "job_url", "salary_min", "salary_max"]
        return [dict(zip(cols, row)) for row in rows]

    def upsert_taste_embedding(self, *, profile_id: str, model_name: str, embedding: Sequence[float]) -> None:
        """Store a taste-profile embedding.

        Uses the key ``{profile_id}:taste`` in candidate_embeddings so it can
        coexist with the resume embedding without a schema change.
        """
        taste_key = f"{profile_id}:taste"
        now = _utcnow()
        emb_list = [float(x) for x in embedding]
        self._con.execute(
            """
            INSERT INTO candidate_embeddings(profile_id, model_name, embedding_json, dim, embedded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (profile_id) DO UPDATE SET
              model_name = excluded.model_name,
              embedding_json = excluded.embedding_json,
              dim = excluded.dim,
              embedded_at = excluded.embedded_at
            """,
            [taste_key, model_name, json.dumps(emb_list), len(emb_list), now],
        )

    def get_taste_embedding(self, profile_id: str) -> list[float] | None:
        """Get taste-profile embedding, or None if not yet computed."""
        taste_key = f"{profile_id}:taste"
        row = self._con.execute(
            "SELECT embedding_json FROM candidate_embeddings WHERE profile_id = ?",
            [taste_key],
        ).fetchone()
        if not row:
            return None
        return json.loads(row[0])

    def get_job_embeddings_for_uuids(self, uuids: list[str]) -> list[tuple[str, list[float]]]:
        """Return (job_uuid, embedding) pairs for the given UUID list.

        Skips UUIDs that have no embedding stored.
        """
        if not uuids:
            return []
        placeholders = ", ".join("?" for _ in uuids)
        rows = self._con.execute(
            f"SELECT job_uuid, embedding_json FROM job_embeddings WHERE job_uuid IN ({placeholders})",
            uuids,
        ).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def get_profile_by_profile_id(self, profile_id: str) -> dict | None:
        """Get profile by profile ID."""
        row = self._con.execute(
            """
            SELECT profile_id, user_id, raw_resume_text, expanded_profile_json,
                   skills_json, experience_json, created_at, updated_at
            FROM candidate_profiles WHERE profile_id = ?
            """,
            [profile_id],
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0],
            "user_id": row[1],
            "raw_resume_text": row[2],
            "expanded_profile_json": json.loads(row[3]) if row[3] else None,
            "skills_json": json.loads(row[4]) if row[4] else None,
            "experience_json": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
            "updated_at": row[7],
        }
