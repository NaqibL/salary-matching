import { NextRequest, NextResponse } from 'next/server'
import { revalidateTag } from 'next/cache'
import { getUserIdFromToken } from '@/lib/jwt-verify'

/**
 * Force revalidate dashboard-stats tag.
 * Auth: X-Crawl-Secret OR Authorization Bearer with user in ADMIN_USER_IDS.
 */
export async function POST(request: NextRequest) {
  const secret = request.headers.get('x-crawl-secret')
  const auth = request.headers.get('authorization')
  const expectedSecret = process.env.CRON_SECRET || process.env.REVALIDATE_SECRET
  const adminIds = new Set((process.env.ADMIN_USER_IDS || '').split(',').map((x) => x.trim()).filter(Boolean))

  let allowed = false
  if (expectedSecret && secret === expectedSecret) {
    allowed = true
  } else if (auth) {
    const userId = await getUserIdFromToken(auth)
    if (userId && adminIds.size > 0 && adminIds.has(userId)) {
      allowed = true
    }
  }

  if (!allowed) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  try {
    revalidateTag('dashboard-stats')
    return NextResponse.json({ revalidated: true, tag: 'dashboard-stats', now: Date.now() })
  } catch (err) {
    console.error('[revalidate-dashboard]', err)
    return NextResponse.json({ error: 'Revalidation failed' }, { status: 500 })
  }
}
