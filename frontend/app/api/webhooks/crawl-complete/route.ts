/**
 * Webhook called by incremental_crawl when crawl completes.
 * Invalidates: Next.js dashboard-stats tag, FastAPI pool + matches + dashboard + job caches.
 * Auth: X-Crawl-Secret header must match CRON_SECRET or REVALIDATE_SECRET.
 */
import { NextRequest, NextResponse } from 'next/server'
import { revalidateTag } from 'next/cache'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.API_URL || 'http://localhost:8000'

export async function POST(request: NextRequest) {
  const secret = request.headers.get('x-crawl-secret')
  const expectedSecret = process.env.CRON_SECRET || process.env.REVALIDATE_SECRET

  if (!expectedSecret || secret !== expectedSecret) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    revalidateTag('dashboard-stats')

    const apiUrl = API_BASE_URL.replace(/\/$/, '')
    const headers: Record<string, string> = { 'X-Crawl-Secret': expectedSecret }

    const [poolRes, matchesRes, dashboardRes, jobRes] = await Promise.all([
      fetch(`${apiUrl}/api/admin/invalidate-pool`, { method: 'POST', headers }),
      fetch(`${apiUrl}/api/admin/invalidate-cache?prefix=matches:`, { method: 'POST', headers }),
      fetch(`${apiUrl}/api/admin/invalidate-cache?prefix=dashboard:`, { method: 'POST', headers }),
      fetch(`${apiUrl}/api/admin/invalidate-cache?prefix=job:`, { method: 'POST', headers }),
    ])

    return NextResponse.json({
      revalidated: true,
      dashboard: true,
      fastapi_pool: poolRes.ok,
      fastapi_matches: matchesRes.ok,
      fastapi_dashboard: dashboardRes.ok,
      fastapi_job: jobRes.ok,
      now: Date.now(),
    })
  } catch (err) {
    console.error('[crawl-complete webhook]', err)
    return NextResponse.json({ error: 'Revalidation failed' }, { status: 500 })
  }
}
