import { DashboardWithAuth } from './DashboardWithAuth'
import { fetchDashboardSummary, fetchJobsOverTimePostedAndRemoved } from '@/lib/server-fetch'

export default async function DashboardPage() {
  const [initialSummary, initialJobsOverTime] = await Promise.all([
    fetchDashboardSummary().catch(() => null),
    fetchJobsOverTimePostedAndRemoved(90).catch(() => null),
  ])

  return (
    <DashboardWithAuth
      initialSummary={initialSummary}
      initialJobsOverTime={Array.isArray(initialJobsOverTime) ? initialJobsOverTime : null}
    />
  )
}
