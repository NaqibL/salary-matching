"""Crawl Phase 1 helper: link freshly fetched jobs to existing postings (SGSAL-024).

A repost (same title + description as a job we already hold) gets
``canonical_job_uuid`` pointed at that job, inherits its LLM fields and Jev
labels, and is dropped from the embed list so the crawl does not pay for the
cleaner, the embedder or Jev again. Any storage failure degrades to "nothing
skipped" — the crawl then behaves exactly as before this feature.
"""
from __future__ import annotations

from typing import Sequence

from mcf.lib.pipeline.posting_key import plan_repost_links, posting_key
from mcf.lib.sources.base import NormalizedJob
from mcf.lib.storage.base import Storage


def link_reposts_for_batch(store: Storage, fetched: Sequence[NormalizedJob]) -> set[str]:
    """Return the job_uuids that are reposts and must skip cleaner/embed/Jev."""
    if not fetched:
        return set()
    keys = {n.job_uuid: posting_key(n.title, n.description) for n in fetched}
    try:
        store.set_content_hashes(list(keys.items()))
        hashes = sorted({k for k in keys.values() if k})
        canon = store.find_canonicals(hashes) if hashes else {}
        pairs, reposts = plan_repost_links(keys, canon)
        store.link_reposts(pairs)
    except Exception as e:  # noqa: BLE001 — never let bookkeeping abort a crawl
        print(f"Warning: repost linking failed, embedding every job this run: {e}")
        return set()
    if reposts:
        print(f"{len(reposts)} reposts linked to existing postings (skipped cleaner/embed/Jev)")
    return reposts
