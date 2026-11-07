'use client'

import useSWR from 'swr'
import { Repeat } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { MostRepostedRow } from '@/lib/types'
import { monthYear, salaryRangeText } from '@/lib/repost'
import { Card, CardBody, EmptyState } from '@/components/design'
import { DASHBOARD_SWR_CONFIG } from '@/lib/swr-config'

export function MostRepostedTable() {
  const { data, error, isLoading } = useSWR<MostRepostedRow[]>(
    'dashboard-most-reposted-365',
    () => dashboardApi.getMostReposted(365, 20),
    DASHBOARD_SWR_CONFIG,
  )

  return (
    <Card className="border-slate-200 dark:border-slate-700">
      <CardBody>
        <div className="flex items-center gap-2 mb-1">
          <Repeat className="w-4 h-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Most reposted roles · last 12 months</h3>
        </div>
        <p className="text-xs text-slate-400 dark:text-slate-500 mb-3">
          Each distinct posting text counts once. Reposts are shown as that posting&apos;s history.
        </p>
        {isLoading && <div className="h-24 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />}
        {error && <EmptyState icon={Repeat} message="Couldn't load reposts" description="Try again later." />}
        {data && data.length === 0 && <EmptyState icon={Repeat} message="No reposted roles yet" description="Appears after the first crawl with posting groups." />}
        {data && data.length > 0 && (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs">
              <thead className="text-left text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="px-2 py-1 font-medium">Role</th>
                  <th className="px-2 py-1 font-medium">Company</th>
                  <th className="px-2 py-1 font-medium text-right">Postings</th>
                  <th className="px-2 py-1 font-medium">First</th>
                  <th className="px-2 py-1 font-medium">Last</th>
                  <th className="px-2 py-1 font-medium">Latest range</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {data.map(r => (
                  <tr key={r.canonical_job_uuid} className="text-slate-700 dark:text-slate-200">
                    <td className="px-2 py-1.5 max-w-[16rem] truncate" title={r.title ?? ''}>{r.title ?? '—'}</td>
                    <td className="px-2 py-1.5 max-w-[12rem] truncate" title={r.company ?? ''}>
                      {r.distinct_companies >= 2 ? `${r.distinct_companies} companies` : (r.company ?? '—')}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{r.reposts_in_window}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{monthYear(r.first_posted) || '—'}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{monthYear(r.last_posted) || '—'}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">{salaryRangeText(r.latest_salary_min, r.latest_salary_max) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
