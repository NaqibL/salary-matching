"""Companies route — returns distinct company names for autocomplete."""

from __future__ import annotations

from fastapi import APIRouter

from mcf.api.deps import get_store

router = APIRouter()


@router.get("/api/companies")
def list_companies() -> list[str]:
    """Return sorted list of distinct company names from active jobs."""
    store = get_store()
    return store.get_distinct_companies()
