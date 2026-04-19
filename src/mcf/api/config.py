"""API configuration."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings.

    Local dev: set values in a .env file in the project root.
    Production: set as environment variables on Railway / GitHub Actions.
    """

    # --- Database ---
    # Set DATABASE_URL to a postgres:// connection string to use PostgreSQL
    # (e.g. Supabase). Leave unset to fall back to local DuckDB.
    database_url: str | None = None
    db_path: str = os.getenv("DB_PATH", "data/mcf.duckdb")

    # --- Supabase (optional, enables auth + file storage) ---
    supabase_url: str | None = None
    supabase_service_key: str | None = None
    # JWT secret from Supabase Dashboard > Settings > API > JWT Settings
    supabase_jwt_secret: str | None = None

    # --- User (local dev fallback when auth is disabled) ---
    default_user_id: str = os.getenv("DEFAULT_USER_ID", "default_user")

    # --- Resume (local dev fallback when file upload is disabled) ---
    resume_path: str = os.getenv("RESUME_PATH", "resume/resume.pdf")

    # --- Matches cache (FastAPI in-memory) ---
    # Set ENABLE_MATCHES_CACHE=1 when bypassing Next.js proxy (frontend calls FastAPI directly).
    # Next.js unstable_cache is preferred on Vercel; use this when FastAPI is on Railway/VPS.
    enable_matches_cache: bool = os.getenv("ENABLE_MATCHES_CACHE", "0") in ("1", "true", "yes")

    # --- Active jobs pool cache ---
    # Cache (job_uuid, embedding, last_seen_at) for 15 min. Reduces DB round-trips for matching.
    # Invalidate via invalidate_active_jobs_pool() when crawl completes.
    enable_active_jobs_pool_cache: bool = os.getenv("ENABLE_ACTIVE_JOBS_POOL_CACHE", "0") in ("1", "true", "yes")

    # --- Response cache (dashboard 1h, job detail 24h) ---
    # TTL-based in-memory cache. Invalidate via POST /api/admin/invalidate-cache.
    enable_response_cache: bool = os.getenv("ENABLE_RESPONSE_CACHE", "0") in ("1", "true", "yes")

    # --- Embeddings cache (by content hash) ---
    # Avoid re-computing BGE embeddings for same text. LRU in-memory + optional DB table.
    enable_embeddings_cache: bool = os.getenv("ENABLE_EMBEDDINGS_CACHE", "1") in ("1", "true", "yes")

    # --- LLM job description cleaning (optional, used during re-embed/crawl) ---
    openrouter_api_key: str | None = None
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")
    job_extractor_llm_enabled: bool = os.getenv("JOB_EXTRACTOR_LLM_ENABLED", "0") in ("1", "true", "yes")

    # --- Admin ---
    # Comma-separated user IDs allowed to access admin endpoints (when using JWT auth)
    admin_user_ids: str = os.getenv("ADMIN_USER_IDS", "")
    cron_secret: str | None = os.getenv("CRON_SECRET") or os.getenv("REVALIDATE_SECRET")

    # --- API ---
    api_port: int = int(os.getenv("API_PORT", "8000"))
    # Comma-separated list of allowed CORS origins (e.g. https://myapp.vercel.app)
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    # When true, allow requests without Authorization header to use default_user_id (local dev only)
    allow_anonymous_local: bool = os.getenv("ALLOW_ANONYMOUS_LOCAL", "false").lower() in ("1", "true", "yes")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def cors_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def auth_enabled(self) -> bool:
        """Auth is enabled when Supabase is configured (JWT secret or URL for JWKS)."""
        return bool(self.supabase_jwt_secret or self.supabase_url)

    @property
    def admin_user_ids_set(self) -> set[str]:
        """Parse ADMIN_USER_IDS into a set."""
        return {x.strip() for x in self.admin_user_ids.split(",") if x.strip()}

    @property
    def storage_enabled(self) -> bool:
        """Supabase Storage is enabled when URL + service key are both set."""
        return bool(self.supabase_url and self.supabase_service_key)


settings = Settings()
