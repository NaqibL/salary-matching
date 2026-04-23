import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'
import { getUserIdFromToken, MATCHES_CACHE_TAG_PREFIX } from '@/lib/jwt-verify'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const MATCHES_CACHE_SECONDS = 900 // 15 minutes

/**
 * Next.js API route that proxies /api/matches to FastAPI with caching.
 * Cache key: user_id + mode + all query params.
 * Cache TTL: 15 minutes.
 * Invalidation: call POST /api/revalidate-matches after resume update or job rating.
 */
export async function GET(request: NextRequest) {
  const authorization = request.headers.get('authorization')
  const user_id = await getUserIdFromToken(authorization)

  if (!user_id) {
    return NextResponse.json(
      { detail: 'Authorization required' },
      { status: 401 }
    )
  }

  const { searchParams } = request.nextUrl
  const mode = searchParams.get('mode') || 'resume'
  const exclude_interacted = searchParams.get('exclude_interacted') ?? 'true'
  const exclude_rated_only = searchParams.get('exclude_rated_only') ?? 'true'
  const top_k = searchParams.get('top_k') || '25'
  const offset = searchParams.get('offset') || '0'
  const max_days_old = searchParams.get('max_days_old') ?? ''
  const session_id = searchParams.get('session_id') ?? ''
  const role_clusters = searchParams.getAll('role_cluster')
  const predicted_tiers = searchParams.getAll('predicted_tier')

  const params = new URLSearchParams({
    mode,
    exclude_interacted,
    exclude_rated_only,
    top_k,
    offset,
  })
  if (max_days_old) params.set('max_days_old', max_days_old)
  if (session_id) params.set('session_id', session_id)
  role_clusters.forEach((c) => params.append('role_cluster', c))
  predicted_tiers.forEach((t) => params.append('predicted_tier', t))

  const url = `${API_BASE_URL}/api/matches?${params}`
  const authHeader = authorization!

  const cacheKey = [
    'matches',
    user_id,
    mode,
    exclude_interacted,
    exclude_rated_only,
    top_k,
    offset,
    max_days_old,
    session_id,
    role_clusters.join(','),
    predicted_tiers.join(','),
  ]

  try {
    const fetchMatches = async () => {
      const res = await fetch(url, {
        headers: { Authorization: authHeader, 'Content-Type': 'application/json' },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Backend error: ${res.status}`)
      }
      return res.json()
    }

    const data = await unstable_cache(
      fetchMatches,
      cacheKey,
      {
        revalidate: MATCHES_CACHE_SECONDS,
        tags: [`${MATCHES_CACHE_TAG_PREFIX}${user_id}`],
      }
    )()

    return NextResponse.json(data, {
      headers: {
        'Cache-Control': `private, s-maxage=${MATCHES_CACHE_SECONDS}, stale-while-revalidate`,
      },
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to fetch matches'
    return NextResponse.json(
      { detail: message },
      { status: 502 }
    )
  }
}
