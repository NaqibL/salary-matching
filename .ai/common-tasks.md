# Common Tasks

Step-by-step guides for the most frequent modifications to this codebase.

---

## Adding a New FastAPI Endpoint

**Description:** Add a new REST endpoint to the backend API.

1. **Define request/response models** (if needed) in `src/mcf/lib/models/models.py`:
   ```python
   class MyRequest(BaseModel):
       field: str

   class MyResponse(BaseModel):
       result: str
   ```

2. **Add business logic** to a matching or lib module (or inline in the route if trivial):
   ```python
   # src/mcf/matching/my_algorithm.py  (if algorithm-related)
   # src/mcf/lib/my_util.py            (if general utility)
   def do_thing(store: Storage, user_id: str, field: str) -> str:
       data = store.get_something(user_id)
       return process(data, field)
   ```

3. **Add the route** to the relevant file in `src/mcf/api/routes/` (or create a new route file and register it in `server.py` with `app.include_router()`):
   ```python
   @app.post("/api/my-endpoint")
   async def my_endpoint(
       body: MyRequest,
       store: Storage = Depends(get_store),
       user: dict = Depends(get_current_user),  # remove if public
   ) -> MyResponse:
       result = do_thing(store, user["sub"], body.field)
       return MyResponse(result=result)
   ```

4. **Add a corresponding Next.js API route** (proxy) in `frontend/app/api/my-endpoint/route.ts`:
   ```typescript
   import { NextRequest, NextResponse } from 'next/server'
   import { serverFetch } from '@/lib/server-fetch'

   export async function POST(request: NextRequest) {
     const body = await request.json()
     const token = request.headers.get('authorization')
     const data = await serverFetch('/api/my-endpoint', {
       method: 'POST',
       body: JSON.stringify(body),
       token,
     })
     return NextResponse.json(data)
   }
   ```

5. **Add a function** to the appropriate namespace in `frontend/lib/api.ts`:
   ```typescript
   export const myApi = {
     doThing: async (field: string) => {
       const { data } = await api.post('/api/my-endpoint', { field })
       return data as MyResponse
     },
   }
   ```

6. **Add a smoke test** in `tests/test_smoke.py`:
   ```python
   def test_my_endpoint_requires_auth(client):
       r = client.post("/api/my-endpoint", json={"field": "test"})
       assert r.status_code < 500
   ```

**Related files:** `server.py`, `models.py`, `frontend/lib/api.ts`, `frontend/lib/types.ts`

---

## Adding a New Frontend Page

**Description:** Add a new route/page to the Next.js frontend.

1. **Create the directory and page file**:
   ```
   frontend/app/my-page/page.tsx
   ```

2. **Scaffold the page component**:
   ```typescript
   // frontend/app/my-page/page.tsx
   import { Metadata } from 'next'

   export const metadata: Metadata = {
     title: 'My Page | MCF Matcher',
     description: 'Description for SEO',
   }

   export default function MyPage() {
     return (
       <div className="container mx-auto px-4 py-8">
         <h1 className="text-2xl font-bold">My Page</h1>
       </div>
     )
   }
   ```

3. **If the page needs client-side interactivity**, add `'use client'` at the top or extract interactive parts into a separate `'use client'` component.

4. **Add the route to the sidebar nav** in `frontend/app/components/layout/Sidebar.tsx` (or `Nav.tsx` for top nav links):
   ```typescript
   { href: '/my-page', label: 'My Page', icon: SomeIcon }
   ```

5. **If the page fetches data**, use SWR:
   ```typescript
   'use client'
   import useSWR from 'swr'
   import { myApi } from '@/lib/api'

   const { data, isLoading } = useSWR('/api/my-endpoint', myApi.doThing)
   ```

6. **If the page should be statically generated** with ISR:
   ```typescript
   // At top of page.tsx (server component)
   export const revalidate = 3600 // seconds
   ```

**Related files:** `frontend/app/components/layout/Sidebar.tsx`, `frontend/app/components/Nav.tsx`

---

## Adding a New React Component

**Description:** Add a shared component used across multiple pages.

1. **Create the file** in `frontend/app/components/MyComponent.tsx`

2. **Follow the standard structure**:
   ```typescript
   // Types first
   interface MyComponentProps {
     value: string
     onAction?: () => void
   }

   // Named export (not default) for shared components
   export function MyComponent({ value, onAction }: MyComponentProps) {
     const [state, setState] = useState(false)

     const handleClick = useCallback(() => {
       onAction?.()
     }, [onAction])

     return (
       <div className={cn('rounded-xl border bg-white dark:bg-slate-800', 'p-4')}>
         {value}
       </div>
     )
   }
   ```

3. **If the component is expensive to render**, wrap with `React.memo`:
   ```typescript
   export const MyComponent = React.memo(function MyComponent(props: MyComponentProps) {
     // ...
   })
   ```

4. **Add type** to `frontend/lib/types.ts` if the component introduces a new shared data shape.

5. **If the component needs shadcn/ui primitives**, import from `@/components/ui/`:
   ```typescript
   import { Button } from '@/components/ui/button'
   import { Card, CardContent } from '@/components/ui/card'
   ```

**Related files:** `frontend/lib/types.ts`, `frontend/lib/utils.ts`, `frontend/components/ui/`

---

## Adding a New Storage Method

**Description:** Add a new database operation available to both DuckDB and Postgres.

1. **Add the abstract method** to `src/mcf/lib/storage/base.py`:
   ```python
   @abstractmethod
   def get_my_data(self, user_id: str, limit: int = 20) -> list[dict]:
       """Returns my data for user."""
       ...
   ```

2. **Implement in DuckDB** (`src/mcf/lib/storage/duckdb_store.py`):
   ```python
   def get_my_data(self, user_id: str, limit: int = 20) -> list[dict]:
       with self._conn.cursor() as cur:
           cur.execute(
               "SELECT * FROM my_table WHERE user_id = ? LIMIT ?",
               [user_id, limit]
           )
           rows = cur.fetchall()
           cols = [d[0] for d in cur.description]
           return [dict(zip(cols, row)) for row in rows]
   ```

3. **Implement in Postgres** (`src/mcf/lib/storage/postgres_store.py`) with the identical signature and semantics.

4. **If a new table is needed**, add the `CREATE TABLE IF NOT EXISTS` statement to the schema setup methods in both store files.

**Note:** Both implementations must behave identically — the same tests run against both.

---

## Adding a New Job Source

**Description:** Add a new job data provider (e.g., LinkedIn, Indeed).

1. **Create source file** `src/mcf/lib/sources/my_source.py`:
   ```python
   from mcf.lib.sources.base import JobSource, NormalizedJob

   class MyJobSource:
       def list_job_ids(self, limit: int | None = None) -> list[str]:
           # Fetch list of job IDs from the new source
           ...

       def get_job_detail(self, job_id: str) -> NormalizedJob:
           # Fetch and normalize a single job
           return NormalizedJob(
               source_id="my_source",
               external_id=job_id,
               title="...",
               # ... other fields
           )
   ```

2. **Register in the pipeline** (`src/mcf/lib/pipeline/incremental_crawl.py`):
   ```python
   elif source == "my_source":
       job_source = MyJobSource(...)
   ```

3. **Add CLI option** in `src/mcf/cli/cli.py` — update the `--source` option choices.

4. **Handle in `NormalizedJob`** — check `src/mcf/lib/sources/base.py` to see if any new fields are needed.

**Related files:** `src/mcf/lib/sources/base.py`, `incremental_crawl.py`, `cli.py`

---

## Adding a New Embedding Use Case

**Description:** Embed a new type of content (e.g., company descriptions, user notes).

1. **Add text extraction function** in `src/mcf/lib/embeddings/` (new file or extend existing):
   ```python
   def extract_company_text(company: dict) -> str:
       return f"{company['name']}. {company.get('description', '')}"
   ```

2. **Use the existing `Embedder`** — it handles caching automatically:
   ```python
   embedder: Embedder = Depends(get_embedder)
   text = extract_company_text(company_data)
   embedding = embedder.embed_query(text)  # Returns np.ndarray
   ```

3. **Store the embedding** — add column/table in both DuckDB and Postgres stores.

4. **Use in matching** — pass the embedding to `MatchingService` or compute similarity directly with NumPy:
   ```python
   similarity = float(np.dot(embedding_a, embedding_b))  # Both must be L2-normalised
   ```

**Note:** BGE embeddings are L2-normalised by default. Dot product == cosine similarity.

---

## Adding Authentication to an Endpoint

**Description:** Protect a currently public FastAPI endpoint.

1. **Import the auth dependency**:
   ```python
   from mcf.api.auth import get_current_user
   ```

2. **Add to the route signature**:
   ```python
   @app.get("/api/protected-thing")
   async def protected_thing(
       store: Storage = Depends(get_store),
       user: dict = Depends(get_current_user),  # raises 401 if no valid JWT
   ) -> MyResponse:
       user_id = user["sub"]  # Supabase user UUID
       ...
   ```

3. **Update the Next.js proxy route** to forward the Authorization header:
   ```typescript
   const token = request.headers.get('authorization')
   const data = await serverFetch('/api/protected-thing', { token })
   ```

4. **Update the frontend API call** — the Axios interceptor already injects the token automatically, so no change needed in `api.ts` for most cases.

**Related files:** `src/mcf/api/auth.py`, `frontend/lib/server-fetch.ts`

---

## Adding a New Configuration Option

**Description:** Add a new env-var-backed config setting.

1. **Add to Settings** in `src/mcf/api/config.py`:
   ```python
   class Settings(BaseSettings):
       # ... existing fields ...
       my_feature_flag: int = 0          # 0 = off, 1 = on
       my_api_key: str | None = None     # Optional secret
   ```

2. **Add to `.env.example`**:
   ```
   MY_FEATURE_FLAG=0
   MY_API_KEY=
   ```

3. **Use via `settings`** anywhere:
   ```python
   from mcf.api.config import settings

   if settings.my_feature_flag:
       enable_feature()
   ```

4. **For frontend env vars**, add to `frontend/.env.local` (dev) and Vercel dashboard (prod):
   ```
   NEXT_PUBLIC_MY_FEATURE=true
   ```
   Then access as `process.env.NEXT_PUBLIC_MY_FEATURE`.

**Note:** Server-only secrets must NOT use `NEXT_PUBLIC_` prefix.

---

## Adding a New Test

**Description:** Add a smoke test for a new endpoint.

1. **Open** `tests/test_smoke.py`

2. **Add test function** — use the session-scoped `client` fixture:
   ```python
   def test_my_endpoint_public(client):
       """Public endpoint must return 200 and expected fields."""
       r = client.get("/api/my-endpoint")
       assert r.status_code == 200
       data = r.json()
       assert "expected_field" in data

   def test_my_endpoint_requires_auth(client):
       """Protected endpoint must not 5xx without auth."""
       r = client.post("/api/my-endpoint", json={"field": "test"})
       assert r.status_code in (401, 403)
   ```

3. **Run**: `uv run pytest tests/ -v`

**Note:** No mocking. Tests hit real DuckDB. Don't add external HTTP calls in tests.

---

## Adding a New Utility Function

**Description:** Add a shared helper used across multiple modules.

- **Backend**: Add to the most relevant `lib/` module, or create `src/mcf/lib/utils.py` if truly generic
- **Frontend**: Add to `frontend/lib/utils.ts` if it's a pure function, or create a custom hook in `frontend/lib/hooks/` if it uses React state

```typescript
// frontend/lib/utils.ts
export function formatSalary(min?: number, max?: number): string {
  if (!min && !max) return 'Not specified'
  const fmt = (n: number) => `$${(n / 1000).toFixed(0)}k`
  return max ? `${fmt(min!)} – ${fmt(max)}` : `From ${fmt(min!)}`
}
```

---

## Modifying the Matching Algorithm

**Description:** Change how jobs are ranked or scored.

The matching pipeline lives in `src/mcf/matching/service.py`.

Key functions to understand:
- `MatchingService.match_candidate_to_jobs()` — resume matching entry point
- `MatchingService.match_taste_to_jobs()` — taste profile matching entry point
- `MatchingService._build_session()` — cosine similarity scoring, recency decay, tier boost
- `MatchingService._expand_query_with_interactions()` — Rocchio query expansion

To change scoring:
1. Modify `_build_session` (recency decay, tier boost) or `_expand_query_with_interactions` (Rocchio α/β/γ) in `matching/service.py`
2. Constants (`_RECENCY_DECAY_PER_DAY`, `_ROCCHIO_ALPHA`, etc.) are at the top of `matching/service.py`
3. For role/tier classification changes, see `matching/classifiers.py`
4. Run smoke tests: `uv run pytest tests/ -v`
5. Test manually: `uv run mcf match-jobs --limit 10`

**Related files:** `matching/service.py`, `matching/classifiers.py`, `api/cache/job_pool.py`, `api/config.py`

---

## Triggering a Manual Crawl

**Description:** Refresh job data without waiting for the nightly cron.

**Option A — CLI (local dev):**
```bash
uv run mcf crawl-incremental --source mcf
uv run mcf crawl-incremental --source cag
```

**Option B — Webhook (production):**
```bash
curl -X POST https://your-vercel-url/api/webhooks/crawl \
  -H "Authorization: Bearer $CRON_SECRET"
```

After crawl completes, trigger ISR revalidation:
```bash
curl -X POST https://your-vercel-url/api/revalidate \
  -H "x-revalidate-secret: $REVALIDATE_SECRET"
```

**Related files:** `src/mcf/cli/cli.py`, `frontend/app/api/webhooks/`, `frontend/app/api/revalidate/`

---

## Updating the Dashboard

**Description:** Add a new metric or chart to the public analytics dashboard.

1. **Add the aggregation query** to both `DuckDBStore` and `PostgresStore`:
   ```python
   def get_my_stat(self) -> dict:
       # SQL aggregation query
       ...
   ```

2. **Add a FastAPI endpoint** in `server.py` (public — no auth):
   ```python
   @app.get("/api/dashboard/my-stat")
   async def get_my_stat(store: Storage = Depends(get_store)) -> dict:
       return store.get_my_stat()
   ```

3. **Add Next.js proxy** in `frontend/app/api/dashboard/my-stat/route.ts`

4. **Add to dashboard page** `frontend/app/dashboard/page.tsx`:
   ```typescript
   const { data: myStat } = useSWR('/api/dashboard/my-stat', dashboardApi.getMyStat)
   // Render with Recharts or a simple stat card
   ```

5. **Consider caching** — dashboard responses are cached in `ResponseCache` (1h TTL). The cache key is the URL path, so no changes needed if the endpoint path is new.
