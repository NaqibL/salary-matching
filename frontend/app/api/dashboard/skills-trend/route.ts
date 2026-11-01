import { NextRequest, NextResponse } from 'next/server'
import { unstable_cache } from 'next/cache'

import { getApiBaseUrl } from '../../../../lib/server-fetch'
const API_BASE_URL = getApiBaseUrl()
const REVALIDATE_SECONDS = 3600
const MAX_SKILLS = 8

export const revalidate = REVALIDATE_SECONDS

export async function GET(request: NextRequest) {
  const weeks = Math.min(Math.max(parseInt(request.nextUrl.searchParams.get('weeks') || '12', 10), 1), 26)
  // Normalise the skills list so equivalent selections share one cache entry.
  const seen = new Set<string>()
  const skills: string[] = []
  for (const part of (request.nextUrl.searchParams.get('skills') || '').split(',')) {
    const s = part.trim().slice(0, 64)
    if (s && !seen.has(s.toLowerCase())) {
      seen.add(s.toLowerCase())
      skills.push(s)
    }
  }
  const selected = skills.slice(0, MAX_SKILLS)
  if (selected.length === 0) {
    return NextResponse.json({ detail: 'skills is required' }, { status: 400 })
  }
  const qs = new URLSearchParams({ skills: selected.join(','), weeks: String(weeks) })
  try {
    const data = await unstable_cache(
      async () => {
        const res = await fetch(
          `${API_BASE_URL}/api/dashboard/skills-trend-public?${qs.toString()}`,
          { headers: { 'Content-Type': 'application/json' }, next: { revalidate: REVALIDATE_SECONDS } }
        )
        if (!res.ok) throw new Error(`Backend error: ${res.status}`)
        return res.json()
      },
      ['dashboard-skills-trend', String(weeks), selected.join(',').toLowerCase()],
      { revalidate: REVALIDATE_SECONDS, tags: ['dashboard-stats'] }
    )()
    return NextResponse.json(data, {
      headers: { 'Cache-Control': `public, s-maxage=${REVALIDATE_SECONDS}, stale-while-revalidate` },
    })
  } catch (err) {
    console.error('[dashboard/skills-trend]', err)
    return NextResponse.json({ detail: 'Failed to fetch' }, { status: 502 })
  }
}
