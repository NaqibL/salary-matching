"""Profile API routes — resume upload, processing, and taste profile."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from mcf.api.auth import get_current_user
from mcf.api.cache.matches import invalidate_user
from mcf.api.cache.response import invalidate_matches_for_user
from mcf.api.config import settings
from mcf.api.deps import get_embedder, get_store
from mcf.lib.embeddings.resume import extract_resume_text, preprocess_resume_text
from mcf.lib.storage.base import Storage
from mcf.matching.service import MatchingService

router = APIRouter()


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------


@router.get("/api/profile")
def get_profile(user_id: str = Depends(get_current_user)):
    """Get current user profile and resume status."""
    store = get_store()
    profile = store.get_profile_by_user_id(user_id)
    resume_path = Path(settings.resume_path)
    resume_exists = resume_path.exists()
    return {
        "user_id": user_id,
        "profile": profile,
        "resume_path": str(resume_path),
        "resume_exists": resume_exists,
    }


@router.post("/api/profile/process-resume")
async def process_resume(user_id: str = Depends(get_current_user)):
    """Process resume from local file or Supabase Storage.

    Tries local file first (dev). If not found and profile has resume_storage_path,
    fetches from Supabase Storage and processes that. Fixes Re-process in production.
    """
    store = get_store()
    resume_path = Path(settings.resume_path)

    if resume_path.exists():
        try:
            resume_text = extract_resume_text(resume_path)
            return _process_resume_text(store, user_id, resume_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")

    # Local file missing — try Supabase Storage
    profile = store.get_profile_by_user_id(user_id)
    if not profile or not profile.get("resume_storage_path"):
        raise HTTPException(
            status_code=404,
            detail="No resume found. Upload a resume first, or ensure the file exists at the configured path.",
        )

    storage_path = profile["resume_storage_path"]
    if not settings.storage_enabled:
        raise HTTPException(
            status_code=503,
            detail="Resume is in cloud storage but Supabase Storage is not configured.",
        )

    try:
        data = await _download_from_supabase(storage_path)
        resume_text = extract_resume_text(data)
        return _process_resume_text(store, user_id, resume_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process resume from storage: {e}")


@router.post("/api/profile/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """Upload a resume file, extract its text, and update the profile + embedding.

    Accepts PDF or DOCX.  If Supabase Storage is configured the raw file is
    also stored there so it can be re-processed later.
    """
    allowed = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Upload a PDF or DOCX.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Optionally push to Supabase Storage
    storage_path: str | None = None
    if settings.storage_enabled:
        storage_path = await _upload_to_supabase(data, user_id, file.filename or "resume.pdf")

    try:
        resume_text = extract_resume_text(data)
        store = get_store()
        result = _process_resume_text(store, user_id, resume_text, storage_path=storage_path)
        result["storage_path"] = storage_path
        return result
    except Exception as e:
        logging.exception("upload_resume failed")
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")


@router.post("/api/profile/reset-ratings")
def reset_ratings(user_id: str = Depends(get_current_user)):
    """Reset job interactions and taste profile for the current user (for testing)."""
    store = get_store()
    result = store.reset_profile_ratings(user_id)
    return result


@router.post("/api/profile/compute-taste")
def compute_taste(user_id: str = Depends(get_current_user)):
    """Build / refresh the taste-profile embedding from Interested/Not Interested ratings."""
    store = get_store()
    profile = store.get_profile_by_user_id(user_id)
    if not profile:
        raise HTTPException(
            status_code=404, detail="No profile found. Please process your resume first."
        )
    result = MatchingService(store).compute_and_store_taste(
        profile_id=profile["profile_id"], user_id=user_id
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("reason", "Failed to compute taste profile")
        )
    if settings.enable_matches_cache:
        invalidate_user(user_id)
    if settings.enable_response_cache:
        invalidate_matches_for_user(user_id)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _process_resume_text(
    store: Storage, user_id: str, resume_text: str, storage_path: str | None = None
) -> dict:
    """Create/update profile + embedding from resume text. Returns response dict."""
    profile = store.get_profile_by_user_id(user_id)
    if profile:
        profile_id = profile["profile_id"]
        store.update_profile(
            profile_id=profile_id,
            raw_resume_text=resume_text,
            resume_storage_path=storage_path,
        )
    else:
        profile_id = secrets.token_urlsafe(16)
        store.create_profile(
            profile_id=profile_id,
            user_id=user_id,
            raw_resume_text=resume_text,
        )
        if storage_path:
            store.update_profile(profile_id=profile_id, resume_storage_path=storage_path)

    embedder = get_embedder()
    preprocessed = preprocess_resume_text(resume_text)
    try:
        embedding = embedder.embed_resume(preprocessed)
    except Exception as e:
        logging.exception("embed_resume failed: %s", e)
        raise
    store.upsert_candidate_embedding(
        profile_id=profile_id,
        model_name=embedder.model_name,
        embedding=embedding,
    )
    if settings.enable_matches_cache:
        invalidate_user(user_id)
    if settings.enable_response_cache:
        invalidate_matches_for_user(user_id)
    return {"status": "ok", "profile_id": profile_id, "message": "Resume processed successfully"}


async def _download_from_supabase(storage_path: str) -> bytes:
    """Download file bytes from Supabase Storage. storage_path is e.g. resumes/{user_id}/resume.pdf."""
    url = f"{settings.supabase_url}/storage/v1/object/{storage_path}"
    headers = {"Authorization": f"Bearer {settings.supabase_service_key}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=30.0)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch resume from storage: {resp.status_code} {resp.text[:200]}",
            )
    return resp.content


async def _upload_to_supabase(data: bytes, user_id: str, filename: str) -> str:
    """Upload file bytes to Supabase Storage and return the storage path."""
    ext = Path(filename).suffix or ".pdf"
    path = f"resumes/{user_id}/resume{ext}"
    url = f"{settings.supabase_url}/storage/v1/object/resumes/{user_id}/resume{ext}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "Content-Type": "application/octet-stream",
        "x-upsert": "true",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.put(url, content=data, headers=headers, timeout=30.0)
        if resp.status_code not in (200, 201):
            raise HTTPException(
                status_code=502,
                detail=f"Supabase Storage upload failed: {resp.status_code} {resp.text}",
            )
    return path
