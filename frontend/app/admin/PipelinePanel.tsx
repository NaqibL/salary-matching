'use client'

import useSWR from 'swr'
import { Database } from 'lucide-react'
import { dashboardApi } from '@/lib/api'
import type { Summary } from '@/app/dashboard/DashboardSummary'
import { Card, CardBody } from '@/components/design'

const fmt = (n: number | undefined | null) => (n == null ? '—' : n.toLocaleString())

/** Owner-only pipeline health (moved off the public dashboard in SGSAL-028). */
export function PipelinePanel() {
  const { data, error, isLoading } = useSWR<Summary>('admin-pipeline-summary', () => dashboardApi.getSummary(), {
    revalidateOnFocus: false,
  })

  const rows: Array<[string, string, string]> = data
    ? [
        ['Postings seen', fmt(data.jobs_seen_total), 'every job row, active or closed'],
        ['Searchable', fmt(data.jobs_searchable_total), 'a vector exists for the job or its canonical posting'],
        ['Vectors stored', fmt(data.vectors_stored), 'deduplicated job_embeddings rows'],
        ['Active, searchable', fmt(data.jobs_with_embeddings), `of ${fmt(data.active_jobs_total)} active`],
        ['Embedding backlog', fmt(data.active_jobs_total - data.jobs_with_embeddings), 'active jobs not yet searchable'],
        ['Inactive jobs', fmt(data.inactive_jobs), 'closed postings kept as history'],
        ['Need backfill', fmt(data.jobs_needing_backfill), 'active jobs missing category / employment type'],
      ]
    : []

  return (
    <Card className="border-slate-200 dark:border-slate-700">
      <CardBody>
        <div className="flex items-center gap-2 mb-3">
          <Database className="w-4 h-4 text-indigo-500" aria-hidden />
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Pipeline health</h3>
        </div>
        {isLoading && !data && <div className="h-24 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />}
        {error && <p className="text-sm text-slate-500">Couldn&apos;t load the summary.</p>}
        {data && (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            {rows.map(([label, value, hint]) => (
              <div key={label} className="flex items-baseline justify-between gap-3 border-b border-slate-100 dark:border-slate-800 py-1">
                <dt className="text-slate-600 dark:text-slate-300">
                  {label}
                  <span className="block text-[11px] text-slate-400 dark:text-slate-500">{hint}</span>
                </dt>
                <dd className="tabular-nums font-medium text-slate-800 dark:text-slate-100">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardBody>
    </Card>
  )
}
