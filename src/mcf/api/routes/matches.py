"""Matches API route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from mcf.api.auth import get_current_user
from mcf.api.cache.matches import get_cached, set_cached
from mcf.api.cache.response import TTL_MATCHES, cache_response
from mcf.api.config import settings
from mcf.api.deps import get_store
from mcf.matching.service import MatchingService

router = APIRouter()


@router.get("/api/matches")
@cache_response(TTL_MATCHES, "matches")
def get_matches(
    exclude_interacted: bool = True,
    exclude_rated_only: bool = False,
    top_k: int = 25,
    offset: int = 0,
    min_similarity: float = 0.0,
    max_days_old: int | None = None,
    mode: str = "resume",
    session_id: str | None = None,
    role_cluster: list[int] = Query(default=[]),
    predicted_tier: list[str] = Query(default=[]),
    user_id: str = Depends(get_current_user),
):
    """Get job matches for the current user.

    *mode* is ``resume`` (default) or ``taste``.
    *exclude_rated_only*: when True, only exclude interested/not_interested (for Discover).
    When False, exclude all interactions (viewed, dismissed, etc.).
    """
    if settings.enable_matches_cache:
        cached = get_cached(
            user_id=user_id,
            mode=mode,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            top_k=top_k,
            offset=offset,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
        )
        if cached is not None:
            return cached

    store = get_store()
    if mode not in ("resume", "taste"):
        raise HTTPException(status_code=400, detail="mode must be 'resume' or 'taste'")
    if not 0.0 <= min_similarity <= 1.0:
        raise HTTPException(status_code=400, detail="min_similarity must be between 0.0 and 1.0")
    if max_days_old is not None and max_days_old <= 0:
        max_days_old = None  # Treat invalid/zero as no filter
    if offset < 0:
        offset = 0

    profile = store.get_profile_by_user_id(user_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail="No profile found. Please process your resume first."
        )

    profile_id = profile["profile_id"]
    svc = MatchingService(store)

    candidate_tier: str | None = None
    if mode == "taste":
        taste_emb = store.get_taste_embedding(profile_id)
        if not taste_emb:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No taste profile found. Go to Resume, rate some jobs, "
                    "then click Update Taste Profile."
                ),
            )
        matches, total, new_session_id = svc.match_taste_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            offset=offset,
            exclude_rated=exclude_interacted,
            user_id=user_id,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            role_clusters=role_cluster or None,
            predicted_tiers=predicted_tier or None,
        )
    else:
        # exclude_rated_only: only interested/not_interested (Discover). Else all interactions.
        matches, total, new_session_id, candidate_tier = svc.match_candidate_to_jobs(
            profile_id=profile_id,
            top_k=top_k,
            offset=offset,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            user_id=user_id,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            role_clusters=role_cluster or None,
            predicted_tiers=predicted_tier or None,
        )

    has_more = offset + len(matches) < total
    result = {
        "matches": matches,
        "total": total,
        "has_more": has_more,
        "mode": mode,
        "session_id": new_session_id,
        "candidate_tier": candidate_tier,
    }
    if settings.enable_matches_cache:
        set_cached(
            user_id=user_id,
            mode=mode,
            exclude_interacted=exclude_interacted,
            exclude_rated_only=exclude_rated_only,
            top_k=top_k,
            offset=offset,
            min_similarity=min_similarity,
            max_days_old=max_days_old,
            session_id=session_id,
            result=result,
        )
    return result
