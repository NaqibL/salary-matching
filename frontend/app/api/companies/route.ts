import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

import { getApiBaseUrl } from '../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

export async function GET() {
  const res = await fetch(`${API_BASE_URL}/api/companies`, { cache: 'no-store' })
  if (!res.ok) {
    return NextResponse.json([], { status: 200 })
  }
  const data = await res.json()
  return NextResponse.json(data, {
    headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate' },
  })
}
