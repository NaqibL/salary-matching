import { NextRequest, NextResponse } from 'next/server'
import { revalidateTag } from 'next/cache'
import { getUserIdFromToken, MATCHES_CACHE_TAG_PREFIX } from '@/lib/jwt-verify'

/**
 * Invalidate matches cache for the current user.
 * Call after: resume upload/process, job rating (markInteraction), compute taste.
 * Requires Authorization: Bearer <token>.
 */
export async function POST(request: NextRequest) {
  const authorization = request.headers.get('authorization')
  const user_id = await getUserIdFromToken(authorization)

  if (!user_id) {
    return NextResponse.json(
      { error: 'Authorization required' },
      { status: 401 }
    )
  }

  try {
    revalidateTag(`${MATCHES_CACHE_TAG_PREFIX}${user_id}`)
    return NextResponse.json({ revalidated: true, tag: `${MATCHES_CACHE_TAG_PREFIX}${user_id}` })
  } catch (err) {
    console.error('[revalidate-matches]', err)
    return NextResponse.json({ error: 'Revalidation failed' }, { status: 500 })
  }
}
