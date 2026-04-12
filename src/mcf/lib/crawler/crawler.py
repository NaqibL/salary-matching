"""Crawler for listing job UUIDs from MyCareersFuture."""

import time
from dataclasses import dataclass
from typing import Callable

from mcf.lib.external.client import MCFClient
from mcf.lib.categories import CATEGORIES


@dataclass
class CrawlProgress:
    """Current progress of a crawl operation."""

    total_jobs: int
    """Total jobs available to fetch."""

    fetched: int
    """Jobs fetched so far."""

    elapsed: float
    """Elapsed time in seconds."""

    # Category tracking (for all-categories crawl)
    current_category: str | None = None
    """Current category being crawled."""

    category_index: int = 0
    """Current category index (1-indexed)."""

    total_categories: int = 0
    """Total number of categories to crawl."""

    category_fetched: int = 0
    """Jobs fetched in current category."""

    category_total: int = 0
    """Total jobs in current category."""

    @property
    def speed(self) -> float:
        """Jobs per second."""
        return self.fetched / self.elapsed if self.elapsed > 0 else 0

    @property
    def eta_seconds(self) -> float:
        """Estimated seconds remaining."""
        if self.speed <= 0:
            return 0
        return (self.total_jobs - self.fetched) / self.speed

    @property
    def percent_complete(self) -> float:
        """Percentage complete."""
        if self.total_jobs <= 0:
            return 0
        return (self.fetched / self.total_jobs) * 100


type ProgressCallback = Callable[[CrawlProgress], None]


@dataclass
class Crawler:
    """Lists job UUIDs from MyCareersFuture for incremental crawling."""

    rate_limit: float = 5.0
    """API requests per second."""

    def list_job_uuids_all_categories(
        self,
        *,
        categories: list[str] | None = None,
        limit: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[str]:
        """List job UUIDs without fetching job detail.

        This is the key primitive for incremental crawling: we can diff UUID sets
        against a database to decide which jobs need `get_job_detail()`.
        """
        fetched_count = 0
        start_time = time.monotonic()
        uuids: list[str] = []
        seen: set[str] = set()

        try:
            client = MCFClient(rate_limit=self.rate_limit)

            # If categories are provided, list within them; else list across all categories
            cats = categories if categories is not None else CATEGORIES

            # Estimate total (sum of per-category totals) for progress/ETA.
            category_counts: list[tuple[str, int]] = []
            for cat in cats:
                resp = client.search_jobs(limit=1, categories=[cat])
                category_counts.append((cat, resp.total))
            estimated_total = sum(c for _, c in category_counts)
            if limit:
                estimated_total = min(estimated_total, limit)

            total_categories = len(category_counts)
            for cat_idx, (category, cat_total) in enumerate(category_counts, 1):
                if cat_total == 0:
                    continue
                page = 0
                page_size = 100
                cat_fetched = 0
                while True:
                    resp = client.search_jobs(
                        page=page,
                        limit=page_size,
                        categories=[category],
                        sort_by_date=True,
                    )
                    if not resp.results:
                        break
                    for job in resp.results:
                        if job.uuid in seen:
                            continue
                        seen.add(job.uuid)
                        uuids.append(job.uuid)
                        fetched_count += 1
                        cat_fetched += 1

                        if on_progress:
                            elapsed = time.monotonic() - start_time
                            on_progress(
                                CrawlProgress(
                                    total_jobs=estimated_total,
                                    fetched=fetched_count,
                                    elapsed=elapsed,
                                    current_category=category,
                                    category_index=cat_idx,
                                    total_categories=total_categories,
                                    category_fetched=cat_fetched,
                                    category_total=cat_total,
                                )
                            )
                        if limit and fetched_count >= limit:
                            break
                    if limit and fetched_count >= limit:
                        break
                    if (page + 1) * page_size >= resp.total:
                        break
                    if (page + 1) * page_size >= 10000:
                        break
                    page += 1
                if limit and fetched_count >= limit:
                    break
            client.close()
            return uuids
        except KeyboardInterrupt:
            return uuids

