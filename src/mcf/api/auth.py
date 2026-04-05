"""Authentication dependency for FastAPI.

When Supabase is configured (SUPABASE_JWT_SECRET or SUPABASE_URL), every request
must carry a valid Supabase JWT in the Authorization header. The JWT subject
(``sub`` claim) becomes the ``user_id`` threaded through every endpoint.

- New JWT Signing Keys: uses JWKS from SUPABASE_URL (no secret needed).
- Legacy: uses SUPABASE_JWT_SECRET with HS256.

When neither is set (local development), auth is skipped and all requests are
attributed to ``settings.default_user_id``.
"""

from __future__ import annotations

from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status

from mcf.api.config import settings

# JWKS client for new Supabase JWT Signing Keys (cached per process)
_jwks_client: jwt.PyJWKClient | None = None


def _get_jwks_client() -> jwt.PyJWKClient:
    """Lazy-init JWKS client from SUPABASE_URL."""
    global _jwks_client
    if _jwks_client is None:
        url = settings.supabase_url or ""
        url = url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        _jwks_client = jwt.PyJWKClient(url)
    return _jwks_client


def _verify_token(token: str) -> str:
    """Verify a Supabase JWT and return the user_id (sub claim)."""
    try:
        if settings.supabase_jwt_secret:
            # Legacy: symmetric secret (HS256)
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        elif settings.supabase_url:
            # New JWT Signing Keys: JWKS (ES256, RS256, etc.)
            jwks = _get_jwks_client()
            key = jwks.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                key.key,
                algorithms=["ES256", "RS256"],
                options={"verify_aud": False},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Auth not configured",
            )

        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing sub claim",
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}"
        )


def get_optional_user(authorization: Optional[str] = Header(default=None)) -> str | None:
    """Like get_current_user but returns None instead of raising 401 when unauthenticated.

    Use for endpoints that are publicly accessible but can optionally use a user
    identity if one is provided (e.g. dashboard analytics, lowball checker).
    """
    if not settings.auth_enabled:
        return settings.default_user_id
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return _verify_token(token)
    except HTTPException:
        return None


def get_current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """FastAPI dependency that resolves the current user_id.

    - If auth is disabled (no SUPABASE_JWT_SECRET): returns default_user_id.
    - If auth is enabled: validates Bearer token and returns the user's UUID.
    """
    if not settings.auth_enabled:
        return settings.default_user_id

    if not authorization:
        if settings.allow_anonymous_local:
            return settings.default_user_id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be: Bearer <token>",
        )

    return _verify_token(token)
