import { NextRequest, NextResponse } from 'next/server'
import { revalidateTag } from 'next/cache'

/**
 * On-demand revalidation for dashboard stats.
 * Call with: POST /api/revalidate?tag=dashboard-stats
 * Header: X-Crawl-Secret: YOUR_CRON_SECRET (never put secret in URL — it can leak in logs)
 */
export async function POST(request: NextRequest) {
  const tag = request.nextUrl.searchParams.get('tag')
  const secret = request.headers.get('x-crawl-secret')
  const expectedSecret = process.env.CRON_SECRET || process.env.REVALIDATE_SECRET

  if (tag !== 'dashboard-stats') {
    return NextResponse.json({ error: 'Invalid tag' }, { status: 400 })
  }

  if (!expectedSecret || secret !== expectedSecret) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    revalidateTag('dashboard-stats')
    return NextResponse.json({ revalidated: true, tag, now: Date.now() })
  } catch (err) {
    console.error('[revalidate]', err)
    return NextResponse.json({ error: 'Revalidation failed' }, { status: 500 })
  }
}
