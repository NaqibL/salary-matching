import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 900

export const revalidate = REVALIDATE_SECONDS

export async function GET(request: NextRequest) {
  const limit = request.nextUrl.searchParams.get('limit') ?? '20'
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/companies/popular?limit=${limit}`,
          { next: { revalidate: REVALIDATE_SECONDS } },
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      [`companies-popular-${limit}`],
      { revalidate: REVALIDATE_SECONDS },
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[companies/popular]', err)
    return NextResponse.json([], { status: 200 })
  }
}
