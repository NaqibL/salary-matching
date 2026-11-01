import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 3600

export const revalidate = REVALIDATE_SECONDS

export async function GET(request: NextRequest) {
  const limit = Math.min(Math.max(parseInt(request.nextUrl.searchParams.get('limit') || '25', 10), 1), 50)
  // role_families.key values are snake_case identifiers; drop anything else.
  const roleFamily = (request.nextUrl.searchParams.get('role_family') || '').trim().slice(0, 64)
  const safeRoleFamily = /^[a-z0-9_]+$/.test(roleFamily) ? roleFamily : ''
  const qs = new URLSearchParams({ limit: String(limit) })
  if (safeRoleFamily) qs.set('role_family', safeRoleFamily)
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/dashboard/top-skills-public?${qs.toString()}`,
          { headers: { 'Content-Type': 'application/json' }, next: { revalidate: REVALIDATE_SECONDS } }
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-top-skills', String(limit), safeRoleFamily],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/top-skills]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
