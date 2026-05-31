import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE = getApiBaseUrl()

export async function GET(request: NextRequest) {
  const auth = request.headers.get('authorization')
  if (!auth) {
    return NextResponse.json({ error: 'Authorization required' }, { status: 401 })
  }
  const res = await fetch(`${API_BASE}/api/admin/cache-timestamp`, {
    headers: { Authorization: auth },
  })
  const data = await res.json()
  if (!res.ok) {
    return NextResponse.json(data, { status: res.status })
  }
  return NextResponse.json(data)
}
