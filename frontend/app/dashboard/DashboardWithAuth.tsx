'use client'

import { DashboardContent } from './DashboardContent'
import type { MarketStats } from '@/lib/types'
import type { JobsPostedRemovedPoint } from './JobsOverTimeChart'

export interface DashboardWithAuthProps {
  initialStats: MarketStats | null
  initialJobsOverTime: JobsPostedRemovedPoint[] | null
  trackedTotal?: number | null
}

export function DashboardWithAuth(props: DashboardWithAuthProps) {
  return <DashboardContent {...props} />
}
