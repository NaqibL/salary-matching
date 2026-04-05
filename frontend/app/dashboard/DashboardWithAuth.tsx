'use client'

import { DashboardContent } from './DashboardContent'
import type { Summary } from './DashboardSummary'
import type { JobsPostedRemovedPoint } from './JobsOverTimeChart'

export interface DashboardWithAuthProps {
  initialSummary: Summary | null
  initialJobsOverTime: JobsPostedRemovedPoint[] | null
}

export function DashboardWithAuth({ initialSummary, initialJobsOverTime }: DashboardWithAuthProps) {
  return (
    <DashboardContent
      initialSummary={initialSummary}
      initialJobsOverTime={initialJobsOverTime}
    />
  )
}
