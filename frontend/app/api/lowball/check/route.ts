import { NextRequest, NextResponse } from 'next/server'
import { getUserIdFromToken } from '@/lib/jwt-verify'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const authorization = request.headers.get('authorization')
  const userId = await getUserIdFromToken(authorization)
  if (!userId) {
    return NextResponse.json({ detail: 'Authorization required' }, { status: 401 })
  }

  const body = await request.json()
  const res = await fetch(`${API_BASE_URL}/api/lowball/check`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: authorization!,
    },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
