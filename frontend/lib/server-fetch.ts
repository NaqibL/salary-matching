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
  const res = await fetch(`${getAppBaseUrl()}/api/dashboard/summary`)
  if (!res.ok) throw new Error('Failed to fetch dashboard summary')
  return res.json()
}

export async function fetchJobsOverTimePostedAndRemoved(limitDays = 90) {
  const res = await fetch(
    `${getAppBaseUrl()}/api/dashboard/jobs-over-time-posted-and-removed?limit_days=${limitDays}`
  )
  if (!res.ok) throw new Error('Failed to fetch jobs over time')
  return res.json()
}
