import { NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()

export const dynamic = 'force-dynamic'

/** raw company name -> canonical name, for the company field's autocomplete. */
export async function GET() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/companies/aliases`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({}, { status: 200 })
    return NextResponse.json(await res.json(), {
      headers: { 'Cache-Control': 'public, s-maxage=300' },
    })
  } catch (err) {
    console.error('[companies/aliases]', err)
    return NextResponse.json({}, { status: 200 })
  }
}
