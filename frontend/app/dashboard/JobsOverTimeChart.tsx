'use client'

import { useCallback, useMemo } from 'react'
import useSWR from 'swr'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { dashboardApi } from '@/lib/api'
import { EmptyState } from '@/components/design'
import { BarChart2 } from 'lucide-react'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

export type JobsPostedRemovedPoint = {
  date: string
  added_count: number
  removed_count: number
}

const CHART_MARGIN_DEFAULT = { top: 8, right: 8, left: 0, bottom: 0 }

function getPostedRemovedDomainMax(data: JobsPostedRemovedPoint[]): number {
  if (!data.length) return 100
  const values = data.flatMap((d) => [d.added_count, d.removed_count]).filter((v) => v > 0)
  if (!values.length) return 100
  const sorted = [...values].sort((a, b) => a - b)
  const p90Index = Math.floor(sorted.length * 0.9)
  const p90 = sorted[p90Index] ?? sorted[sorted.length - 1]
  return Math.max(100, Math.ceil(p90 * 1.2))
}

export interface JobsOverTimeChartProps {
  limitDays: number
  fallbackData?: JobsPostedRemovedPoint[] | null
}

export function JobsOverTimeChart({ limitDays, fallbackData }: JobsOverTimeChartProps) {
  const formatDate = useCallback((d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' })
  }, [])

  const { data, isLoading, error } = useSWR<JobsPostedRemovedPoint[]>(
    ['dashboard-jobs-over-time-posted-removed', limitDays],
    () => dashboardApi.getJobsOverTimePostedAndRemoved(limitDays),
    {
      ...DASHBOARD_SWR_CONFIG,
      fallbackData: fallbackData ?? undefined,
    }
  )

  const jobsPostedAndRemoved = data ?? fallbackData ?? []
  const domainMax = useMemo(() => getPostedRemovedDomainMax(jobsPostedAndRemoved), [jobsPostedAndRemoved])

  if (error) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
      <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-4">
        Added vs removed
      </h3>
      <div className="h-[280px] w-full min-h-[200px] sm:h-[300px]">
        {isLoading && !jobsPostedAndRemoved.length ? (
          <div className="h-full w-full animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
        ) : jobsPostedAndRemoved.length === 0 ? (
          <EmptyState
            icon={BarChart2}
            message="No data for this period"
            description="Added and removed counts will appear once jobs are crawled."
            className="h-full py-8"
          />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={jobsPostedAndRemoved}
              margin={CHART_MARGIN_DEFAULT}
              barCategoryGap={4}
              barGap={2}
              barSize={12}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(226, 232, 240)" />
              <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
              <YAxis fontSize={11} domain={[0, domainMax]} />
              <Tooltip
                formatter={(value: number) => [value.toLocaleString(), '']}
                labelFormatter={(label) => formatDate(label)}
              />
              <Legend />
              <Bar dataKey="added_count" name="Added" fill="rgb(16, 185, 129)" radius={[2, 2, 0, 0]} />
              <Bar dataKey="removed_count" name="Removed" fill="rgb(239, 68, 68)" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
