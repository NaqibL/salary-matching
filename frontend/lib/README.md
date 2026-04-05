# Frontend Library (`frontend/lib/`)

## Purpose

Non-React utilities, type definitions, the central API client, and custom hooks that are shared across the entire frontend. Everything in this directory is importable from anywhere via the `@/lib/` path alias. This is the frontend equivalent of the backend's `lib/` package — pure logic with no UI.

## Key Files

| File | Purpose |
|---|---|
| `api.ts` | Axios instance + all API functions grouped by domain (`jobsApi`, `profileApi`, `dashboardApi`, `adminApi`) |
| `types.ts` | All TypeScript interfaces for API data (`Job`, `Match`, `Profile`, `JobDetail`, etc.) |
| `supabase.ts` | Supabase browser client singleton |
| `swr-config.ts` | Global SWR fetcher configuration |
| `jwt-verify.ts` | Server-side JWT validation (used in Next.js API routes) |
| `server-fetch.ts` | Authenticated `fetch` wrapper for server-side calls from API routes |
| `profile-cache.ts` | SWR cache key + `mutateProfile` helper |
| `job-prefetch.ts` | `prefetchJobDetail(uuid)` — called on `JobCard` hover |
| `useDebouncedRatings.ts` | Hook: accumulates ratings and flushes after 800ms idle |
| `utils.ts` | `cn()` helper (clsx + tailwind-merge) |

## Dependencies

| Package | Use |
|---|---|
| `axios` | HTTP client (base instance in `api.ts`) |
| `swr` | Client-side caching/revalidation |
| `@supabase/supabase-js` | Auth client |
| `jose` | JWT verification (server-side, in API routes) |
| `clsx` + `tailwind-merge` | `cn()` utility |

## Internal Dependencies

None — this directory is the bottom of the frontend dependency graph. Components and pages import from here, not the reverse.

## API Client Design

`api.ts` exports a single Axios instance plus domain-grouped functions:

```typescript
// Auto-injects Supabase JWT on every request
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  if (data.session?.access_token) {
    config.headers['Authorization'] = `Bearer ${data.session.access_token}`
  }
  return config
})

// Usage in components:
const matches = await profileApi.getMatches()
const job = await jobsApi.getJobDetail(uuid)
```

Never add raw `axios.get(...)` calls in components — always add a named function to the appropriate namespace in `api.ts`.

## Type Definitions

`types.ts` is the single source of truth for all shared TypeScript types. Key interfaces:

| Type | Description |
|---|---|
| `Job` | Base job listing (uuid, title, company, salary) |
| `Match` | `Job` + similarity score + matched skills |
| `JobDetail` | Full job detail including description, requirements |
| `Profile` | User profile (has_resume, resume_embedding_status, ratings count) |
| `InteractionType` | `'viewed' \| 'dismissed' \| 'applied' \| 'saved' \| 'interested' \| 'not_interested'` |
| `LowballResult` | Salary check result with percentile and verdict |
| `DashboardSummary` | Aggregate stats for dashboard page |

## State Management

This directory provides the primitives for state management but doesn't hold state itself:
- `profile-cache.ts` exposes the SWR cache key so multiple components can share profile data
- `swr-config.ts` configures global SWR behaviour (deduping interval, error retry)

## Common Modifications

- **Add API function**: Add to relevant namespace object in `api.ts`
- **Add type**: Add interface/type to `types.ts`
- **Add utility**: Add to `utils.ts` (pure function) or create new `use*.ts` hook file
