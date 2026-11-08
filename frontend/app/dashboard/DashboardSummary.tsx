'use client'

import useSWR from 'swr'
import { Briefcase, Building2, CheckCircle, Sparkles } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import { Card } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

export type Summary = {
  total_jobs: number
  active_jobs: number
  active_jobs_total: number
  inactive_jobs: number
  by_source: Record<string, number>
  jobs_with_embeddings: number
  inactive_jobs_with_embeddings: number
  jobs_needing_backfill: number
  // SGSAL-024: pipeline reach vs search reach (absent on older cached responses)
  jobs_seen_total?: number
  jobs_searchable_total?: number
  vectors_stored?: number
  // SGSAL-028: visitor tiles
  companies_hiring?: number
  new_this_week?: number
}

const TRACKED_SINCE = 'Mar 2026'

/**
 * Four tiles a visitor understands (SGSAL-028). The pipeline numbers (searchable, inactive,
 * backlog, backfill) live on the owner-only admin page — see app/admin/PipelinePanel.tsx.
 */
const SUMMARY_CARDS = [
  {
    key: 'live',
    label: 'Live jobs',
    icon: CheckCircle,
    iconColor: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
    valueColor: 'text-emerald-600 dark:text-emerald-400',
    pick: (s: Summary) => s.active_jobs_total,
    sublabel: 'open right now',
  },
  {
    key: 'new',
    label: 'New this week',
    icon: Sparkles,
    iconColor: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400',
    valueColor: 'text-indigo-600 dark:text-indigo-400',
    pick: (s: Summary) => s.new_this_week,
    sublabel: 'first seen in the last 7 days',
  },
  {
    key: 'companies',
    label: 'Companies hiring',
    icon: Building2,
    iconColor: 'bg-sky-100 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400',
    valueColor: 'text-sky-700 dark:text-sky-400',
    pick: (s: Summary) => s.companies_hiring,
    sublabel: 'with at least one live job',
  },
  {
    key: 'tracked',
    label: `Postings tracked since ${TRACKED_SINCE}`,
    icon: Briefcase,
    iconColor: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
    valueColor: 'text-slate-900 dark:text-slate-100',
    pick: (s: Summary) => s.jobs_seen_total ?? s.active_jobs_total + s.inactive_jobs,
    sublabel: 'including closed ones',
  },
]

export interface DashboardSummaryProps {
  fallbackData?: Summary | null
}

export function DashboardSummary({ fallbackData }: DashboardSummaryProps) {
  const { data: summary, isLoading, error } = useSWR<Summary>(
    'dashboard-summary',
    () => dashboardApi.getSummary(),
    {
      ...DASHBOARD_SWR_CONFIG,
      fallbackData: fallbackData ?? undefined,
    }
  )

  const displaySummary = summary ?? fallbackData
  if (error && !displaySummary) return null
  if (!displaySummary && isLoading) return null
  if (!displaySummary) return null

  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">
        Summary
      </h2>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {SUMMARY_CARDS.map(({ key, label, icon: Icon, iconColor, valueColor, pick, sublabel }) => {
          const rawValue = pick(displaySummary)
          const displayValue = rawValue != null ? rawValue.toLocaleString() : '—'
          return (
            <Card
              key={key}
              size="compact"
              className="flex flex-col items-center justify-center text-center min-h-[100px] border-slate-200 dark:border-slate-700 transition-shadow hover:shadow-md"
            >
              <div className={`p-2 rounded-lg mb-2 ${iconColor}`}>
                <Icon className="size-5" aria-hidden />
              </div>
              <div className={`text-xl font-bold tabular-nums ${valueColor}`}>{displayValue}</div>
              <div className="text-sm text-slate-500 dark:text-slate-400">{label}</div>
              <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{sublabel}</div>
            </Card>
          )
        })}
      </div>
    </section>
  )
}
