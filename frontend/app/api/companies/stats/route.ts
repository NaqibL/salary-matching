import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 900

export const revalidate = REVALIDATE_SECONDS

const ALLOWED = new Set(['family', 'category', 'q', 'agency', 'min_active', 'sort', 'limit'])

export async function GET(request: NextRequest) {
  const qs = new URLSearchParams()
  for (const [k, v] of request.nextUrl.searchParams.entries()) {
    if (ALLOWED.has(k) && v) qs.set(k, v.slice(0, 80))
  }
  qs.sort()
  const key = qs.toString()
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(`${API_BASE_URL}/api/companies/stats?${key}`, {
          next: { revalidate: REVALIDATE_SECONDS },
        })
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      [`companies-stats-v3-${key}`],
      { revalidate: REVALIDATE_SECONDS },
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[companies/stats]', err)
    return NextResponse.json({ detail: 'Failed to fetch company stats' }, { status: 502 })
  }
}
