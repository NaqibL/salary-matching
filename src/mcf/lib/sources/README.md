# Job Sources (`src/mcf/lib/sources/`)

## Purpose

Adapters that fetch job listings from external platforms and normalize them into a common `NormalizedJob` format. Each source implements the `JobSource` protocol. The pipeline layer (`incremental_crawl.py`) is source-agnostic and works with any `JobSource`.

## Key Files

| File | Purpose |
|---|---|
| `base.py` | `JobSource` protocol + `NormalizedJob` frozen dataclass |
| `mcf_source.py` | MyCareersFuture REST API source |
| `cag_source.py` | Careers@Gov via Algolia search API |

## Dependencies

| Package | Use |
|---|---|
| `httpx` | Async HTTP client for MCF REST API |
| `requests` | Sync HTTP for Algolia (CAG) |
| `tenacity` | Retry logic for flaky external APIs |
| `lxml` / `beautifulsoup4` | Cleaning HTML in job descriptions |

## Internal Dependencies

- `mcf.lib.api.client` — `MCFClient` and Algolia client used by source implementations
- `mcf.lib.models` — MCF API Pydantic models (deserialized before normalization)

## NormalizedJob Schema

```python
@dataclass(frozen=True)
class NormalizedJob:
    source_id: str         # "mcf" or "cag"
    external_id: str       # UUID from the source
    title: str | None
    company_name: str | None
    description_html: str | None
    description_text: str | None
    salary_min: int | None  # Monthly SGD
    salary_max: int | None
    skills: list[str]
    posted_at: datetime | None
    expires_at: datetime | None
    url: str | None
    # ... additional optional fields
```

## Source: MCF (MyCareersFuture)

- REST API: `https://api.mycareersfuture.gov.sg/search`
- Rate limit: configurable, default 4 req/s
- Auth: none (public API)
- `list_job_ids()`: paginates search results filtered by category
- `get_job_detail(uuid)`: fetches full job detail

## Source: CAG (Careers@Gov)

- Algolia index with public read-only credentials (hardcoded in `cag_source.py` — these are extracted from the public gov website's own frontend)
- `list_job_ids()`: Algolia search across all gov positions
- `get_job_detail(job_id)`: additional Algolia detail query

## Common Modifications

- **Add new source**: See [Adding a New Job Source](../../../.ai/common-tasks.md#adding-a-new-job-source)
- **Add fields to NormalizedJob**: Edit `base.py` dataclass, update both source adapters and `duckdb_store.py`/`postgres_store.py` schema
