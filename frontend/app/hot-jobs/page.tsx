'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import { Building2, Flame } from 'lucide-react'
import { hotJobsApi } from '@/lib/api'
import type { HotJob, HotJobsResponse } from '@/lib/types'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { PageHeader, EmptyState, LoadingState } from '@/components/design'
import { getDaysAgo } from '@/app/components/JobCard'

function fmtSalary(min: number | null, max: number | null): string | null {
  if (!min && !max) return null
  const fmt = (v: number) => `$${v.toLocaleString()}`
  if (min && max) return `${fmt(min)} – ${fmt(max)} / mo`
  return `${fmt((min ?? max)!)} / mo`
}

function AboveMarketBadge({ pct }: { pct: number | null }) {
  if (pct == null) return null
  const cls =
    pct >= 50
      ? 'bg-emerald-100 text-emerald-700'
      : 'bg-amber-100 text-amber-700'
  return (
    <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${cls}`}>
      +{pct.toFixed(0)}% above market
    </span>
  )
}

function HotJobCard({ job }: { job: HotJob }) {
  const daysAgo = getDaysAgo(job.posted_date ?? undefined)
  const salary = fmtSalary(job.salary_min, job.salary_max)
  const seniority = job.inferred_seniority
  const category = job.categories[0]

  const content = (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm hover:shadow-md transition-shadow dark:border-slate-700 dark:bg-slate-800 p-6">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 line-clamp-2">
            {job.title}
          </h3>
          {job.company_name && (
            <span className="flex items-center gap-1.5 mt-1 text-sm text-slate-500 dark:text-slate-400">
              <Building2 size={14} className="shrink-0" />
              {job.company_name}
            </span>
          )}
        </div>
        <AboveMarketBadge pct={job.above_market_pct} />
      </div>

      {salary && (
        <p className="text-base font-medium text-slate-800 dark:text-slate-200 mb-3">
          {salary}
          <span className="ml-2 text-xs font-normal text-slate-400">Monthly base salary (SGD)</span>
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        {category && (
          <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 font-medium">
            {category}
          </span>
        )}
        {seniority && (
          <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300 font-medium">
            {seniority}
          </span>
        )}
        {daysAgo !== null && (
          <span className="text-slate-400">
            {daysAgo === 0 ? 'Posted today' : daysAgo === 1 ? 'Posted 1 day ago' : `Posted ${daysAgo} days ago`}
          </span>
        )}
      </div>
    </div>
  )

  if (!job.job_url) return content
  return (
    <a href={job.job_url} target="_blank" rel="noopener noreferrer" className="block">
      {content}
    </a>
  )
}

export default function HotJobsPage() {
  const [category, setCategory] = useState('')
  const [seniority, setSeniority] = useState('')

  const { data, isLoading } = useSWR<HotJobsResponse>(
    'hot-jobs',
    () => hotJobsApi.list({ limit: 100 }),
    { revalidateOnFocus: false },
  )

  const jobs = data?.jobs ?? []

  const categories = useMemo(
    () => Array.from(new Set(jobs.flatMap((j) => j.categories))).sort(),
    [jobs],
  )
  const seniorities = useMemo(
    () => Array.from(new Set(jobs.map((j) => j.inferred_seniority).filter((s): s is string => !!s))).sort(),
    [jobs],
  )

  const filtered = jobs.filter((j) => {
    if (category && !j.categories.includes(category)) return false
    if (seniority && j.inferred_seniority !== seniority) return false
    return true
  })

  return (
    <Layout userSlot={<NavUserActions />}>
      <div className="space-y-6">
        <PageHeader
          title="Hot Jobs (Beta)"
          subtitle={`Active listings paying above market rate · Updated daily · ${jobs.length} listings`}
        />

        {jobs.length > 0 && (
          <div className="flex flex-wrap gap-3">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select
              value={seniority}
              onChange={(e) => setSeniority(e.target.value)}
              className="px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">All seniority levels</option>
              {seniorities.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        )}

        {isLoading ? (
          <LoadingState />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Flame}
            message="No above-market listings right now"
            description="Check back after the daily crawl (10:00 SGT)."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filtered.map((job) => (
              <HotJobCard key={job.job_uuid} job={job} />
            ))}
          </div>
        )}
      </div>
    </Layout>
  )
}
