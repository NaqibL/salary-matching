import { DashboardWithAuth } from './DashboardWithAuth'
import { fetchDashboardSummary, fetchJobsOverTimePostedAndRemoved, fetchMarketStats } from '@/lib/server-fetch'
import { DEFAULT_RANGE } from './JobsOverTimeChart'

export default async function DashboardPage() {
  const [initialStats, initialJobsOverTime, summary] = await Promise.all([
    fetchMarketStats().catch(() => null),
    fetchJobsOverTimePostedAndRemoved(DEFAULT_RANGE).catch(() => null),
    fetchDashboardSummary().catch(() => null),
  ])

  return (
    <DashboardWithAuth
      initialStats={initialStats && typeof initialStats === 'object' ? initialStats : null}
      initialJobsOverTime={Array.isArray(initialJobsOverTime) ? initialJobsOverTime : null}
      trackedTotal={typeof summary?.jobs_seen_total === 'number' ? summary.jobs_seen_total : null}
    />
  )
}
