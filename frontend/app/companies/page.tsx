'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { Building2, Search } from 'lucide-react'
import { companiesApi, dashboardApi } from '@/lib/api'
import type { CompanyAgencyFilter, CompanyStatsResponse, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { familyLabel } from '@/lib/roleFamilies'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, EmptyState, PageHeader } from '@/components/design'
import { CompanyStatsTable } from './CompanyStatsTable'

const MIN_ACTIVE_OPTIONS = [10, 3, 1] as const
const SORTS: CompanyStatsSort[] = ['openings', 'repost_rate', 'median_salary']
const AGENCY_OPTIONS: Array<{ value: CompanyAgencyFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'direct', label: 'Direct employers' },
  { value: 'agency', label: 'Staffing agencies' },
]

const selectCls =
  'rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-sm text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50'

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

function CompaniesExplorer() {
  const router = useRouter()
  const sp = useSearchParams()

  const family = sp.get('family') ?? ''
  const category = sp.get('category') ?? ''
  const agencyParam = sp.get('agency')
  const agency: CompanyAgencyFilter = agencyParam === 'direct' || agencyParam === 'agency' ? agencyParam : 'all'
  const sortParam = sp.get('sort') as CompanyStatsSort | null
  const sort: CompanyStatsSort = sortParam && SORTS.includes(sortParam) ? sortParam : 'openings'
  const minActive = Number(sp.get('min_active')) || 10
  const [query, setQuery] = useState(sp.get('q') ?? '')
  const q = useDebounced(query.trim(), 300)

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(sp.toString())
    if (value) next.set(key, value)
    else next.delete(key)
    const qs = next.toString()
    router.replace(qs ? `/companies?${qs}` : '/companies', { scroll: false })
  }
  useEffect(() => {
    if ((sp.get('q') ?? '') !== q) setParam('q', q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  const { data: families = [] } = useSWR<RoleFamilyRow[]>('dashboard-role-families', dashboardApi.getRoleFamilies, {
    revalidateOnFocus: false,
  })

  const params = { family, category, q, agency, min_active: q ? 1 : minActive, sort, limit: 100 }
  const { data, isLoading, error } = useSWR<CompanyStatsResponse>(
    ['companies-stats', JSON.stringify(params)],
    () => companiesApi.getStats(params),
    { revalidateOnFocus: false, keepPreviousData: true },
  )

  // Industry options come from the data itself (MCF categories seen on the current rows).
  const categories = useMemo(() => {
    const set = new Set<string>(category ? [category] : [])
    for (const r of data?.rows ?? []) for (const c of Object.keys(r.category_counts)) set.add(c)
    return Array.from(set).sort()
  }, [data, category])

  const summary = data?.summary
  const focus = [family && familyLabel(family, families), category].filter(Boolean).join(' · ')
  const subtitle = focus
    ? `Who is hiring for ${focus}`
    : 'Who is hiring, what they pay, and how much of it is the same ad again'

  return (
    <div className="space-y-5">
      <PageHeader title="Companies" subtitle={subtitle} />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[12rem]">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" aria-hidden />
          <input
            type="search"
            aria-label="Search companies"
            placeholder="Search companies…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <select aria-label="Role family" className={selectCls} value={family} onChange={(e) => setParam('family', e.target.value)}>
          <option value="">All role families</option>
          {families
            .filter((f) => f.role_family !== 'other')
            .map((f) => (
              <option key={f.role_family} value={f.role_family}>
                {f.display_name}
              </option>
            ))}
        </select>
        <select aria-label="Industry" className={selectCls} value={category} onChange={(e) => setParam('category', e.target.value)}>
          <option value="">All industries</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <div role="group" aria-label="Employer type" className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden text-sm">
          {AGENCY_OPTIONS.map((a) => (
            <button
              key={a.value}
              type="button"
              aria-pressed={agency === a.value}
              onClick={() => setParam('agency', a.value === 'all' ? '' : a.value)}
              className={`px-2.5 py-1.5 ${
                agency === a.value
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
        <select
          aria-label="Minimum openings"
          className={selectCls}
          value={minActive}
          disabled={!!q}
          onChange={(e) => setParam('min_active', e.target.value === '10' ? '' : e.target.value)}
        >
          {MIN_ACTIVE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n === 1 ? 'Any openings' : `${n}+ openings`}
            </option>
          ))}
        </select>
      </div>

      {/* Summary strip */}
      <div className="space-y-1">
        {summary && summary.companies > 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            <span className="font-medium text-slate-700 dark:text-slate-200">{summary.companies.toLocaleString()}</span> companies ·{' '}
            <span className="font-medium text-slate-700 dark:text-slate-200">{summary.openings.toLocaleString()}</span> openings
            {summary.median_salary != null && (
              <>
                {' '}· median <span className="font-medium text-slate-700 dark:text-slate-200">${summary.median_salary.toLocaleString()}</span>/mo
              </>
            )}
            {data && data.rows.length < data.total_matching && <> · showing top {data.rows.length}</>}
          </p>
        )}
        <p className="text-xs text-slate-400 dark:text-slate-500">
          Repost rate = share of a company&apos;s live postings whose text has been posted before. Staffing agencies are identified by
          posting across 10+ role families or by name.
        </p>
      </div>

      {/* Results */}
      <Card>
        <CardBody>
          {isLoading && !data && <div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}
          {error && <EmptyState icon={Building2} message="Couldn't load companies" description="Try again later." />}
          {data && data.rows.length === 0 && (
            <EmptyState
              icon={Building2}
              message="No companies match"
              description={minActive > 1 && !q ? 'Lower the minimum openings or clear a filter.' : 'Try a different name or filter.'}
            />
          )}
          {data && data.rows.length > 0 && (
            <CompanyStatsTable
              rows={data.rows}
              sort={sort}
              onSort={(s) => setParam('sort', s === 'openings' ? '' : s)}
              familyRows={families}
              selectedFamily={family || undefined}
            />
          )}
        </CardBody>
      </Card>
    </div>
  )
}

export default function CompaniesPage() {
  return (
    <Layout userSlot={<NavUserActions />}>
      <Suspense fallback={<div className="h-48 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />}>
        <CompaniesExplorer />
      </Suspense>
    </Layout>
  )
}
