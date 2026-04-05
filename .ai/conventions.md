# Conventions

Coding standards and patterns observed throughout this codebase.

---

## File Naming

### Python Backend
| File Type | Convention | Example |
|---|---|---|
| Module | `snake_case.py` | `matching_service.py` |
| Abstract base | `base.py` (per package) | `src/mcf/lib/storage/base.py` |
| Implementation | `{technology}_store.py` | `duckdb_store.py`, `postgres_store.py` |
| Source adapters | `{name}_source.py` | `mcf_source.py`, `cag_source.py` |
| CLI | `cli.py` | `src/mcf/cli/cli.py` |
| Config | `config.py` | `src/mcf/api/config.py` |
| Tests | `test_{feature}.py` | `tests/test_smoke.py` |

### Frontend (TypeScript/React)
| File Type | Convention | Example |
|---|---|---|
| Page | `page.tsx` (App Router) | `app/matches/page.tsx` |
| Layout | `layout.tsx` | `app/layout.tsx` |
| Component | `PascalCase.tsx` | `JobCard.tsx`, `ResumeTab.tsx` |
| API route | `route.ts` | `app/api/matches/route.ts` |
| Hook | `use{Name}.ts` | `useDebouncedRatings.ts` |
| Utility | `camelCase.ts` | `job-prefetch.ts`, `utils.ts` |
| Types | `types.ts` (centralised) | `frontend/lib/types.ts` |

---

## Directory Organization

### Python
```
src/mcf/
├── api/           # FastAPI routes, middleware, caches, auth
│   └── services/  # Business logic called by routes
├── cli/           # Typer commands
└── lib/           # Reusable library modules
    ├── api/       # External API clients
    ├── crawler/   # Job UUID listing
    ├── embeddings/# BGE wrapper, resume/job text extraction
    ├── models/    # Pydantic API response models
    ├── pipeline/  # Crawl orchestration
    ├── sources/   # Job source adapters
    └── storage/   # DB abstraction + implementations
```

**Rule:** Route handlers live in `api/server.py`. Business logic belongs in `api/services/`. Raw data access belongs in `lib/storage/`.

### Frontend
```
frontend/
├── app/
│   ├── {page}/page.tsx       # One directory per route
│   ├── api/{endpoint}/route.ts # Next.js API routes (proxy/BFF)
│   └── components/           # Shared components used across pages
├── lib/                      # Non-React utilities, API client, types
└── components/ui/            # shadcn/ui primitives (don't edit directly)
```

**Rule:** Page-specific components go in `app/components/`. shadcn/ui primitives live in `components/ui/` and should not be modified — extend them via wrapper components instead.

---

## Code Patterns

### Python — FastAPI Route Handlers
```python
@app.get("/api/resource/{id}")
async def get_resource(
    id: str,
    store: Storage = Depends(get_store),
    user: dict = Depends(get_current_user),  # optional for protected routes
) -> ResponseModel:
    result = store.get_thing(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Not found")
    return result
```

### Python — Storage Abstraction
All DB access goes through the `Storage` interface. Never import `DuckDBStore` or `PostgresStore` directly in route handlers — always use `Depends(get_store)`.

```python
store: Storage = Depends(get_store)
jobs = store.get_active_jobs(limit=50)
```

### Python — Pydantic Models
- Use `BaseModel` for API request/response shapes
- Use `ConfigDict(extra="allow")` on MCF API models (upstream schema can add fields)
- Use `BaseSettings` in `config.py` for environment-backed config
- Use `dataclass(frozen=True)` for internal value objects (e.g. `NormalizedJob`)

```python
class Job(BaseModel):
    uuid: str
    title: str
    salary: Salary | None = None
    model_config = ConfigDict(extra="allow")
```

### Python — Protocol Pattern
Use `Protocol` classes (not ABC) for external-facing interfaces:
```python
class JobSource(Protocol):
    def list_job_ids(self, ...) -> list[str]: ...
    def get_job_detail(self, job_uuid: str) -> NormalizedJob: ...
```

Abstract base classes (ABC) are used for internal interfaces (e.g. `Storage`).

### Python — Async vs Sync
- FastAPI route handlers are `async def`
- I/O-heavy operations (DB queries, HTTP calls) are awaited or use `run_in_executor`
- CPU-bound operations (embedding computation) are sync — called from routes as-is (BGE inference is fast enough at current scale)
- CLI commands are sync (Typer doesn't support async natively)

### Python — Error Handling
```python
# HTTP errors in routes
raise HTTPException(status_code=404, detail="Job not found")
raise HTTPException(status_code=401, detail="Not authenticated")

# Retry for external API calls
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def fetch_job_detail(self, uuid: str) -> JobDetail: ...
```

### Python — Lifespan Pattern
Global singletons (store, embedder, caches) are initialised in the FastAPI lifespan context manager:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _embedder
    _store = _make_store()
    _embedder = Embedder(settings)
    yield
    if _store: _store.close()

app = FastAPI(lifespan=lifespan)
```

### Frontend — Data Fetching with SWR
```typescript
const { data, isLoading, error, mutate } = useSWR(
  isAuthed ? '/api/matches' : null,  // null = suspend fetch
  profileApi.getMatches,
  { revalidateOnFocus: false }
)
```

### Frontend — API Client Pattern
All API calls go through `frontend/lib/api.ts`. The Axios instance auto-injects the Supabase JWT:
```typescript
// lib/api.ts — add to appropriate namespace object
export const profileApi = {
  uploadResume: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.post('/api/profile/upload-resume', form)
    return data
  },
}
```

Never call `fetch()` or `axios` directly from components — always use functions from `api.ts`.

### Frontend — State Management
- **Server state** (jobs, profile, dashboard): SWR
- **UI state** (modals, form inputs, loading flags): `useState`
- **Shared auth/profile state**: React Context (`ProfileProvider`, `AuthGate`)
- **Rating batching**: Custom provider (`RatingsQueueProvider`)
- No global state library (Redux, Zustand) — not needed at current scale

### Frontend — Component Structure
```typescript
// 1. Types at top
interface ComponentProps {
  value: string
  onChange?: (v: string) => void
}

// 2. Default export — named function (for React DevTools)
export default function ComponentName({ value, onChange }: ComponentProps) {
  // 3. Hooks
  const [localState, setLocalState] = useState(false)

  // 4. Derived values / memoized
  const processed = useMemo(() => transform(value), [value])

  // 5. Handlers
  const handleClick = useCallback(() => { ... }, [deps])

  // 6. JSX
  return <div className="...">...</div>
}
```

### Frontend — Performance Patterns
- Heavy components are lazy-loaded with `dynamic()` + `ssr: false`
- Lists use `React.memo` with custom equality (compare by UUID, not full object)
- Job detail pages use `prefetchJobDetail()` on hover (in `JobCard`)
- Dashboard page uses ISR (`revalidate: 3600`) — not client-fetched

---

## Import Conventions

### Python
Order: stdlib → third-party → local. One blank line between groups.
```python
import logging
from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel

from mcf.api.config import settings
from mcf.lib.storage.base import Storage
```

Always use **absolute imports** from the `mcf` package root. Never use relative imports (`from ..lib.storage import ...`).

### TypeScript/React
Order: React → Next.js → third-party → internal (`@/lib/*`, `@/app/components/*`). Type imports are separate.
```typescript
import { useState, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import useSWR from 'swr'

import { profileApi } from '@/lib/api'
import type { Match } from '@/lib/types'
import { cn } from '@/lib/utils'
import { JobCard } from '@/app/components/JobCard'
```

Use **path alias** `@/` for everything under `frontend/`. All paths in `tsconfig.json` map `@/*` to `./frontend/*`.

---

## Type Definitions

### Python
- **API models**: `src/mcf/lib/models/models.py` and `job_detail.py`
- **Internal value objects**: `@dataclass(frozen=True)` in the relevant module
- **Interfaces/protocols**: `base.py` in each package
- **Settings**: `src/mcf/api/config.py`
- Naming: `PascalCase` for classes, `UPPER_SNAKE` for enums, `snake_case` for aliases

### TypeScript
- **All shared types**: `frontend/lib/types.ts` (single source of truth)
- **Component prop types**: Defined inline (`interface Props { ... }`) at top of component file
- **API response shapes**: Mirror backend Pydantic models (manually kept in sync)
- Naming: `PascalCase` for interfaces/types, `camelCase` for type aliases of primitives

---

## Testing Conventions

- **Framework**: pytest
- **Location**: `tests/` at project root
- **Style**: Smoke tests only (no unit tests, no mocks)
- **DB**: Real DuckDB instance (no mocking)
- **Scope**: Session-scoped `TestClient` fixture so lifespan runs once
- **What gets tested**:
  - Public routes return 200 and expected shape
  - Protected routes return `< 500` (not necessarily 200)
  - Health endpoint
- **How to run**: `uv run pytest tests/ -v`

There are no frontend tests currently.

---

## Configuration Management

- Backend config lives in `src/mcf/api/config.py` as a Pydantic `Settings` class
- Values come from `.env` (local) or environment variables (production) — same precedence
- **Feature flags** are env vars with `int` type (`0` = off, `1` = on), e.g. `ENABLE_MATCHES_CACHE`
- Frontend env vars use `NEXT_PUBLIC_` prefix for client-accessible vars
- Secrets (JWT, DB URL) are **never** hardcoded — always from env
- Exception: Careers@Gov Algolia public API key is hardcoded in `cag_source.py` (it's a public read-only key extracted from the gov website's own client-side code)

---

## Styling Approach

- **Tailwind CSS** utility classes everywhere — no CSS modules or styled-components
- **Dark mode**: Via `class` strategy (`dark:` prefix); toggled by `next-themes`
- **Color tokens**: CSS variables defined in `globals.css` (e.g. `--background`, `--card`, `--primary`)
- **Variants**: `class-variance-authority` (cva) for multi-variant components
- **Merging**: `cn()` helper (clsx + tailwind-merge) for conditional/merged classNames
- **shadcn/ui** components are the base primitives — don't edit `components/ui/` files; wrap them instead
- **Custom animations**: Defined in `tailwind.config.js` (`fadeIn`, `borderPulse`)
- **Responsive**: Mobile-first, `sm:` / `md:` / `lg:` breakpoints
- **Icons**: Lucide React inline (`<Building2 size={14} />`)
- **Charts**: Recharts with custom Tailwind-matching color palette
