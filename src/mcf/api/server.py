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

from mcf.api.config import settings
from mcf.api.deps import _make_store, close_store, set_store
from mcf.api.routes import admin, dashboard, jobs, lowball, matches, profile

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = _make_store()
    set_store(store)
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
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
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


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/cors-check")
def cors_check(request: Request):
    """Debug: returns request origin and whether it's in ALLOWED_ORIGINS.

    Use this to verify CORS is configured correctly when upload fails with
    'CORS missing Allow Origin'. Call from the browser console:
    fetch('https://your-api.railway.app/api/cors-check').then(r=>r.json()).then(console.log)
    """
    origin = request.headers.get("origin", "(none)")
    allowed = settings.cors_origins
    return {
        "request_origin": origin,
        "allowed_origins": allowed,
        "origin_allowed": origin in allowed,
    }
