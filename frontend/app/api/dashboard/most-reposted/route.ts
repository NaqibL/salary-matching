import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 3600

export const revalidate = REVALIDATE_SECONDS

export async function GET(req: NextRequest) {
  const days = req.nextUrl.searchParams.get('days') === '90' ? '90' : '365'
  const limitRaw = Number(req.nextUrl.searchParams.get('limit') ?? '20')
  const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(limitRaw, 1), 100) : 20
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/dashboard/most-reposted-public?days=${days}&limit=${limit}`,
          { headers: { 'Content-Type': 'application/json' }, next: { revalidate: REVALIDATE_SECONDS } }
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-most-reposted', days, String(limit)],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/most-reposted]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
