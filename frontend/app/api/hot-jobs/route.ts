import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  const qs = request.nextUrl.searchParams.toString()
  const res = await fetch(`${API_BASE_URL}/api/hot-jobs${qs ? `?${qs}` : ''}`, { cache: 'no-store' })
  if (!res.ok) {
    return NextResponse.json({ jobs: [], count: 0 }, { status: 200 })
  }
  const data = await res.json()
  return NextResponse.json(data, {
    headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate' },
  })
}
