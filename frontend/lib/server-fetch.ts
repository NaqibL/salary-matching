/**
 * Base URL for Railway FastAPI backend. Throws in non-development environments
 * if NEXT_PUBLIC_API_URL is not set, so misconfigured deploys fail loudly.
 */
export function getApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL
  if (!url) {
    if (process.env.NODE_ENV !== 'development') {
      throw new Error(
        'NEXT_PUBLIC_API_URL is not set. Configure it in your Vercel environment variables.'
      )
    }
    return 'http://localhost:8000'
  }
  return url
}

/**
 * Base URL for server-side fetch to our own Next.js API routes.
 * Required because relative URLs don't resolve correctly during SSR.
 */
function getAppBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_APP_URL) {
    return process.env.NEXT_PUBLIC_APP_URL
  }
  if (process.env.VERCEL_URL) {
    return `https://${process.env.VERCEL_URL}`
  }
  return 'http://localhost:3000'
}

export async function fetchDashboardSummary() {
  const res = await fetch(`${getAppBaseUrl()}/api/dashboard/summary`, {
    next: { tags: ['dashboard-stats'] },
  })
  if (!res.ok) throw new Error('Failed to fetch dashboard summary')
  return res.json()
}

export async function fetchJobsOverTimePostedAndRemoved(limitDays = 90) {
  const res = await fetch(
    `${getAppBaseUrl()}/api/dashboard/jobs-over-time-posted-and-removed?limit_days=${limitDays}`,
    { next: { tags: ['dashboard-stats'] } },
  )
  if (!res.ok) throw new Error('Failed to fetch jobs over time')
  return res.json()
}
