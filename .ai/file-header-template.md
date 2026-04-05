# File Header Templates

Templates for documenting new files added to this codebase.

---

## Python Module (Backend)

Use for any new `.py` file in `src/mcf/`:

```python
"""
Brief one-sentence description of what this module does.

Longer description if needed — explain the core concept, algorithm,
or design decision. Keep to 2-3 sentences max.

Dependencies:
    - mcf.lib.storage.base: Storage interface for DB access
    - sentence_transformers: BGE embedding model

Exports:
    - MyClass: Main class description
    - my_function: What it does
"""
```

### Example — Service Module
```python
"""
Semantic job matching service using cosine similarity and Rocchio query expansion.

Computes similarity between a user's query embedding (resume or taste profile)
and all active job embeddings. Applies recency decay and filters interacted jobs.

Dependencies:
    - mcf.api.active_jobs_pool_cache: Pre-loaded job embeddings
    - mcf.lib.storage.base: Storage interface
    - numpy: Vector math

Exports:
    - MatchingService: Main service class
    - get_matches: Convenience function for route handlers
"""
```

### Example — Storage Implementation
```python
"""
DuckDB implementation of the Storage abstract base class.

All schema creation, migrations, and queries for local development
and testing. Production uses PostgresStore with the same interface.

Dependencies:
    - duckdb: Local columnar database
    - mcf.lib.storage.base: Storage interface

Exports:
    - DuckDBStore: Storage implementation backed by DuckDB
"""
```

### Example — Pydantic Models
```python
"""
Pydantic models mirroring the MyCareersFuture REST API response schema.

These models are used both for deserializing API responses and for
FastAPI response serialization. Extra fields are allowed to handle
upstream schema additions gracefully.

Exports:
    - Job: Top-level job listing model
    - Skill: Skill tag model
    - Salary: Min/max salary range
    - Company: Employer info
"""
```

---

## TypeScript/React Component

Use for new `.tsx` files in `frontend/app/components/`:

```typescript
/**
 * ComponentName — Brief one-sentence description.
 *
 * Longer note if the component has non-obvious behavior, e.g.:
 * "Uses React.memo with UUID equality to avoid re-renders during list updates."
 *
 * @dependencies
 *   - @/lib/api: profileApi.getMatches for data fetching
 *   - @/lib/types: Match interface
 *   - @/components/ui/card: Card primitive
 *
 * @exports
 *   - JobCard (named): Main card component
 */
```

### Example — Data-Fetching Component
```typescript
/**
 * ResumeTab — Resume upload form with match results list.
 *
 * Handles file upload to /api/profile/upload-resume, then fetches
 * semantic matches via SWR. Renders a scrollable list of JobCards.
 *
 * @dependencies
 *   - @/lib/api: profileApi.uploadResume, profileApi.getMatches
 *   - @/lib/types: Match
 *   - JobCard: Result card component
 *
 * @exports
 *   - ResumeTab (default): Main tab component
 */
```

### Example — Context Provider
```typescript
/**
 * RatingsQueueProvider — Batches and debounces job rating API calls.
 *
 * Queues rating updates from TasteTab and flushes them after 800ms
 * of inactivity to reduce API calls during rapid swiping.
 *
 * @dependencies
 *   - @/lib/api: profileApi.rateJob
 *   - @/lib/useDebouncedRatings: Debounce hook
 *
 * @exports
 *   - RatingsQueueProvider (default): Context provider
 *   - useRatingsQueue: Hook to enqueue a rating
 */
```

---

## TypeScript Utility / Hook

Use for new `.ts` files in `frontend/lib/`:

```typescript
/**
 * @module myUtil
 * @description Brief one-sentence description.
 *
 * @dependencies
 *   - Listed if non-obvious
 *
 * @exports
 *   - myFunction: What it does and returns
 *   - MyType: Type description
 */
```

### Example — Custom Hook
```typescript
/**
 * @module useDebouncedRatings
 * @description Debounces job rating updates to batch API calls.
 *
 * Accumulates ratings in a local queue and flushes after 800ms
 * of inactivity. Prevents excessive calls during fast swiping.
 *
 * @exports
 *   - useDebouncedRatings(onFlush): Returns { enqueue } function
 */
```

### Example — API Client Namespace
```typescript
/**
 * @module api
 * @description Axios API client with JWT auto-injection and all endpoint functions.
 *
 * The base `api` Axios instance injects the Supabase access token
 * from the current session on every request.
 *
 * @exports
 *   - api: Base Axios instance (use sparingly — prefer domain namespaces)
 *   - jobsApi: Job detail and interaction endpoints
 *   - profileApi: Resume upload, match fetching, rating
 *   - dashboardApi: Public analytics endpoints
 *   - adminApi: Cache management (admin only)
 */
```

---

## Next.js API Route

Use for new `route.ts` files in `frontend/app/api/`:

```typescript
/**
 * @route POST /api/my-endpoint
 * @description Brief description of what this proxy does.
 *
 * Proxies to FastAPI /api/my-endpoint. Forwards Authorization header.
 * Returns 401 if no token present.
 *
 * @auth Required (Bearer JWT)
 * @body { field: string }
 * @returns { result: string }
 */
```

---

## Python CLI Command

Use when adding new Typer commands to `cli.py`:

```python
@app.command("my-command")
def my_command(
    option: Annotated[str, typer.Option(help="What this option does")] = "default",
) -> None:
    """
    One-line summary shown in `mcf --help`.

    Longer explanation of what this command does, when to use it,
    and any important side effects (e.g. writes to DB, calls external API).
    """
```

---

## When to Skip the Header

- **Short utility files** (< 30 lines, obvious purpose): skip the docstring
- **`__init__.py`**: skip unless it exports something non-obvious
- **shadcn/ui component files** in `components/ui/`: skip (auto-generated)
- **`page.tsx` files** with just a layout: skip unless the page has non-obvious data fetching

The goal is to help future readers (human or AI) quickly understand a file's role without reading the implementation.
