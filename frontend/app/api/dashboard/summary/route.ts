import { NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 3600 // 1 hour

async function fetchSummary() {
  const res = await fetch(`${API_BASE_URL}/api/dashboard/summary-public`, {
    headers: { 'Content-Type': 'application/json' },
    next: { revalidate: REVALIDATE_SECONDS },
  })
  if (!res.ok) {
    throw new Error(`Backend error: ${res.status}`)
  }
  return res.json()
}

export const revalidate = REVALIDATE_SECONDS

export async function GET() {
  try {
    const data = await unstable_cache(
      fetchSummary,
      ['dashboard-summary'],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: {
        'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate`,
      },
    })
  } catch (err) {
    console.error('[dashboard/summary]', err)
    return NextResponse.json(
      { detail: 'Failed to fetch dashboard summary' },
      { status: 502 }
    )
  }
}
