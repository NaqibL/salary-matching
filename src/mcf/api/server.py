"""FastAPI server — app factory, lifespan, and middleware."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import HTTPException

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from mcf.api.config import settings
from mcf.api.deps import _make_store, close_store, set_embedder, set_store
from mcf.api.limiter import limiter
from mcf.api.routes import admin, companies, dashboard, jobs, lowball, matches, profile

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.allow_anonymous_local and settings.auth_enabled:
        logger.warning(
            "SECURITY: ALLOW_ANONYMOUS_LOCAL=true is set while auth is enabled "
            "(SUPABASE_URL/SUPABASE_JWT_SECRET configured). This disables all FastAPI "
            "authentication. Remove ALLOW_ANONYMOUS_LOCAL from production environment."
        )

    store = _make_store()
    set_store(store)
    from mcf.lib.embeddings.embedder import Embedder, EmbedderConfig
    from mcf.lib.embeddings.embeddings_cache import EmbeddingsCache
    cache = EmbeddingsCache(store=store) if settings.enable_embeddings_cache else None
    set_embedder(Embedder(EmbedderConfig(), embeddings_cache=cache))
    if settings.enable_active_jobs_pool_cache:
        try:
            from mcf.api.cache.job_pool import get_pool_or_fetch as _warm_pool
            _warm_pool(store)
            logger.info("Active jobs pool warmed on startup")
        except Exception:
            logger.warning("Failed to warm active jobs pool on startup", exc_info=True)
    yield
    close_store()


app = FastAPI(title="Job Matcher API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


def _add_cors_if_missing(response, request: Request) -> None:
    """Add CORS headers to response when missing (e.g. on 500 errors)."""
    origin = request.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        return
    existing = {h.lower() for h in response.headers}
    if "access-control-allow-origin" not in existing:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"


class CORSEnforcementMiddleware(BaseHTTPMiddleware):
    """Ensure CORS headers on all responses when request has Origin.

    FastAPI's CORSMiddleware can omit headers on 500 and other error paths. This
    safety net ensures the browser doesn't block with 'missing Allow Origin'.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception as exc:
            import traceback

            if not isinstance(exc, HTTPException):
                logging.error("Unhandled exception on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
            status = exc.status_code if isinstance(exc, HTTPException) else 500
            detail = exc.detail if isinstance(exc, HTTPException) else "Internal server error"
            response = JSONResponse(status_code=status, content={"detail": detail})
        _add_cors_if_missing(response, request)
        return response


# CORSEnforcement runs first (outermost); CORSMiddleware handles preflight and normal CORS
app.add_middleware(CORSEnforcementMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(jobs.router)
app.include_router(dashboard.router)
app.include_router(profile.router)
app.include_router(matches.router)
app.include_router(admin.router)
app.include_router(lowball.router)
app.include_router(companies.router)


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}

