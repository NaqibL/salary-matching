/**
 * Server-side JWT verification for Supabase tokens.
 * Used by API routes to extract user_id from the Authorization header.
 */
import { jwtVerify, createRemoteJWKSet } from 'jose'

function getJwksUrl(): string {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
  return url ? `${url.replace(/\/$/, '')}/auth/v1/.well-known/jwks.json` : ''
}

export async function getUserIdFromToken(authorization: string | null): Promise<string | null> {
  if (!authorization?.startsWith('Bearer ')) return null
  const token = authorization.slice(7).trim()
  if (!token) return null

  const secret = process.env.SUPABASE_JWT_SECRET
  const jwksUrl = getJwksUrl()

  try {
    if (secret) {
      // Legacy: symmetric secret (HS256)
      const { payload } = await jwtVerify(
        token,
        new TextEncoder().encode(secret),
        { algorithms: ['HS256'] }
      )
      return (payload.sub as string) ?? null
    }
    if (jwksUrl) {
      // JWKS (ES256, RS256)
      const { payload } = await jwtVerify(token, createRemoteJWKSet(new URL(jwksUrl)), {
        algorithms: ['ES256', 'RS256'],
      })
      return (payload.sub as string) ?? null
    }
  } catch {
    // Token invalid or expired
  }
  return null
}

export const MATCHES_CACHE_TAG_PREFIX = 'matches-'
