'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import useSWR from 'swr'
import { Building2, Search } from 'lucide-react'
import { companiesApi, dashboardApi } from '@/lib/api'
import type { CompanyStatsResponse, CompanyStatsSort, RoleFamilyRow } from '@/lib/types'
import { familyLabel } from '@/lib/roleFamilies'
import { AGENCY_TOOLTIP } from '@/app/components/AgencyTag'
import { Layout } from '@/app/components/layout'
import NavUserActions from '@/app/components/NavUserActions'
import { Card, CardBody, EmptyState, PageHeader } from '@/components/design'
import { CompanyStatsTable } from './CompanyStatsTable'

const MIN_ACTIVE_OPTIONS = [10, 3, 1] as const
const SORTS: CompanyStatsSort[] = ['openings', 'median_salary']

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
  const showAgencies = sp.get('agencies') === 'show'
  const sortParam = sp.get('sort') as CompanyStatsSort | null
  const sort: CompanyStatsSort = sortParam && SORTS.includes(sortParam) && (sortParam !== 'median_salary' || family) ? sortParam : 'openings'
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

  // A name search looks at everyone (no floor, agencies included); otherwise agencies are hidden by default.
  const agency = q || showAgencies ? 'all' : 'direct'
  const effectiveMin = q ? 1 : minActive
  const params = { family, category, q, agency, min_active: effectiveMin, sort, limit: 100 } as const
  const { data, isLoading, error } = useSWR<CompanyStatsResponse>(
    ['companies-stats', JSON.stringify(params)],
    () => companiesApi.getStats(params),
    { revalidateOnFocus: false, keepPreviousData: true },
  )
  // How many agencies the default view hides (same filters, agencies only).
  const hiddenParams = { family, category, agency: 'agency', min_active: effectiveMin, limit: 1 } as const
  const { data: hidden } = useSWR<CompanyStatsResponse>(
    agency === 'direct' ? ['companies-stats-hidden', JSON.stringify(hiddenParams)] : null,
    () => companiesApi.getStats(hiddenParams),
    { revalidateOnFocus: false },
  )

  const categories = useMemo(() => {
    const set = new Set<string>(category ? [category] : [])
    for (const r of data?.rows ?? []) for (const c of Object.keys(r.category_counts)) set.add(c)
    return Array.from(set).sort()
  }, [data, category])

  const summary = data?.summary
  const focus = [family && familyLabel(family, families), category].filter(Boolean).join(' · ')
  const subtitle = focus ? `Who is hiring for ${focus}` : 'Who is hiring in Singapore, and what they advertise'

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
            placeholder="Search a company…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <select aria-label="Job type" className={selectCls} value={family} onChange={(e) => setParam('family', e.target.value)}>
          <option value="">All job types</option>
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
        <label className={`inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 ${q ? 'opacity-50' : ''}`} title={AGENCY_TOOLTIP}>
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            checked={showAgencies || !!q}
            disabled={!!q}
            onChange={(e) => setParam('agencies', e.target.checked ? 'show' : '')}
          />
          Show recruitment agencies
        </label>
      </div>

      {/* Summary strip */}
      {summary && summary.companies > 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.companies.toLocaleString()}</span> companies ·{' '}
          <span className="font-medium text-slate-700 dark:text-slate-200">{summary.openings.toLocaleString()}</span> openings
          {agency === 'direct' && hidden != null && hidden.total_matching > 0 && (
            <> · {hidden.total_matching.toLocaleString()} recruitment {hidden.total_matching === 1 ? 'agency' : 'agencies'} hidden</>
          )}
          {data && data.rows.length < data.total_matching && <> · showing top {data.rows.length}</>}
        </p>
      )}

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
      <p className="text-xs text-slate-400 dark:text-slate-500">
        Recruitment agencies are companies registered under SSIC 78 (employment agencies). Salary figures are the median of
        advertised monthly ranges for the chosen job type. Openings count live listings.
      </p>
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
