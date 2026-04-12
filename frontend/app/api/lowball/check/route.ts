import { NextRequest, NextResponse } from 'next/server'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const authorization = request.headers.get('authorization')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authorization) headers['Authorization'] = authorization

  const body = await request.json()
  const res = await fetch(`${API_BASE_URL}/api/lowball/check`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
