import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

// Never stored in the Next.js data cache: a saved copy per filter/sort combination could be
// days older than its neighbours, so one company showed different numbers depending on the
// button pressed. The backend keeps its own short cache; the CDN holds a response for 5 min.
export const dynamic = 'force-dynamic'

const CDN_SECONDS = 300
const ALLOWED = new Set(['family', 'category', 'q', 'agency', 'min_active', 'sort', 'limit'])

export async function GET(request: NextRequest) {
  const qs = new URLSearchParams()
  for (const [k, v] of request.nextUrl.searchParams.entries()) {
    if (ALLOWED.has(k) && v) qs.set(k, v.slice(0, 80))
  }
  qs.sort()
  try {
    const res = await fetch(`${API_BASE_URL}/api/companies/stats?${qs.toString()}`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`Backend error: ${res.status}`)
    return NextResponse.json(await res.json(), {
      headers: { 'Cache-Control': `public, s-maxage=${CDN_SECONDS}` },
    })
  } catch (err) {
    console.error('[companies/stats]', err)
    return NextResponse.json({ detail: 'Failed to fetch company stats' }, { status: 502 })
  }
}
