import { NextRequest, NextResponse } from 'next/server'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function GET(request: NextRequest) {
  const auth = request.headers.get('authorization')
  if (!auth) {
    return NextResponse.json({ error: 'Authorization required' }, { status: 401 })
  }
  const res = await fetch(`${API_BASE}/api/admin/cache-stats`, {
    headers: { Authorization: auth },
  })
  const data = await res.json()
  if (!res.ok) {
    return NextResponse.json(data, { status: res.status })
  }
  return NextResponse.json(data)
}
