import { NextResponse } from 'next/server'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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
