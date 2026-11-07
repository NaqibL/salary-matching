'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { postingsApi } from '@/lib/api'
import type { PostingHistory } from '@/lib/types'
import { fullDate, monthYear, salaryMovement, salaryRangeText } from '@/lib/repost'

const ROWS_COLLAPSED = 8

export function PostingHistoryPanel({ jobUuid }: { jobUuid: string }) {
  const { data, error, isLoading } = useSWR<PostingHistory>(
    ['posting-history', jobUuid],
    () => postingsApi.getHistory(jobUuid),
    { revalidateOnFocus: false, dedupingInterval: 3600000 },
  )
  const [showAll, setShowAll] = useState(false)

  if (isLoading) {
    return (
      <div className="mt-3 space-y-2" aria-busy="true">
        <div className="h-3 w-2/3 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />
        <div className="h-3 w-1/2 rounded bg-slate-100 dark:bg-slate-700 animate-pulse" />
      </div>
    )
  }
  if (error || !data) {
    return <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">Couldn&apos;t load posting history.</p>
  }

  const occ = data.occurrences
  const rows = showAll ? occ : occ.slice(0, ROWS_COLLAPSED)
  const movement = salaryMovement(occ)
  const companies = data.distinct_companies >= 2 ? ` · ${data.distinct_companies} company names` : ''

  return (
    <div className="mt-3 rounded-lg border border-slate-100 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40 p-3">
      <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
        First seen {monthYear(data.first_posted)} · last {monthYear(data.last_posted)} · {data.repost_count} postings{companies}
      </p>
      {movement && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{movement}</p>
      )}
      <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-700">
        {rows.map(o => (
          <li key={o.job_uuid} className="py-1.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <span className="text-slate-600 dark:text-slate-300 tabular-nums">{fullDate(o.date) || '—'}</span>
              <span className={o.is_active ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}>
                {o.is_active ? 'Active' : 'Closed'}
              </span>
            </div>
            <div className="flex flex-wrap justify-between gap-x-2 text-slate-500 dark:text-slate-400">
              <span className="truncate">{o.company || 'Company not listed'}</span>
              <span>{salaryRangeText(o.salary_min, o.salary_max) ?? 'No salary listed'}</span>
            </div>
          </li>
        ))}
      </ul>
      {occ.length > ROWS_COLLAPSED && (
        <button
          type="button"
          onClick={() => setShowAll(v => !v)}
          className="mt-1 text-xs font-medium text-indigo-500 hover:text-indigo-700 dark:text-indigo-400"
        >
          {showAll ? 'Show fewer' : `Show all ${occ.length}`}
        </button>
      )}
      <p className="mt-2 text-[11px] leading-snug text-slate-400 dark:text-slate-500">
        Frequent reposting can mean ongoing hiring, high turnover or an agency listing. Treat it as a signal, not a verdict.
      </p>
    </div>
  )
}
