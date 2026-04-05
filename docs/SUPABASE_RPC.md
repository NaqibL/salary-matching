# Supabase RPC Functions

PostgreSQL functions for expensive queries, callable via `supabase.rpc()`. Use when your database is Supabase Postgres.

## Migration

```bash
psql $DATABASE_URL -f scripts/migrations/006_rpc_dashboard_and_matching.sql
```

## Functions

### `get_dashboard_summary()`

Returns dashboard stats. **Cached 5 minutes** in `rpc_result_cache`. Invalidated on crawl completion (via `refresh_dashboard_materialized_views`).

**Returns:** `{ total_jobs, active_jobs, inactive_jobs, by_source, jobs_with_embeddings, jobs_needing_backfill }`

### `get_active_jobs_for_matching(p_user_id, p_limit)`

Returns job UUIDs for the matching pool, excluding jobs the user has interacted with. No DB cache (user-specific).

**Params:**
- `p_user_id` (text) — Supabase auth user ID
- `p_limit` (int, default 5000) — max job UUIDs to return

**Returns:** `{ job_uuid: string }[]`

### `invalidate_rpc_cache(p_key?)`

Invalidate RPC cache. `p_key = null` clears expired entries; `p_key = 'dashboard_summary'` clears that cache.

---

## Calling from Next.js

### Dashboard summary (with cache headers)

```ts
// Option A: Direct Supabase RPC (bypasses FastAPI)
import { supabase } from '@/lib/supabase'

export async function getDashboardSummary() {
  const { data, error } = await supabase.rpc('get_dashboard_summary')
  if (error) throw error
  return data
}
```

**Next.js route with Cache-Control:**

```ts
// app/api/dashboard/summary-rpc/route.ts
import { NextResponse } from 'next/server'
import { supabase } from '@/lib/supabase'

const CACHE_SECONDS = 300 // 5 min, matches DB cache TTL

export async function GET() {
  const { data, error } = await supabase.rpc('get_dashboard_summary')
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 502 })
  }
  return NextResponse.json(data, {
    headers: {
      'Cache-Control': `public, s-maxage=${CACHE_SECONDS}, stale-while-revalidate`,
    },
  })
}
```

### Active jobs for matching

```ts
import { supabase } from '@/lib/supabase'

export async function getActiveJobsForMatching(userId: string, limit = 5000) {
  const { data, error } = await supabase.rpc('get_active_jobs_for_matching', {
    p_user_id: userId,
    p_limit: limit,
  })
  if (error) throw error
  return (data ?? []).map((r: { job_uuid: string }) => r.job_uuid)
}
```

**With SWR (client-side cache):**

```ts
import useSWR from 'swr'
import { supabase } from '@/lib/supabase'

function useActiveJobsForMatching(userId: string | null) {
  return useSWR(
    userId ? ['active-jobs-matching', userId] : null,
    async () => {
      const { data } = await supabase.rpc('get_active_jobs_for_matching', {
        p_user_id: userId!,
        p_limit: 5000,
      })
      return (data ?? []).map((r: { job_uuid: string }) => r.job_uuid)
    },
    { revalidateOnFocus: false, dedupingInterval: 60000 } // 1 min dedupe
  )
}
```

---

## Next.js routes

| Route | RPC | Cache |
|-------|-----|-------|
| `/api/dashboard/summary` | — | 1h (via FastAPI) |
| `/api/dashboard/summary-rpc` | `get_dashboard_summary` | 5 min `s-maxage`, `stale-while-revalidate` |

To use RPC for dashboard summary, switch `dashboardApi.getSummary()` to fetch `/api/dashboard/summary-rpc` instead of `/api/dashboard/summary`.

## When to use

| Use case | FastAPI route | Supabase RPC |
|----------|---------------|--------------|
| Dashboard summary | `/api/dashboard/summary-public` | `get_dashboard_summary()` |
| Active jobs for matching | N/A (matches flow uses FastAPI) | `get_active_jobs_for_matching()` |

Use Supabase RPC when:
- Database is Supabase Postgres
- You want to reduce load on the FastAPI backend
- You need PostgREST cache headers (set in Next.js route)
