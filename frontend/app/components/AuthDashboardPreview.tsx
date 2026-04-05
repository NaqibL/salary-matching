'use client'

import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Briefcase, CheckCircle, Database } from 'lucide-react'
import { Card, CardBody } from '@/components/design'
import { Skeleton } from '@/components/ui/skeleton'

type Summary = {
  total_jobs: number
  active_jobs: number
  jobs_with_embeddings: number
}

export interface AuthDashboardPreviewProps {
  summary: Summary | null
  activeJobsOverTime: Array<{ date: string; active_count: number }>
  jobsByCategory: Array<{ category: string; count: number }>
  loading: boolean
}

function formatDate(d: string) {
  const date = new Date(d)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function AuthDashboardPreview({
  summary,
  activeJobsOverTime,
  jobsByCategory,
  loading,
}: AuthDashboardPreviewProps) {
  const hasData = summary || activeJobsOverTime.length > 0 || jobsByCategory.length > 0

  if (loading && !hasData) {
    return (
      <div className="space-y-8">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    )
  }

  if (!hasData) {
    return null
  }

  return (
    <div className="space-y-8">
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Card size="compact" className="flex flex-row items-center gap-4 border-slate-200 dark:border-slate-700">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 dark:bg-slate-700">
              <Briefcase className="size-5 text-slate-600 dark:text-slate-400" />
            </div>
            <div>
              <div className="text-xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                {summary.total_jobs?.toLocaleString() ?? '—'}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">Total jobs</div>
            </div>
          </Card>
          <Card size="compact" className="flex flex-row items-center gap-4 border-slate-200 dark:border-slate-700">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
              <CheckCircle className="size-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <div className="text-xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
                {summary.active_jobs?.toLocaleString() ?? '—'}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">Active jobs</div>
            </div>
          </Card>
          <Card size="compact" className="flex flex-row items-center gap-4 border-slate-200 dark:border-slate-700 col-span-2 sm:col-span-1">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-indigo-100 dark:bg-indigo-900/30">
              <Database className="size-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <div className="text-xl font-bold tabular-nums text-indigo-600 dark:text-indigo-400">
                {summary.jobs_with_embeddings?.toLocaleString() ?? '—'}
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400">With embeddings</div>
            </div>
          </Card>
        </div>
      )}

      {activeJobsOverTime.length > 0 && (
        <Card className="border-slate-200 dark:border-slate-700">
          <CardBody>
            <h3 className="mb-4 text-sm font-medium text-slate-700 dark:text-slate-300">
              Active jobs over time (last 30 days)
            </h3>
            <div className="h-[260px] w-full min-h-[200px] sm:h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activeJobsOverTime} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="authActiveJobsGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="rgb(59, 130, 246)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="rgb(59, 130, 246)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(226, 232, 240)" />
                  <XAxis dataKey="date" tickFormatter={formatDate} fontSize={11} />
                  <YAxis fontSize={11} />
                  <Tooltip
                    formatter={(value: number) => [value.toLocaleString(), 'Active jobs']}
                    labelFormatter={(label) => formatDate(label)}
                  />
                  <Area
                    type="monotone"
                    dataKey="active_count"
                    stroke="rgb(59, 130, 246)"
                    strokeWidth={2}
                    fill="url(#authActiveJobsGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      )}

      {jobsByCategory.length > 0 && (
        <Card className="border-slate-200 dark:border-slate-700">
          <CardBody>
            <h3 className="mb-4 text-sm font-medium text-slate-700 dark:text-slate-300">
              Top categories (last 30 days)
            </h3>
            <div className="h-[260px] w-full min-h-[200px] sm:h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={jobsByCategory} layout="vertical" margin={{ left: 100, right: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(226, 232, 240)" />
                  <XAxis type="number" fontSize={11} />
                  <YAxis type="category" dataKey="category" width={95} fontSize={11} />
                  <Tooltip formatter={(value: number) => [value.toLocaleString(), 'Jobs']} />
                  <Bar dataKey="count" name="Jobs" fill="rgb(99, 102, 241)" radius={[0, 4, 4, 0]} barSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
