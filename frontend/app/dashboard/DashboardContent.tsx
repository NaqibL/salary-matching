'use client'

import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import dynamic from 'next/dynamic'
import { Database, BarChart2 } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import { Layout } from '../components/layout'
import NavUserActions from '../components/NavUserActions'
import {
  Card,
  CardBody,
  EmptyState,
  LoadingState,
} from '@/components/design'
import { DashboardErrorBoundary } from './DashboardErrorBoundary'
import { DashboardSummary } from './DashboardSummary'
import { JobsOverTimeChart } from './JobsOverTimeChart'
import { DashboardCharts } from './DashboardCharts'
import { toast } from 'sonner'
import type { Summary } from './DashboardSummary'
import type { JobsPostedRemovedPoint } from './JobsOverTimeChart'

const LazyDashboardCharts = dynamic(() => import('./DashboardCharts').then((m) => ({ default: m.DashboardCharts })), {
  ssr: false,
  loading: () => (
    <div className="space-y-8">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="h-64 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="h-96 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
      </div>
    </div>
  ),
})

type CategoryStats = {
  active_count: number
  top_employment_type: string | null
  top_position_level: string | null
  avg_salary: number | null
  employment_types: Array<{ employment_type: string; count: number }>
  position_levels: Array<{ position_level: string; count: number }>
  salary_buckets: Array<{ bucket: string; count: number }>
}

const TIME_RANGE_OPTIONS = [
  { value: 30, label: '30d' },
  { value: 90, label: '90d' },
  { value: 180, label: '180d' },
  { value: 365, label: '365d' },
]

export interface DashboardContentProps {
  initialSummary: Summary | null
  initialJobsOverTime: JobsPostedRemovedPoint[] | null
}

export function DashboardContent({ initialSummary, initialJobsOverTime }: DashboardContentProps) {
  const [activeJobsOverTime, setActiveJobsOverTime] = useState<Array<{ date: string; active_count: number }>>([])
  const [jobsByCategory, setJobsByCategory] = useState<Array<{ category: string; count: number }>>([])
  const [jobsByEmploymentType, setJobsByEmploymentType] = useState<Array<{ employment_type: string; count: number }>>([])
  const [jobsByPositionLevel, setJobsByPositionLevel] = useState<Array<{ position_level: string; count: number }>>([])
  const [salaryDistribution, setSalaryDistribution] = useState<Array<{ bucket: string; count: number }>>([])
  const [loading, setLoading] = useState(true)
  const [limitDays, setLimitDays] = useState(90)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [categoryTrends, setCategoryTrends] = useState<
    Array<{ date: string; active_count: number; added_count: number; removed_count: number }>
  >([])
  const [categoryStats, setCategoryStats] = useState<CategoryStats | null>(null)
  const [categoryDetailLoading, setCategoryDetailLoading] = useState(false)

  const formatDate = useCallback((d: string) => {
    const date = new Date(d)
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' })
  }, [])

  const employmentData = useMemo(
    () =>
      selectedCategory && categoryStats
        ? categoryStats.employment_types.filter((x) => x.employment_type !== 'Unknown')
        : jobsByEmploymentType,
    [selectedCategory, categoryStats, jobsByEmploymentType]
  )
  const positionData = useMemo(
    () =>
      selectedCategory && categoryStats
        ? categoryStats.position_levels.filter((x) => x.position_level !== 'Unknown')
        : jobsByPositionLevel,
    [selectedCategory, categoryStats, jobsByPositionLevel]
  )
  const salaryData = useMemo(
    () => (selectedCategory && categoryStats ? categoryStats.salary_buckets : salaryDistribution),
    [selectedCategory, categoryStats, salaryDistribution]
  )

  const hasRetriedRef = useRef(false)

  // Static chart data (category, employment type, position level, salary) — fetched once,
  // these don't change with the time range selector.
  useEffect(() => {
    const load = async () => {
      try {
        const data = await dashboardApi.getChartsStatic()
        setJobsByCategory((data.jobs_by_category || []).filter((x) => x.category !== 'Unknown'))
        setJobsByEmploymentType((data.jobs_by_employment_type || []).filter((x) => x.employment_type !== 'Unknown'))
        setJobsByPositionLevel((data.jobs_by_position_level || []).filter((x) => x.position_level !== 'Unknown'))
        setSalaryDistribution(data.salary_distribution || [])
      } catch {
        // Static data unavailable — charts will remain empty
      }
    }
    load()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Active jobs over time — re-fetched when the time range changes.
  useEffect(() => {
    const load = async (isRetry = false) => {
      setLoading(true)
      try {
        const ajo = await dashboardApi.getActiveJobsOverTime(limitDays)
        setActiveJobsOverTime(ajo || [])
        hasRetriedRef.current = false
      } catch (err: unknown) {
        if (!isRetry && !hasRetriedRef.current) {
          hasRetriedRef.current = true
          setTimeout(() => load(true), 1500)
        } else {
          toast.error('Failed to load dashboard. Is the API server running?')
        }
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [limitDays])

  useEffect(() => {
    if (!selectedCategory) {
      setCategoryTrends([])
      setCategoryStats(null)
      return
    }
    const load = async () => {
      setCategoryDetailLoading(true)
      try {
        const [trends, stats] = await Promise.all([
          dashboardApi.getCategoryTrends(selectedCategory, limitDays),
          dashboardApi.getCategoryStats(selectedCategory),
        ])
        setCategoryTrends(trends || [])
        setCategoryStats(stats || null)
      } catch {
        setCategoryTrends([])
        setCategoryStats(null)
      } finally {
        setCategoryDetailLoading(false)
      }
    }
    load()
  }, [selectedCategory, limitDays])

  const hasData =
    initialSummary ||
    (initialJobsOverTime && initialJobsOverTime.length > 0) ||
    activeJobsOverTime.length > 0 ||
    jobsByCategory.length > 0

  return (
    <Layout userSlot={<NavUserActions />}>
      <DashboardErrorBoundary>
        {/* ── Page header ──────────────────────────────────────────────────── */}
        <div className="-mx-4 lg:-mx-8 px-4 lg:px-8 pt-10 pb-10 mb-8 bg-gradient-to-br from-indigo-50/60 via-white to-slate-50 dark:from-indigo-950/15 dark:via-slate-900 dark:to-slate-900 border-b border-slate-200/70 dark:border-slate-800">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-11 items-center justify-center rounded-xl bg-indigo-100 dark:bg-indigo-950/50">
                <BarChart2 className="size-5 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                  Dashboard
                </h1>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Job market analytics and trends
                </p>
              </div>
            </div>
            <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-700">
              {TIME_RANGE_OPTIONS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setLimitDays(value)}
                  className={`px-4 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 ${
                    limitDays === value
                      ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100'
                      : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && !hasData ? (
          <LoadingState variant="dashboard" />
        ) : !hasData ? (
          <Card className="border-slate-200 dark:border-slate-700">
            <CardBody>
              <EmptyState
                icon={Database}
                message="No dashboard data"
                description="Live job data will appear when the API server is connected and has crawled jobs."
              />
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-8">
            <DashboardSummary fallbackData={initialSummary} />

            <section className="space-y-6">
              <h2 className="text-lg font-semibold leading-tight text-slate-900 dark:text-slate-100">
                Jobs over time
              </h2>
              <div className="space-y-6">
                <JobsOverTimeChart limitDays={limitDays} fallbackData={initialJobsOverTime} />
                <LazyDashboardCharts
                  hideJobsOverTimeHeader
                  activeJobsOverTime={activeJobsOverTime}
                  jobsByCategory={jobsByCategory}
                  employmentData={employmentData}
                  positionData={positionData}
                  salaryData={salaryData}
                  categoryTrends={categoryTrends}
                  selectedCategory={selectedCategory}
                  categoryStats={categoryStats}
                  categoryDetailLoading={categoryDetailLoading}
                  limitDays={limitDays}
                  onCategorySelect={setSelectedCategory}
                  formatDate={formatDate}
                />
              </div>
            </section>
          </div>
        )}
      </DashboardErrorBoundary>
    </Layout>
  )
}
