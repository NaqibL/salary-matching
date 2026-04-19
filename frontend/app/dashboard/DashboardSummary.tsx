'use client'

import useSWR from 'swr'
import { Briefcase, CheckCircle, XCircle, Database, AlertCircle, SearchX } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import { Card } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

export type Summary = {
  total_jobs: number
  active_jobs: number
  inactive_jobs: number
  by_source: Record<string, number>
  jobs_with_embeddings: number
  inactive_jobs_with_embeddings: number
  jobs_needing_backfill: number
  active_unembedded?: number
}

const SUMMARY_CARDS = [
  {
    key: 'total_jobs',
    label: 'Total jobs',
    icon: Briefcase,
    iconColor: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
    valueColor: 'text-slate-900 dark:text-slate-100',
    valueKey: 'total_jobs' as const,
  },
  {
    key: 'active_jobs',
    label: 'Active jobs',
    icon: CheckCircle,
    iconColor: 'bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
    valueColor: 'text-emerald-600 dark:text-emerald-400',
    valueKey: 'active_jobs' as const,
  },
  {
    key: 'inactive_jobs',
    label: 'Inactive jobs',
    icon: XCircle,
    iconColor: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
    valueColor: 'text-slate-600 dark:text-slate-400',
    valueKey: 'inactive_jobs' as const,
  },
  {
    key: 'jobs_embedded_total',
    label: 'Jobs embedded',
    icon: Database,
    iconColor: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400',
    valueColor: 'text-indigo-600 dark:text-indigo-400',
    valueKey: 'jobs_embedded_total' as const,
    sublabel: null as string | null,
  },
  {
    key: 'jobs_needing_backfill',
    label: 'Need backfill',
    icon: AlertCircle,
    iconColor: 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
    valueColor: 'text-amber-600 dark:text-amber-400',
    valueKey: 'jobs_needing_backfill' as const,
    sublabel: 'Category/employment missing',
  },
  {
    key: 'active_unembedded',
    label: 'Active unembedded',
    icon: SearchX,
    iconColor: 'bg-rose-100 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400',
    valueColor: 'text-rose-600 dark:text-rose-400',
    valueKey: 'active_unembedded' as const,
    sublabel: 'Missing from search',
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

  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">
        Summary
      </h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {SUMMARY_CARDS.map(({ key, label, icon: Icon, iconColor, valueColor, valueKey, sublabel }) => {
          const activeEmbedded = displaySummary?.jobs_with_embeddings ?? 0
          const inactiveEmbedded = displaySummary?.inactive_jobs_with_embeddings ?? 0
          const rawValue =
            valueKey === 'active_unembedded'
              ? (displaySummary?.active_jobs ?? 0) - activeEmbedded
              : valueKey === 'jobs_embedded_total'
              ? activeEmbedded + inactiveEmbedded
              : displaySummary?.[valueKey]
          const embeddedSublabel =
            valueKey === 'jobs_embedded_total'
              ? `${(activeEmbedded / 1000).toFixed(1)}k active · ${(inactiveEmbedded / 1000).toFixed(1)}k inactive`
              : undefined
          const displayValue =
            rawValue != null ? (typeof rawValue === 'number' ? rawValue.toLocaleString() : String(rawValue)) : '—'
          return (
            <Card
              key={key}
              size="compact"
              className="flex flex-col items-center justify-center text-center min-h-[100px] border-slate-200 dark:border-slate-700 transition-shadow hover:shadow-md"
            >
              <div className={`p-2 rounded-lg mb-2 ${iconColor}`}>
                <Icon className="size-5" aria-hidden />
              </div>
              <div className={`text-xl font-bold tabular-nums ${valueColor}`}>
                {displayValue}
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400">{label}</div>
              {(embeddedSublabel ?? sublabel) && (
                <div className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{embeddedSublabel ?? sublabel}</div>
              )}
            </Card>
          )
        })}
      </div>
    </section>
  )
}
