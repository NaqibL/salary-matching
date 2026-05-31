import { NextRequest, NextResponse } from 'next/server'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE = getApiBaseUrl()

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
