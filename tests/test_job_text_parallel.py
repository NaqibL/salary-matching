"""Tests for the thread-pooled text builder used by re-embed and the crawl.

No network: a mock cleaner that sleeps briefly stands in for the LLM call.
"""

from __future__ import annotations

import threading
import time

import mcf.lib.embeddings.job_description_extractor as _jde
from mcf.lib.embeddings.job_description_extractor import (
    LLMCleanResult,
    register_llm_cleaner,
)
from mcf.lib.embeddings.job_text import build_texts_parallel, default_llm_workers


class _SlowCleaner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    def should_clean(self, description: str) -> bool:
        return True

    def clean(self, description: str, title: str | None) -> LLMCleanResult:
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        time.sleep(0.05)
        with self.lock:
            self.in_flight -= 1
        return LLMCleanResult(cleaned_text=description.upper())


def _reset() -> None:
    _jde._LLM_ENABLED = False
    register_llm_cleaner(None)  # type: ignore[arg-type]


def _enable(cleaner) -> None:
    _jde._LLM_ENABLED = True
    register_llm_cleaner(cleaner)


class TestBuildTextsParallel:
    def setup_method(self):
        _reset()

    def teardown_method(self):
        _reset()

    def test_preserves_order_and_runs_concurrently(self):
        cleaner = _SlowCleaner()
        _enable(cleaner)
        items = list(range(40))

        def build(i: int) -> str:
            return cleaner.clean(f"job {i}", None).cleaned_text

        out = list(build_texts_parallel(items, build, workers=8))
        assert out == [f"JOB {i}" for i in items]
        assert cleaner.max_in_flight > 1

    def test_inline_when_no_cleaner_registered(self):
        seen_threads: set[int] = set()

        def build(i: int) -> int:
            seen_threads.add(threading.get_ident())
            return i * 2

        out = list(build_texts_parallel([1, 2, 3], build, workers=8))
        assert out == [2, 4, 6]
        assert seen_threads == {threading.get_ident()}

    def test_single_worker_runs_inline(self):
        _enable(_SlowCleaner())
        seen_threads: set[int] = set()

        def build(i: int) -> int:
            seen_threads.add(threading.get_ident())
            return i

        assert list(build_texts_parallel([1, 2], build, workers=1)) == [1, 2]
        assert seen_threads == {threading.get_ident()}

    def test_empty_input(self):
        _enable(_SlowCleaner())
        assert list(build_texts_parallel([], lambda x: x, workers=4)) == []

    def test_default_workers_env(self, monkeypatch):
        monkeypatch.delenv("LLM_CLEAN_WORKERS", raising=False)
        assert default_llm_workers() == 8
        monkeypatch.setenv("LLM_CLEAN_WORKERS", "6")
        assert default_llm_workers() == 6
        monkeypatch.setenv("LLM_CLEAN_WORKERS", "junk")
        assert default_llm_workers() == 8
        monkeypatch.setenv("LLM_CLEAN_WORKERS", "0")
        assert default_llm_workers() == 1
