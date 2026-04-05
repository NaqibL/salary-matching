import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const REVALIDATE_SECONDS = 3600

export const revalidate = REVALIDATE_SECONDS

export async function GET(request: NextRequest) {
  const limitDays = Math.min(Math.max(parseInt(request.nextUrl.searchParams.get('limit_days') || '90', 10), 1), 365)
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/dashboard/active-jobs-over-time-public?limit_days=${limitDays}`,
          { headers: { 'Content-Type': 'application/json' }, next: { revalidate: REVALIDATE_SECONDS } }
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-active-jobs-over-time', String(limitDays)],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/active-jobs-over-time]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
