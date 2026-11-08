'use client'

import useSWR from 'swr'
import { Users } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { SeniorityBreakdownRow } from '@/lib/types'
import { EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'
import { fmtMoney } from './ChartTooltip'

/** Compact ladder: level, live ads, median advertised monthly base (one axis per figure). */
export function SeniorityTable() {
  const { data, isLoading } = useSWR<SeniorityBreakdownRow[]>(
    'dashboard-seniority-breakdown',
    dashboardApi.getSeniorityBreakdown,
    DASHBOARD_SWR_CONFIG,
  )
  const rows = data ?? []
  const maxJobs = Math.max(1, ...rows.map((r) => r.jobs))

  if (isLoading && !data) return <div className="h-48 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-700" />
  if (rows.length === 0) {
    return <EmptyState icon={Users} message="No seniority data yet" description="Levels are read from ad text during processing." className="py-8" />
  }

  return (
    <table className="min-w-full text-sm">
      <thead className="text-left text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
        <tr>
          <th className="px-2 py-2 font-medium">Level</th>
          <th className="px-2 py-2 font-medium">Live ads</th>
          <th className="px-2 py-2 font-medium text-right">Median pay</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-200">
        {rows.map((r) => (
          <tr key={r.seniority}>
            <td className="px-2 py-1.5 font-medium">{r.seniority}</td>
            <td className="px-2 py-1.5 min-w-[7rem]">
              <div className="flex items-center gap-2">
                <div className="h-2 flex-1 rounded-sm bg-slate-100 dark:bg-slate-700/60">
                  <div className="h-2 rounded-sm" style={{ width: `${Math.max(2, (100 * r.jobs) / maxJobs)}%`, backgroundColor: 'var(--viz-1, #2a78d6)' }} />
                </div>
                <span className="w-12 text-right text-xs tabular-nums">{r.jobs.toLocaleString()}</span>
              </div>
            </td>
            <td className="px-2 py-1.5 text-right tabular-nums">{fmtMoney(r.median_salary)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
