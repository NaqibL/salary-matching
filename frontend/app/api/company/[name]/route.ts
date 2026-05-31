import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 900 // 15 min — aligns with crawl cadence

export const revalidate = REVALIDATE_SECONDS

export async function GET(
  _request: NextRequest,
  { params }: { params: { name: string } },
) {
  const name = params.name
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/companies/${encodeURIComponent(name)}/profile`,
          { next: { revalidate: REVALIDATE_SECONDS } },
        )
        if (res.status === 404) return null
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      [`company-profile-${name}`],
      { revalidate: REVALIDATE_SECONDS },
    )()

    if (!data) {
      return NextResponse.json({ detail: 'Company not found' }, { status: 404 })
    }
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[company/profile]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
