"""Crawl-side repost linking (SGSAL-024). Uses an in-memory fake store — no DB, no network."""

from mcf.lib.pipeline.reposts import link_reposts_for_batch
from mcf.lib.sources.base import NormalizedJob


class FakeStore:
    def __init__(self, canonicals: dict[str, str]):
        self._canon = canonicals
        self.hashes: list[tuple[str, str | None]] = []
        self.pairs: list[tuple[str, str]] = []

    def set_content_hashes(self, rows):
        self.hashes.extend(rows)

    def find_canonicals(self, hashes):
        return {h: u for h, u in self._canon.items() if h in hashes}

    def link_reposts(self, pairs):
        self.pairs.extend(pairs)
        return len(pairs)


def _job(uuid: str, title: str, desc: str | None) -> NormalizedJob:
    return NormalizedJob(source_id="mcf", external_id=uuid, title=title, company_name="ACME",
                         location=None, job_url=None, skills=[], description=desc)


def test_repost_of_existing_posting_is_skipped_and_linked():
    from mcf.lib.pipeline.posting_key import posting_key
    old_key = posting_key("Data Analyst", "Build dashboards.")
    store = FakeStore({old_key: "old-1"})
    new = _job("new-1", "data analyst", "Build  dashboards.")
    skip = link_reposts_for_batch(store, [new])
    assert skip == {"new-1"}
    assert store.pairs == [("new-1", "old-1")]
    assert store.hashes == [("new-1", old_key)]


def test_two_new_copies_in_one_batch_share_the_first():
    store = FakeStore({})
    a, b = _job("a", "Chef", "Cook."), _job("b", "Chef", "Cook.")
    skip = link_reposts_for_batch(store, [a, b])
    assert skip == {"b"}
    assert store.pairs == [("a", "a"), ("b", "a")]


def test_textless_job_is_never_skipped():
    store = FakeStore({})
    skip = link_reposts_for_batch(store, [_job("x", "Chef", None)])
    assert skip == set()
    assert store.pairs == [("x", "x")]
    assert store.hashes == [("x", None)]


def test_store_failure_degrades_to_no_skips(capsys):
    class Broken(FakeStore):
        def find_canonicals(self, hashes):
            raise RuntimeError("db down")
    store = Broken({})
    skip = link_reposts_for_batch(store, [_job("a", "Chef", "Cook.")])
    assert skip == set()
    assert "repost linking failed" in capsys.readouterr().out
