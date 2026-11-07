# src/mcf/lib/pipeline/posting_key.py
"""Content-addressed posting key and repost link planning (SGSAL-024).

The key is a hash of the *text the embedder and LLM cleaner see*: title +
description. Company is deliberately excluded (it is not in the embedded text,
so agency reposts under different company names are byte-identical vectors).
This is the single implementation; the backfill and the crawl both import it.
Never re-implement it in SQL.
"""
from __future__ import annotations

import hashlib


def posting_key(title: str | None, description: str | None) -> str | None:
    """Return a 32-hex-char key for (title, description), or None when there is no description.

    Normalisation: whitespace runs collapsed to one space and trimmed in both
    fields; the title is additionally case-folded (titles vary in casing
    between reposts, descriptions do not).
    """
    if not description or not description.strip():
        return None
    t = " ".join((title or "").split()).casefold()
    d = " ".join(description.split())
    return hashlib.sha256(f"{t}\n{d}".encode("utf-8")).hexdigest()[:32]


def plan_repost_links(
    keys: dict[str, str | None],
    canon: dict[str, str],
) -> tuple[list[tuple[str, str]], set[str]]:
    """Decide, for each job, which job owns its vector.

    Args:
        keys: job_uuid -> posting key (None when the job has no description).
              Iteration order decides which of several new jobs with the same
              key becomes canonical (the first one).
        canon: posting key -> canonical job_uuid already in the DB. Mutated:
               keys that were unknown get the new canonical added.

    Returns:
        (pairs, reposts): ``pairs`` has one ``(job_uuid, canonical_job_uuid)``
        per input job (self-pairs for canonicals); ``reposts`` is the set of
        job_uuids that point at a *different* job and must skip
        cleaner/embed/Jev.
    """
    pairs: list[tuple[str, str]] = []
    reposts: set[str] = set()
    for job_uuid, key in keys.items():
        if key is None:
            pairs.append((job_uuid, job_uuid))
            continue
        owner = canon.get(key)
        if owner is None or owner == job_uuid:
            canon[key] = job_uuid
            pairs.append((job_uuid, job_uuid))
        else:
            pairs.append((job_uuid, owner))
            reposts.add(job_uuid)
    return pairs, reposts
