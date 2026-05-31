import { NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

export async function GET() {
  const res = await fetch(`${API_BASE_URL}/api/jobs/taxonomy`)
  if (!res.ok) {
    return NextResponse.json({ clusters: [] }, { status: 200 })
  }
  const data = await res.json()
  return NextResponse.json(data, {
    headers: { 'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate' },
  })
}
