'use client'

import { useCallback, useMemo, useState } from 'react'
import useSWR from 'swr'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart2 } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import { EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'
import { CHART_TEXT, ChartTooltip, TICK, VIZ_1, VIZ_8 } from './ChartTooltip'

export type JobsPostedRemovedPoint = {
  date: string
  added_count: number
  removed_count: number
}

const RANGES = [30, 90, 365] as const
export const DEFAULT_RANGE = 90

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
  /** Server-rendered data for the default range only. */
  fallbackData?: JobsPostedRemovedPoint[] | null
}

/** The one time chart on the dashboard; the range switch lives here because nothing else uses it. */
export function JobsOverTimeChart({ fallbackData }: JobsOverTimeChartProps) {
  const [limitDays, setLimitDays] = useState<number>(DEFAULT_RANGE)
  const formatDate = useCallback((d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }, [])

  const { data, isLoading, error } = useSWR<JobsPostedRemovedPoint[]>(
    ['dashboard-jobs-over-time-posted-removed', limitDays],
    () => dashboardApi.getJobsOverTimePostedAndRemoved(limitDays),
    { ...DASHBOARD_SWR_CONFIG, fallbackData: limitDays === DEFAULT_RANGE ? fallbackData ?? undefined : undefined },
  )

  const points = data ?? (limitDays === DEFAULT_RANGE ? fallbackData ?? [] : [])
  const domainMax = useMemo(() => getPostedRemovedDomainMax(points), [points])

  if (error && !points.length) return null

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-700 dark:bg-slate-800">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Ads added and removed per day</h3>
          <p className="text-xs text-slate-400 dark:text-slate-500">last {limitDays} days · one bar per day</p>
        </div>
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-700 self-start" role="group" aria-label="Range">
          {RANGES.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={limitDays === value}
              onClick={() => setLimitDays(value)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
                limitDays === value
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {value}d
            </button>
          ))}
        </div>
      </div>
      <div className={`h-[260px] w-full sm:h-[300px] ${CHART_TEXT}`}>
        {isLoading && !points.length ? (
          <div className="h-full w-full animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
        ) : points.length === 0 ? (
          <EmptyState icon={BarChart2} message="No data for this period" description="Daily counts appear once ads are crawled." className="h-full py-8" />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={4} barGap={2} barSize={12}>
              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.15} vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatDate} tick={TICK} minTickGap={24} />
              <YAxis tick={TICK} domain={[0, domainMax]} tickFormatter={(v: number) => v.toLocaleString()} width={48} />
              <Tooltip cursor={{ fill: 'currentColor', fillOpacity: 0.06 }} content={<ChartTooltip labelFormatter={formatDate} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="added_count" name="Added" fill={VIZ_1} radius={[2, 2, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="removed_count" name="Removed" fill={VIZ_8} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
