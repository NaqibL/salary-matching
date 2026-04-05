import { NextRequest, NextResponse } from 'next/server'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function DELETE(request: NextRequest) {
  const auth = request.headers.get('authorization')
  if (!auth) {
    return NextResponse.json({ error: 'Authorization required' }, { status: 401 })
  }
  const { searchParams } = request.nextUrl
  const key = searchParams.get('key')
  const prefix = searchParams.get('prefix')
  const params = new URLSearchParams()
  if (key) params.set('key', key)
  if (prefix) params.set('prefix', prefix)
  const url = `${API_BASE}/api/admin/cache?${params}`
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: auth },
  })
  const data = await res.json()
  if (!res.ok) {
    return NextResponse.json(data, { status: res.status })
  }
  return NextResponse.json(data)
}
