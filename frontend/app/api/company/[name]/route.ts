import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

// Not stored in the Next.js data cache (see companies/stats): a profile saved mid-crawl used
// to be served for days. The backend caches the profile; the CDN holds it for 5 min.
export const dynamic = 'force-dynamic'

const CDN_SECONDS = 300

export async function GET(
  _request: NextRequest,
  { params }: { params: { name: string } },
) {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/companies/${encodeURIComponent(params.name)}/profile`,
      { cache: 'no-store' },
    )
    if (res.status === 404) {
      return NextResponse.json({ detail: 'Company not found' }, { status: 404 })
    }
    if (!res.ok) throw new Error(`Backend error: ${res.status}`)
    return NextResponse.json(await res.json(), {
      headers: { 'Cache-Control': `public, s-maxage=${CDN_SECONDS}` },
    })
  } catch (err) {
    console.error('[company/profile]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
